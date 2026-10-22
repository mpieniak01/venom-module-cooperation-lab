"""Independent tactical oracles and solver verification, never model assistance."""

from __future__ import annotations

import random

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.games import (
    MemoryEnvironment,
    NimEnvironment,
    SokobanEnvironment,
    TicTacToeEnvironment,
    make_environment,
    state_digest,
)
from venom_module_cooperation_lab.evaluation.manifest import list_cases
from venom_module_cooperation_lab.evaluation.references import (
    assess,
    nim_sum,
    reference_action,
    solve_sokoban,
)


def test_minimax_tactical_wins_blocks_and_no_mutation():
    win = TicTacToeEnvironment({"board": ["X", "X", "", "O", "O", "", "", "", ""]})
    before = state_digest(win)
    best = assess(win, "A", {"square": "A3"})
    missed = assess(win, "A", {"square": "C1"})
    assert best["value_before"] == best["value_after"] == 1
    assert best["optimal"] and not best["missed_win"]
    assert missed["missed_win"] and missed["missed_block"] and missed["worse_move"]
    assert state_digest(win) == before
    assert reference_action(win, "optimal", random.Random(17)) == {"square": "A3"}
    block = TicTacToeEnvironment({"board": ["O", "O", "", "X", "", "", "", "X", ""]})
    assert assess(block, "A", {"square": "C3"})["missed_block"]
    assert not assess(block, "A", {"square": "A3"})["missed_block"]


def test_minimax_identifies_fork_and_unavoidable_loss():
    fork = TicTacToeEnvironment({"board": ["X", "", "", "", "O", "O", "", "", "X"]})
    assessment = assess(fork, "A", {"square": "C1"})
    assert assessment["created_fork"]
    assert assess(fork, "A", {"square": "A2"})["missed_fork"]
    for field in ("A2", "A3", "B1", "C1", "C2"):
        assert isinstance(assess(fork, "A", {"square": field})["value_after"], int)


def test_nim_losing_start_is_not_an_error_and_winning_loss_is():
    losing = NimEnvironment({"heaps": [1, 2, 3]})
    assert nim_sum(losing.heaps) == 0
    for action in losing.legal_actions():
        metrics = assess(losing, "A", action)
        assert not metrics["lost_winning_position"]
        assert not metrics["winning_position_before"] and metrics["optimal"]
    winning = NimEnvironment({"heaps": [3, 4, 5]})
    action = reference_action(winning, "optimal", random.Random(17))
    assert assess(winning, "A", action)["winning_position_after"]
    assert assess(winning, "A", {"heap": 0, "take": 1})["lost_winning_position"]
    last = NimEnvironment({"heaps": [1]})
    assert assess(last, "A", {"heap": 0, "take": 1})["winning_position_after"]


def test_memory_assessment_uses_only_previously_revealed_pairs():
    env = MemoryEnvironment({}, 17)
    pair = [0, next(i for i in range(1, 16) if env._cards[0] == env._cards[i])]
    assert not assess(env, "A", {"cards": [0, 1]})["missed_known_pair"]
    # Reveal each partner in a mismatch, leaving a known but unmatched pair.
    distractors = [i for i in range(16) if env._cards[i] != env._cards[0]][:2]
    env.step("A", {"cards": [pair[0], distractors[0]]})
    env.step("A", {"cards": [pair[1], distractors[1]]})
    assert env.known_pairs() == [pair]
    assert assess(env, "A", {"cards": distractors})["missed_known_pair"]
    assert not assess(env, "A", {"cards": list(reversed(pair))})["missed_known_pair"]
    assert reference_action(env, "remembering", random.Random(17)) == {"cards": pair}
    env.step("A", {"cards": distractors})
    assert env.result()["known_pairs_missed"] == 1


@pytest.mark.parametrize(
    "case",
    [case for case in list_cases() if case["game"] == "sokoban"],
    ids=lambda case: case["id"],
)
def test_sokoban_solver_paths_and_scores_are_exact_and_replayable(case):
    env = make_environment("sokoban", case["config"], case["seed"])
    solved = solve_sokoban(env)
    assert solved["solvable"] and 0 < solved["min_pushes"] <= solved["min_moves"]
    assert len(solved["path"]) == solved["min_moves"]
    for action in solved["path"]:
        metrics = assess(env, "A", action)
        assert metrics["optimal_step"] and not metrics["introduced_deadlock"]
        env.step("A", action)
    assert env.result()["success"]
    assert env.result()["moves"] == solved["min_moves"]
    assert env.result()["pushes"] >= solved["min_pushes"]
    assert solve_sokoban(env)["min_moves"] == 0


def test_sokoban_deadlock_and_bounded_solver_failures_are_environment_errors():
    env = SokobanEnvironment(
        {"board": ["#######", "# .   #", "# $@  #", "#     #", "#######"]}
    )
    metrics = assess(env, "A", {"move": "left"})
    assert metrics["introduced_deadlock"] and metrics["min_moves_after"] is None
    env.step("A", {"move": "left"})
    assert not solve_sokoban(env)["solvable"]
    with pytest.raises(LabError, match="reference_no_action"):
        reference_action(env, "optimal", random.Random(17))
    blocked = SokobanEnvironment({"board": ["#####", "#@$ #", "# . #", "#####"]})
    assert not solve_sokoban(blocked)["solvable"]
    with pytest.raises(LabError, match="reference_unsolvable"):
        reference_action(blocked, "optimal", random.Random(17))
    for bad_limit in (0, True, 20001):
        with pytest.raises(LabError, match="invalid_solver_limit"):
            solve_sokoban(blocked, bad_limit)
    with pytest.raises(LabError, match="environment_solver_limit"):
        solve_sokoban(blocked, 1)


def test_reference_random_is_seeded_and_unsupported_is_explicit():
    env = NimEnvironment({})
    assert reference_action(env, "random", random.Random(3)) == reference_action(
        env, "random", random.Random(3)
    )
    with pytest.raises(LabError, match="unsupported_reference"):
        reference_action(env, "remembering", random.Random(3))
    assert assess(env, "B", {"heap": 0, "take": 1}) == {
        "legal": False,
        "reference_version": "reference-v1",
    }
    assert not assess(env, "A", {"heap": True, "take": 1})["legal"]
    assert not assess(MemoryEnvironment({}, 17), "A", {"cards": [False, 1]})["legal"]
    assert not assess(MemoryEnvironment({}, 17), "A", {"cards": [0, 1], "extra": 1})[
        "legal"
    ]
    assert not assess(env, "A", {"heap": -1, "take": 1})["legal"]
