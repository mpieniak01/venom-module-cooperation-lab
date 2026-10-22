"""Rule transitions and strict invalid actions, independent of GPU/runtime."""

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
    sokoban_transition,
    state_digest,
)
from venom_module_cooperation_lab.evaluation.manifest import (
    CASES,
    list_cases,
    manifest_hash,
)
from venom_module_cooperation_lab.evaluation.references import reference_action


@pytest.mark.parametrize("case", list_cases(), ids=lambda case: case["id"])
def test_seeded_case_replays_identical_public_transitions(case):
    one = make_environment(case["game"], case["config"], case["seed"])
    two = make_environment(case["game"], case["config"], case["seed"])
    rng = random.Random(case["seed"])
    reference = "remembering" if case["game"] == "memory" else "optimal"
    for _ in range(case["max_actions"]):
        assert state_digest(one) == state_digest(two)
        if one.finished:
            break
        action = reference_action(one, reference, rng)
        state = one.step(one.current_player, action)
        assert state == two.step(two.current_player, action)
    assert one.finished
    assert one.result()["success"]
    assert one.legal_actions() == []
    assert one.observation("A")["finished"]
    with pytest.raises(LabError, match="illegal_action"):
        one.step(one.current_player, {})


def test_ttt_three_in_line_and_role_swap_preserve_existing_referee():
    env = TicTacToeEnvironment({"starting_player": "B"})
    for player, field in zip("BABAB", ["A1", "B1", "A2", "B2", "A3"], strict=True):
        env.step(player, {"square": field})
    assert env.result() == {
        "success": True,
        "winner": "B",
        "draw": False,
        "actions": 5,
        "board_moves": 5,
    }
    assert env.observation("B")["your_symbol"] == "X"


def test_ttt_rejects_wrong_player_extra_key_occupied_and_bad_coordinate():
    env = TicTacToeEnvironment({})
    for player, action in [
        ("B", {"square": "A1"}),
        ("A", {"square": "a1"}),
        ("A", {"square": "A1", "extra": 1}),
        ("A", {"square": True}),
    ]:
        with pytest.raises(LabError, match="illegal_action"):
            env.step(player, action)
    env.step("A", {"square": "A1"})
    with pytest.raises(LabError, match="illegal_action"):
        env.step("B", {"square": "A1"})
    assert env.result()["actions"] == 1


@pytest.mark.parametrize(
    "config",
    [
        {"board": [""] * 8},
        {"board": [False] * 9},
        {"starting_player": "C"},
        {"starting_player": []},
        {"board": ["O"] + [""] * 8},
        {"current_player": "B"},
        {"board": ["X"] * 3 + ["O"] * 3 + [""] * 3},
        {"board": ["O"] * 3 + ["X", "X", "", "X", "X", ""]},
        {"board": ["X"] * 3 + ["O", "O", "", "O", "", ""]},
        {"unknown": 2},
    ],
)
def test_ttt_rejects_invalid_start(config):
    with pytest.raises(LabError, match="invalid_game_config"):
        TicTacToeEnvironment(config)


def test_ttt_draw_and_precompleted_state():
    env = TicTacToeEnvironment({"board": ["X", "O", "X", "X", "O", "O", "O", "X", "X"]})
    assert env.finished and env.result()["draw"]
    assert env.public_state()["current_player"] is None
    won = TicTacToeEnvironment({"board": ["X", "X", "X", "O", "O", "", "", "", ""]})
    assert won.result()["winner"] == "A"


def test_nim_last_stone_wins_with_zero_heaps_and_swapped_starter():
    env = NimEnvironment({"heaps": [0, 2], "starting_player": "B"})
    assert env.legal_actions() == [{"heap": 1, "take": 1}, {"heap": 1, "take": 2}]
    env.step("B", {"heap": 1, "take": 2})
    assert env.finished and env.result()["winner"] == "B"


@pytest.mark.parametrize(
    "action",
    [
        {"heap": -1, "take": 1},
        {"heap": 3, "take": 1},
        {"heap": 0, "take": 0},
        {"heap": 0, "take": 4},
        {"heap": True, "take": 1},
        {"heap": 0, "take": True},
        {"heap": 0, "take": 1, "retry": True},
        {"heap": 0},
    ],
)
def test_nim_strict_actions_do_not_mutate_on_rejection(action):
    env = NimEnvironment({})
    before = state_digest(env)
    with pytest.raises(LabError, match="illegal_action"):
        env.step("A", action)
    assert state_digest(env) == before


@pytest.mark.parametrize(
    "config",
    [
        {"heaps": []},
        {"heaps": [0]},
        {"heaps": [True]},
        {"heaps": [-1]},
        {"heaps": [33]},
        {"heaps": [32] * 5},
        {"heaps": [1] * 9},
        {"starting_player": "C"},
        {"starting_player": []},
    ],
)
def test_nim_configuration_is_bounded(config):
    with pytest.raises(LabError, match="invalid_game_config"):
        NimEnvironment(config)


@pytest.mark.parametrize(
    "action",
    [
        {"cards": [0]},
        {"cards": [0, 0]},
        {"cards": [0, 16]},
        {"cards": [0, -1]},
        {"cards": [False, 5]},
        {"cards": (0, 5)},
        {"cards": [0, 5], "extra": 1},
    ],
)
def test_memory_strict_pair_selection(action):
    env = MemoryEnvironment({}, 17)
    with pytest.raises(LabError, match="illegal_action"):
        env.step("A", action)
    assert env.attempts == 0


def test_memory_accepts_reversed_pair_and_rejects_matched_cards():
    env = MemoryEnvironment({}, 17)
    first = next(i for i in range(1, 16) if env._cards[i] == env._cards[0])
    env.step("A", {"cards": [first, 0]})
    assert env.result()["pairs_found"] == 1
    with pytest.raises(LabError, match="illegal_action"):
        env.step(
            "A", {"cards": [0, next(i for i in range(16) if i not in env.matched)]}
        )
    for size in (2, True, "4"):
        with pytest.raises(LabError, match="invalid_game_config"):
            MemoryEnvironment({"size": size}, 17)


def test_sokoban_blocked_push_never_pulls_or_leaves_board():
    env = SokobanEnvironment({"board": ["#####", "#@$ #", "# . #", "#####"]})
    with pytest.raises(LabError, match="illegal_action"):
        env.step("A", {"move": "up"})
    with pytest.raises(LabError, match="illegal_action"):
        env.step("A", {"move": "teleport"})
    assert (
        sokoban_transition(env.floor, env.player_position, env.box_position, "wrong")
        is None
    )
    pushed = env.transition("right")
    assert pushed == ((1, 2), (1, 3), True)
    assert sokoban_transition(env.floor, (1, 2), (1, 3), "right") is None
    moved = env.transition("down")
    assert moved == ((2, 1), (1, 2), False)
    assert env.public_state()["board"][2][2] == "."


def test_sokoban_stops_at_exact_reachability_deadlock():
    env = SokobanEnvironment(
        {"board": ["#######", "# .   #", "# $@  #", "#     #", "#######"]}
    )
    env.step("A", {"move": "left"})
    assert env.finished and env.result()["deadlock"]
    assert not env.result()["success"]
    assert env.result()["pushes"] == 1


def test_sokoban_target_and_player_target_markers():
    solved = SokobanEnvironment({"board": ["#####", "#@* #", "#####"]})
    assert solved.finished and solved.result()["success"]
    assert "*" in solved.public_state()["board"][1]
    standing = SokobanEnvironment({"board": ["#####", "#+$ #", "#####"]})
    assert "+" in standing.public_state()["board"][1]


@pytest.mark.parametrize(
    "board",
    [
        [],
        ["###", "#@#", "###"],
        ["###", "@$.", "##"],
        ["###", "@$.?", "###"],
        ["#########"] * 3,
        ["###"] * 9,
        ["#####", "#@$.#", "# $ #", "#####"],
        ["#####", "#@@.#", "# $ #", "#####"],
        ["#####", "#@$.#", "# . #", "#####"],
        [False, "#@$.#", "#####"],
    ],
)
def test_sokoban_rejects_unbounded_or_malformed_fixture(board):
    with pytest.raises(LabError, match="invalid_game_config"):
        SokobanEnvironment({"board": board})


def test_factory_case_contract_and_manifest_are_isolated():
    digest = manifest_hash()
    cases = list_cases()
    cases[0]["config"]["board"] = ["X"] * 9
    assert manifest_hash() == digest and len(digest) == 64
    assert CASES[0]["config"] == {}
    for game in ("tic_tac_toe", "nim", "memory", "sokoban"):
        env = make_environment(game, {}, 17)
        assert env.observation("A")["action_schema"]
        assert "legal_actions" not in env.observation("A", listed=False)
        with pytest.raises(LabError, match="invalid_game_player"):
            env.observation("C")
    for bad_seed in (-1, 2**32, True, 1.5):
        with pytest.raises(LabError, match="invalid_game_config"):
            make_environment("nim", {}, bad_seed)
    with pytest.raises(LabError, match="unsupported_game"):
        make_environment("chess", {}, 17)
    with pytest.raises(LabError, match="invalid_game_config"):
        make_environment("nim", None, 17)
