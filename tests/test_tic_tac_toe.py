from __future__ import annotations

import asyncio
import json

import pytest
from conftest import SPEC
from pydantic import ValidationError

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER
from venom_module_cooperation_lab.tic_tac_toe import TicTacToe

LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)
DRAW = ["A1", "A2", "A3", "B1", "B3", "B2", "C1", "C3", "C2"]


def square(index):
    return "ABC"[index // 3] + str(index % 3 + 1)


def request(**fields):
    return RunRequest(model_id=SPEC.model_id, scenario_id="tic_tac_toe", **fields)


@pytest.mark.parametrize("line", LINES)
def test_referee_detects_every_winning_line_and_rejects_moves_after_end(line):
    game = TicTacToe()
    other = [i for i in range(9) if i not in line]
    for index, coordinate in enumerate(
        [
            square(line[0]),
            square(other[0]),
            square(line[1]),
            square(other[1]),
            square(line[2]),
        ]
    ):
        state = game.play("A" if index % 2 == 0 else "B", coordinate)
    assert state["winner"] == "A" and state["finished"] and not state["draw"]
    assert state["next_player"] is None
    with pytest.raises(LabError, match="invalid_game_move"):
        game.play("B", square(other[2]))
    state["board"][0] = "tampered"
    assert "tampered" not in game.board


def test_referee_detects_circle_win_and_full_board_draw():
    game = TicTacToe()
    for i, move in enumerate(["A1", "B1", "A2", "B2", "C3", "B3"]):
        state = game.play("A" if i % 2 == 0 else "B", move)
    assert state["winner"] == "B"
    game = TicTacToe()
    for i, move in enumerate(DRAW):
        state = game.play("A" if i % 2 == 0 else "B", move)
    assert state["draw"] and state["finished"] and state["winner"] is None


@pytest.mark.parametrize("move", ["", "A4", "D1", "A0", "B2 because", "A1 B2", "1A"])
def test_invalid_move_cannot_mutate_board(move):
    game = TicTacToe()
    before = game.public()
    with pytest.raises(LabError, match="invalid_game_move"):
        game.play("A", move)
    assert game.public() == before


def test_occupied_square_and_wrong_turn_preserve_state():
    game = TicTacToe()
    game.play("A", " a1 ")
    with pytest.raises(LabError, match="invalid_game_move"):
        game.play("A", "A2")
    game.play("B", "B1")
    before = game.public()
    with pytest.raises(LabError, match="occupied_game_square"):
        game.play("A", "A1")
    assert game.public() == before


def test_game_budget_is_nine_moves_and_legacy_limits_are_unchanged():
    config = RunConfig.build(request(), {})
    assert config.mode == "dialog" and config.budgets.max_turns == 9
    assert config.budgets.total_input_tokens == 9 * 2048
    for mode in ["single", "self_correction", "no_contact", "dialog_encouraged"]:
        with pytest.raises(ValidationError):
            request(mode=mode)
    with pytest.raises(ValidationError):
        RunRequest(model_id=SPEC.model_id, scenario_id="split_facts", max_turns=9)
    with pytest.raises(ValidationError):
        request(max_turns=10)


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en"])
@pytest.mark.parametrize(
    "moves,winner", [(["A1", "B1", "A2", "B2", "A3"], "A"), (DRAW, None)]
)
async def test_game_runner_uses_authoritative_board_and_stops_on_actual_result(
    rig, language, moves, winner
):
    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        adapter = factory(model, lease)
        adapter.responses = [
            json.dumps(
                {
                    "kind": "complete",
                    "recipient": "B" if i % 2 == 0 else "A",
                    "content": move,
                }
            )
            for i, move in enumerate(moves)
        ]
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(request(communication_language=language), "game")
    await asyncio.wait_for(runner.jobs[row["id"]].task, timeout=5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    assert len(adapters[0].recorded) == len(moves)
    events = runner.store.events(row["id"], owner=OWNER)
    states = [event["payload"] for event in events if event["kind"] == "game"]
    assert len(states) == len(moves) + 1
    assert states[-1]["winner"] == winner
    assert states[-1]["draw"] is (winner is None)
    assert states[-1]["finished"]
    assert all(
        e["payload"]["sequence"] == e["seq"] for e in events if e["kind"] == "message"
    )
    prompt = adapters[0].recorded[1][1][-1].content
    assert "A X . ." in prompt
    assert ("Aktualna plansza" if language == "pl" else "Current board") in prompt
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_invalid_model_move_is_visible_not_delivered_and_releases_runtime(rig):
    runner, _ = rig
    row, _ = await runner.start(request(), "bad-game")
    await asyncio.wait_for(runner.jobs[row["id"]].task, timeout=5)
    assert runner.snapshot(row["id"])["run"]["status"] == "failed"
    events = runner.store.events(row["id"], owner=OWNER)
    message = next(event["payload"] for event in events if event["kind"] == "message")
    assert message["content"] == "Message from A"
    assert message["delivered_to"] == []
    assert events[-1]["payload"]["reason_code"] == "invalid_game_move"
    assert runner.admission.snapshot()["status"] == "available"
