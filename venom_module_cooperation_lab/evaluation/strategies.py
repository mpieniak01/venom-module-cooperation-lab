"""Explicit TTT coaching; model proposals remain independently scored."""

from __future__ import annotations

import copy
import random
from typing import Any

from .games import Environment
from .references import assess, reference_action

STRATEGY_VERSION = "ttt-coaching-v1"


def strategy_action(
    env: Environment,
    player: str,
    action: dict[str, Any],
    assessment: dict[str, Any],
    record: dict[str, Any],
    variant: str,
    seed: int,
) -> dict[str, Any]:
    if variant == "standard" or not assessment.get("legal"):
        return action
    record["model_action"] = copy.deepcopy(action)
    if assessment["worse_move"]:
        better = reference_action(env, "optimal", random.Random(seed))
        if variant == "reflection":
            # Kept in the journal until the episode ends, never a live hint.
            record["lesson"] = {
                "board": env.public_state()["board"],
                "model_action": copy.deepcopy(action),
                "better_action": better,
                "assessment": copy.deepcopy(assessment),
            }
        else:
            action = better
    if variant == "assisted":
        record["assistance"] = {
            "version": STRATEGY_VERSION,
            "applied": action != record["model_action"],
            "source": "minimax",
        }
        record["execution_assessment"] = assess(env, player, action)
    return action


def lessons_for(item: dict[str, Any], player: str) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(d["lesson"])
        for d in item["decisions"]
        if d.get("actor") == "model" and d["player"] == player and "lesson" in d
    ][-3:]
