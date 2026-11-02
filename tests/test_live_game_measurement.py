"""CPU evidence of measurement correctness, not model learning or inference."""

from __future__ import annotations

import asyncio
import copy

import pytest
from pydantic import ValidationError

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.live_game_measurement import canonical_board
from venom_module_cooperation_lab.live_game_strategy import LiveGameStrategy
from venom_module_cooperation_lab.rule_reflection import _transform, supported_rules
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER, LabRunner
from venom_module_cooperation_lab.tic_tac_toe import TicTacToe

WIN = ["X", "X", "", "O", "O", "", "", "", ""]
BLOCK = ["O", "O", "", "X", "", "", "", "X", ""]


def board(cells):
    """Build a mutable board fixture with a matching move counter."""
    return TicTacToe(board=list(cells), moves=sum(bool(c) for c in cells))


def test_opportunities_prioritize_win_and_measure_actual_proposals_before_solver():
    """Score the model proposal before any solver correction."""
    strategy = LiveGameStrategy("game_assisted")
    record = strategy.choose(board(WIN), "A", "C1", 0)
    assert record["model_action"] == {"square": "C1"}
    assert record["action"] != record["model_action"]
    counts = strategy.public()["measurement"]["totals"]
    assert counts["win_opportunities"] == 1
    assert counts["wins_taken"] == counts["block_opportunities"] == 0
    assert counts["solver_interventions"] == 1
    assert counts["optimal_moves"] == 0
    strategy.choose(board(BLOCK), "A", "A3", 0)
    counts = strategy.public()["measurement"]["totals"]
    assert counts["blocks_taken"] == counts["block_opportunities"] == 1
    assert counts["legal_moves"] == counts["proposals"] == 2


def test_unavoidable_fork_is_not_a_missed_possible_block():
    """Exclude multiple immediate threats from possible single-move blocks."""
    strategy = LiveGameStrategy("game_strategic")
    game = board(["O", "O", "", "O", "X", "X", "", "X", ""])
    proposal = strategy.choose(game, "A", "A3", 0)
    assert proposal["assessment"]["missed_block"] is True  # frozen scorer unchanged
    totals = strategy.public()["measurement"]["totals"]
    assert totals["unavoidable_threats"] == 1
    assert totals["block_opportunities"] == totals["blocks_taken"] == 0


@pytest.mark.parametrize("rotation", range(4))
@pytest.mark.parametrize("mirror", [False, True])
def test_repeated_errors_are_symmetry_aware_but_private_to_player(rotation, mirror):
    """Recognize symmetric repeated mistakes without sharing player evidence."""
    strategy = LiveGameStrategy("game_reflection")
    strategy.choose(board(WIN), "A", "C1", 0)
    strategy.begin()
    transformed, action = _transform(WIN, "C1", rotation, mirror)
    result = strategy.choose(board(transformed), "A", action, 0)
    assert result["tactical_measurement"]["win_now"]["repeated_error"] is True
    swapped = ["O" if c == "X" else "X" if c == "O" else "" for c in WIN]
    strategy.choose(board(["O", "O", "", "X", "X", "", "", "", "X"]), "B", "C1", 0)
    assert canonical_board(swapped, "B") == canonical_board(WIN, "A")
    assert strategy.public()["measurement"]["totals"]["repeated_tactical_errors"] == 1
    assert strategy.public()["measurement"]["games"][0]["repeated_tactical_errors"] == 0
    assert strategy.public()["measurement"]["games"][1]["repeated_tactical_errors"] == 1


def test_rule_opportunities_and_transfer_are_observed_not_implied_by_acceptance():
    """Count actual applications separately from rule acceptance."""
    strategy = LiveGameStrategy("game_reflection")
    strategy.choose(board(WIN), "A", "C1", 0)
    strategy.note_ids["A"] = "win_now"
    strategy.evidence["A"] = {"board": WIN}
    rotated, square = _transform(WIN, "A3", 1, True)
    strategy.choose(board(rotated), "A", square, 0)
    strategy.choose(board(["X", "X", "", "O", "", "", "O", "", ""]), "A", "B2", 0)
    strategy.choose(TicTacToe(), "A", "A1", 0)
    data = strategy.public()["measurement"]
    assert data["rules"]["A"]["win_now"] == {
        "without_reminder": {"opportunities": 1, "followed": 0},
        "with_reminder": {"opportunities": 2, "followed": 1},
    }
    assert data["transfer"]["A"] == {
        "source_equivalent": {"opportunities": 1, "followed": 1},
        "new_position": {"opportunities": 1, "followed": 0},
    }
    assert data["totals"]["first_empty_choices"] >= 1
    data["totals"]["legal_moves"] = 100
    assert strategy.public()["measurement"]["totals"]["legal_moves"] == 4


@pytest.mark.parametrize(
    "raw,code", [("A1 A2", "invalid_format"), ("A1", "occupied_game_square")]
)
def test_bad_model_proposals_do_not_disappear_from_legality_denominator(raw, code):
    """Keep malformed and illegal answers in the proposal denominator."""
    strategy = LiveGameStrategy("game_strategic")
    game = board(WIN)
    with pytest.raises(LabError, match=code):
        strategy.choose(game, "A", raw, 0)
    strategy.measurement.stop("failed", code)
    data = strategy.public()["measurement"]
    assert data["totals"]["proposals"] == 1
    assert data["totals"]["legal_moves"] == 0
    assert data["games"][0]["status"] == "failed"
    assert data["failure_category"] == (
        "format" if code == "invalid_format" else "illegal_move"
    )


@pytest.mark.parametrize(
    "status,reason,category",
    [
        ("failed", "runtime_busy", "infrastructure"),
        ("cancelled", "run_cancelled", "cancelled"),
        ("completed", None, None),
    ],
)
def test_technical_end_never_invents_a_completed_game(status, reason, category):
    """Preserve unfinished games when execution stops or fails."""
    strategy = LiveGameStrategy("game_strategic")
    strategy.measurement.stop(status, reason)
    data = strategy.public()["measurement"]
    assert data["failure_category"] == category
    assert data["totals"]["proposals"] == 0
    assert data["games"][0]["status"] != "completed"


def test_grounded_context_is_explicit_versioned_and_preserves_legacy_requests():
    """Version the optional context while preserving legacy idempotency."""
    request = RunRequest(
        model_id="fixture", scenario_id="tic_tac_toe", mode="game_reflection"
    )
    baseline = RunConfig.build(request, {"model_id": "fixture"}).public()
    example_request = request.model_copy(
        update={"reflection_context": "grounded_example"}
    )
    example = RunConfig.build(example_request, {"model_id": "fixture"}).public()
    assert baseline["strategy_version"] == "ttt-coaching-v4"
    assert example["strategy_version"] == "ttt-coaching-v5-grounded-example"
    assert baseline["config_hash"] != example["config_hash"]
    assert baseline["budgets"] == example["budgets"]
    for config, req in [(baseline, request), (example, example_request)]:
        assert LabRunner._same_request(config, req, False)
    old = copy.deepcopy(baseline)
    old.pop("reflection_context")
    assert LabRunner._same_request(old, request, False)
    assert not LabRunner._same_request(old, example_request, False)
    with pytest.raises(
        ValidationError, match="reflection_context_requires_reflection_mode"
    ):
        RunRequest(
            model_id="fixture",
            scenario_id="tic_tac_toe",
            mode="game_strategic",
            reflection_context="grounded_example",
        )


@pytest.mark.parametrize("language", ["pl", "en"])
def test_grounded_reminder_is_private_historical_and_carries_a_verified_better_move(
    language,
):
    """Keep the verified historical example private and explicitly labeled."""
    strategy = LiveGameStrategy("game_reflection", grounded_example=True)
    strategy.choose(board(WIN), "A", "C1", 0)
    evidence = supported_rules(strategy.feedback(board(WIN), "A"))["win_now"]
    assert evidence["better_actions"] == [{"square": "A3"}]
    strategy.notes = {"A": "PRIVATE_A", "B": "PRIVATE_B"}
    strategy.evidence["A"] = {
        "board": WIN,
        "mistaken_move": {"square": "C1"},
        "better_moves": evidence["better_actions"],
    }
    own = strategy.reminder("A", language)
    assert "A3" in own
    assert "C1" in own
    assert "PRIVATE_B" not in own
    assert ("NIE aktualna" if language == "pl" else "NOT the current") in own
    assert "A3" not in strategy.reminder("B", language)
    assert "PRIVATE_A" in strategy.memory("A", language)
    strategy.grounded_example = False
    assert strategy.reminder("A", language) == "PRIVATE_A"


@pytest.mark.asyncio
async def test_runner_persists_failure_measurements_and_original_proposal(rig):
    """Persist rejected raw output and measurements before terminal status."""
    runner, _ = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        """Supply deterministic fake responses without invoking a model."""
        adapter = factory(model, lease)
        adapter.responses = ["A1", "A1"]
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b", scenario_id="tic_tac_toe", mode="game_strategic"
        ),
        "measured-failure",
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    events = runner.store.events(row["id"], owner=OWNER, limit=100)
    last = [e["payload"] for e in events if e["kind"] == "game"][-1]
    data = last["strategy"]["measurement"]
    assert data["totals"]["proposals"] == 2
    assert data["totals"]["legal_moves"] == 1
    assert data["totals"]["illegal_moves"] == 1
    assert data["games"][0]["status"] == "failed"
    assert last["finished"] is False
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    assert messages[-1]["raw_content"] == "A1"
    assert messages[-1]["delivered_to"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("context", ["rule_only", "grounded_example"])
async def test_runner_carries_only_own_grounded_example_and_keeps_control_prompt(
    rig, context
):
    """Exercise both context variants through the CPU-only runner."""
    import json

    runner, adapters = rig
    factory = runner.adapter_factory

    def configured(model, lease):
        """Supply deterministic fake responses without invoking a model."""
        adapter = factory(model, lease)
        adapter.responses = [
            "A1",
            "A2",
            "A3",
            "B2",
            "B1",
            "B3",
            "C1",
            '{"rule_id":"block_win"}',
            '{"rule_id":"win_now"}',
            "A1",
            "A2",
            "A3",
            "B2",
            "B1",
            "B3",
            "C1",
        ]
        return adapter

    runner.adapter_factory = configured
    row, _ = await runner.start(
        RunRequest(
            model_id="test-0.4b",
            scenario_id="tic_tac_toe",
            mode="game_reflection",
            game_count=2,
            reflection_context=context,
        ),
        "grounded-" + context,
    )
    await asyncio.wait_for(runner.jobs[row["id"]].task, 5)
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    records = adapters[0].recorded
    first_note = json.loads(records[7][1][1].content)
    assert all(
        ("better_moves" in item) == (context == "grounded_example")
        for item in first_note["supported_rules"].values()
    )
    next_a = records[9][1][-1].content
    next_b = records[10][1][-1].content
    assert ("Past-game example" in next_a) == (context == "grounded_example")
    assert ("Past-game example" in next_b) == (context == "grounded_example")
    assert "block the opponent" in next_a
    assert "Take an immediate winning move" in next_b
    events = []
    after = 0
    while page := runner.store.events(row["id"], owner=OWNER, after=after, limit=100):
        events.extend(page)
        after = page[-1]["seq"]
    last = [e["payload"] for e in events if e["kind"] == "game"][-1]
    data = last["strategy"]["measurement"]
    assert len(data["games"]) == 2
    assert all(g["status"] == "completed" for g in data["games"])
    assert data["totals"]["legal_moves"] == 14
    assert data["run_status"] == "completed"
