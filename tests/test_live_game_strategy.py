"""Live conversation variants: board transitions, coaching and private notes."""

from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from venom_module_cooperation_lab.live_game_strategy import LiveGameStrategy
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER
from venom_module_cooperation_lab.tic_tac_toe import TicTacToe


@pytest.mark.parametrize("mode", ["game_strategic", "game_reflection", "game_assisted"])
def test_live_variants_have_versioned_identity_and_require_game(mode):
    with pytest.raises(ValidationError):
        RunRequest(model_id="fixture", scenario_id="split_facts", mode=mode)
    req = RunRequest(model_id="fixture", scenario_id="tic_tac_toe", mode=mode)
    cfg = RunConfig.build(req, {}).public()
    assert cfg["schema_version"] == 6
    assert cfg["scheduler"] == "live-game-strategy-v2"
    assert cfg["strategy_version"] == "ttt-coaching-v2"
    assert "Plan ahead" in cfg["prompts"][0]
    if mode == "game_reflection":
        assert cfg["game_count"] == 3 and cfg["remember_games"]
        assert cfg["budgets"]["total_input_tokens"] == 33 * 2048


@pytest.mark.parametrize(
    "fields", [{"game_count": 1}, {"remember_games": False}, {"max_turns": 5}]
)
def test_reflection_rejects_unusable_memory_or_incomplete_games(fields):
    with pytest.raises(ValidationError):
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            **fields,
        )


def test_live_solver_preserves_proposal_and_unassisted_game_keeps_mistakes():
    board = ["X", "X", "", "O", "O", "", "", "", ""]
    for mode, expected in [
        ("game_strategic", "B3"),
        ("game_reflection", "B3"),
        ("game_assisted", "A3"),
    ]:
        strategy = LiveGameStrategy(mode)
        record = strategy.choose(
            TicTacToe(board=board, moves=4), "A", '{"square":"B3"}', 7
        )
        assert record["model_action"] == {"square": "B3"}
        assert record["action"] == {"square": expected}
        assert record["assessment"]["missed_win"]
        assert strategy.public()["solver_interventions"] == (mode == "game_assisted")
        assert ("lesson" in record) == (mode == "game_reflection")


@pytest.mark.asyncio
async def test_live_reflection_is_charged_published_and_carried_only_to_own_player(rig):
    runner, adapters = rig
    factory = runner.adapter_factory
    moves = ["A1", "B1", "A2", "B2", "A3"]
    note_a = "Take an immediate winning move before considering a defensive block."
    note_b = "Block the opponent winning line when I cannot win this turn."

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = (
            moves + ['{"rule":"' + note_a + '"}', '{"rule":"' + note_b + '"}']
        ) * 2
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=2,
            communication_language="en",
        ),
        "live-notes",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    notes = [e["payload"] for e in events if e["kind"] == "reflection"]
    assert len(notes) == 4 and [n["player"] for n in notes] == ["A", "B", "A", "B"]
    assert notes[1]["feedback"]["lessons"]
    assert all(n["feedback"]["player"] == n["player"] for n in notes)
    calls = adapters[0].recorded
    assert len(calls) == 14
    assert note_a in calls[7][1][0].content
    assert note_b not in calls[7][1][0].content
    assert note_b in calls[8][1][0].content
    assert note_a not in calls[8][1][0].content
    assert "A:A1 B:B1" not in calls[7][1][0].content
    assert all(n["accepted"] for n in notes)
    assert calls[0][2].temperature == 0.8
    assert calls[0][2].allowed_outputs == ()
    assert calls[0][2].session_protocol == "game-eval-v2"
    assert sum(e["kind"] == "usage" for e in events) == 14
    assert sum(e["kind"] == "message" for e in events) == 10
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_live_assisted_updates_board_and_transcript_with_executed_move(rig):
    from dataclasses import replace

    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        original = adapter.generate

        def generate(player, messages, params, deadline):
            # Propose the first free cell; the host may replace poor proposals.
            board = runner.jobs[next(iter(runner.jobs))].game
            coordinate = next(
                "ABC"[i // 3] + str(i % 3 + 1)
                for i, v in enumerate(board.board)
                if not v
            )
            return replace(
                original(player, messages, params, deadline), text=coordinate
            )

        adapter.generate = generate
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b", scenario_id="tic_tac_toe", mode="game_assisted"
        ),
        "live-assisted",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    interventions = [m for m in messages if m["assistance"]["applied"]]
    assert interventions
    assert all(m["model_move"] != m["game_move"] == m["content"] for m in interventions)
    assert all(m["raw_content"] == m["model_move"] for m in messages)
    assert len(adapters[0].recorded) == len(messages)  # No hidden retries.
    final = [e["payload"] for e in events if e["kind"] == "game"][-1]
    assert final["finished"] and final["draw"]
    assert final["strategy"]["result_scope"] == "assisted"
    assert final["strategy"]["solver_interventions"] == len(interventions)
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("response", ["not a move", '{"square":"A1"}'])
async def test_live_variant_errors_are_durable_and_never_retried(rig, response):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = ["A1", response]
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b", scenario_id="tic_tac_toe", mode="game_assisted"
        ),
        "invalid-live",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "failed"
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    assert len(adapters[0].recorded) == 2
    assert messages[-1]["raw_content"] == response
    assert messages[-1]["delivered_to"] == []
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_invalid_notes_are_journalled_but_not_replayed_or_fatal(rig):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = ["A1", "B1", "A2", "B2", "A3", "", "<think>unfinished"] * 2
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=2,
        ),
        "invalid-reflection",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    notes = [e["payload"] for e in events if e["kind"] == "reflection"]
    assert len(notes) == 4 and all(
        n["accepted"] is False and not n["content"] for n in notes
    )
    assert {n["reason_code"] for n in notes} == {"empty_note", "unfinished_note"}
    assert len(adapters[0].recorded) == 14
    assert "<think>unfinished" not in adapters[0].recorded[8][1][0].content
    final = [e["payload"] for e in events if e["kind"] == "game"][-1]
    assert final["series"]["number"] == 2 and final["finished"]
    assert final["strategy"]["accepted_notes"] == 0
    assert final["strategy"]["rejected_notes"] == 4
