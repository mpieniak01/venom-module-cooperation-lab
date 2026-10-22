"""No hidden card/oracle leakage and no mutation through public observations."""

from __future__ import annotations

import random

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.games import (
    MemoryEnvironment,
    make_environment,
    state_digest,
)
from venom_module_cooperation_lab.evaluation.references import reference_action


def test_hidden_deck_never_appears_in_model_or_operator_observations():
    env = MemoryEnvironment({}, 17)
    first = env.observation("A")
    assert first["board"] == [None] * 16 and first["last_reveal"] == []
    assert "_cards" not in first and "revealed_knowledge" not in first
    assert "known_pairs" not in first and "reference" not in first
    env.step("A", {"cards": [0, 1]})
    visible = env.observation("A")
    assert visible["last_reveal"] == [
        {"card": i, "value": env._cards[i]} for i in (0, 1)
    ]
    for index, value in enumerate(visible["board"]):
        assert value == (env._cards[index] if index in env.matched else None)
    env.step("A", {"cards": [2, 3]})
    assert [item["card"] for item in env.public_state()["last_reveal"]] == [2, 3]
    assert 0 in env.revealed_knowledge and 1 in env.revealed_knowledge
    assert "knowledge" not in env.public_state()
    assert "known_pairs_missed" not in env.public_state()["result"]


def test_memory_reference_is_invariant_to_permutation_of_unseen_cards():
    first = MemoryEnvironment({}, 17)
    second = MemoryEnvironment({}, 29)
    # First observation contains no card identities: the reference cannot peek.
    assert reference_action(first, "remembering", random.Random(1)) == reference_action(
        second, "remembering", random.Random(1)
    )
    for env in (first, second):
        env.step("A", {"cards": [0, 1]})
    # Give the same public evidence but permute the still-hidden deck.
    second._cards[0:2] = first._cards[0:2]
    second.revealed_knowledge = dict(first.revealed_knowledge)
    assert reference_action(first, "remembering", random.Random(3)) == reference_action(
        second, "remembering", random.Random(3)
    )


def test_observation_copies_do_not_mutate_engine_or_leak_a_second_player():
    for game in ("tic_tac_toe", "nim", "memory", "sokoban"):
        env = make_environment(game, {}, 17)
        before = state_digest(env)
        visible = env.observation("A")
        visible["result"]["winner"] = "B"
        visible["legal_actions"].clear()
        if "board" in visible:
            visible["board"].clear()
        if "heaps" in visible:
            visible["heaps"].clear()
        assert state_digest(env) == before
        if game in {"memory", "sokoban"}:
            with pytest.raises(LabError, match="invalid_game_player"):
                env.observation("B")


def test_seed_is_local_and_never_changes_global_rng():
    state = random.getstate()
    first = MemoryEnvironment({}, 17)
    second = MemoryEnvironment({}, 17)
    assert first._cards == second._cards
    assert first.deck_id == second.deck_id
    assert random.getstate() == state
