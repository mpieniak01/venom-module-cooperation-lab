from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from venom_module_cooperation_lab.game_series import GameSeries
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER


@pytest.mark.parametrize(
    "fields",
    [
        {"game_count": 0},
        {"game_count": 11},
        {"game_count": True},
        {"game_count": 2, "max_turns": 8},
        {"scenario_id": "split_facts", "game_count": 2},
        {"scenario_id": "split_facts", "remember_games": False},
    ],
)
def test_series_rejects_invalid_or_unrelated_settings(fields):
    with pytest.raises(ValidationError):
        RunRequest(**({"model_id": "fixture", "scenario_id": "tic_tac_toe"} | fields))


def test_series_has_explicit_identity_and_bounded_aggregate_budgets():
    one = RunConfig.build(RunRequest(model_id="fixture", scenario_id="tic_tac_toe"), {})
    assert "game_count" not in one.public() and "remember_games" not in one.public()
    many = RunConfig.build(
        RunRequest(model_id="fixture", scenario_id="tic_tac_toe", game_count=10), {}
    )
    assert many.public()["schema_version"] == 4
    assert many.public()["scheduler"] == "board-series-memory-v1"
    assert many.budgets.total_input_tokens == 90 * 2048
    assert many.budgets.wall_seconds == 1800
    assert many.budgets.max_context_tokens == 2048
    off = RunConfig.build(
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            game_count=10,
            remember_games=False,
        ),
        {},
    )
    assert off.public()["config_hash"] != many.public()["config_hash"]


def test_memory_is_bounded_public_results_not_host_strategy():
    series = GameSeries(10, True)
    for n in range(1, 6):
        series.begin(n)
        series.record("A", "A1", {"finished": True, "winner": "A", "draw": False})
    memory = series.memory("B", "en")
    assert "#1:" not in memory and "#2:" not in memory
    assert "#3:" in memory and "#5:" in memory and "A:A1" in memory
    assert "You are B" in memory and "not the current board" in memory
    assert "zakończone partie" in series.memory("A", "pl")
    snapshot = series.public()
    snapshot["results"][0]["moves"].append("bad")
    assert "bad" not in series.results[0]["moves"]
    series.remember = False
    assert series.memory("A", "en") == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("remember", [True, False])
async def test_two_games_keep_weights_reset_contexts_and_publish_actual_results(
    rig, remember
):
    runner, adapters = rig
    factory = runner.adapter_factory
    resets = []

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = ["A1", "B1", "A2", "B2", "A3"] * 2
        adapter.reset = lambda: resets.append(True)
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            game_count=2,
            remember_games=remember,
            communication_language="en",
        ),
        "series",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    retried, created = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            game_count=2,
            remember_games=remember,
            communication_language="en",
        ),
        "series",
    )
    assert retried["id"] == row["id"] and not created
    assert len(adapters) == 1 and len(resets) == 2 and adapters[0].closed
    assert len(adapters[0].recorded) == 10
    first_second_game = adapters[0].recorded[5]
    assert first_second_game[0] == "A"
    system = first_second_game[1][0].content
    assert ("A:A1 B:B1 A:A2 B:B2 A:A3" in system) is remember
    assert ("result=A" in system) is remember
    assert "Current board" in first_second_game[1][-1].content
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    games = [event["payload"] for event in events if event["kind"] == "game"]
    assert games[-1]["series"]["number"] == 2
    assert [v["winner"] for v in games[-1]["series"]["results"]] == ["A", "A"]
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    assert [e["game_number"] for e in messages] == [1] * 5 + [2] * 5
    assert messages[5]["in_reply_to"] is None
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_error_in_second_game_never_starts_third_game(rig):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = ["A1", "B1", "A2", "B2", "A3", "D1"]
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(model_id="test-0.4b", scenario_id="tic_tac_toe", game_count=3),
        "series-error",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "failed"
    assert len(adapters[0].recorded) == 6 and adapters[0].closed
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    games = [e["payload"] for e in events if e["kind"] == "game"]
    assert games[-1]["series"]["number"] == 2
    assert len(games[-1]["series"]["results"]) == 1
    assert runner.admission.snapshot()["status"] == "available"
