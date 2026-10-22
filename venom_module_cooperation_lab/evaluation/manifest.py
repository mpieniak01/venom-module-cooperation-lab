"""Versioned, small CPU-verifiable fixtures; never copy this into model input."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

SUITE_VERSION = "suite-v1"
RULESET_VERSION = "game-eval-v2"
CASES: list[dict[str, Any]] = [
    {
        "id": "ttt-opening-v1",
        "game": "tic_tac_toe",
        "config": {},
        "seed": 17,
        "max_actions": 9,
    },
    {
        "id": "ttt-win-v1",
        "game": "tic_tac_toe",
        "config": {"board": ["X", "X", "", "O", "O", "", "", "", ""]},
        "seed": 17,
        "max_actions": 5,
    },
    {
        "id": "ttt-block-v1",
        "game": "tic_tac_toe",
        "config": {"board": ["O", "O", "", "X", "", "", "", "X", ""]},
        "seed": 18,
        "max_actions": 5,
    },
    {
        "id": "ttt-fork-v1",
        "game": "tic_tac_toe",
        "config": {"board": ["X", "", "", "", "O", "", "", "", "X"]},
        "seed": 19,
        "max_actions": 6,
    },
    {
        "id": "nim-winning-v1",
        "game": "nim",
        "config": {"heaps": [3, 4, 5]},
        "seed": 17,
        "max_actions": 12,
    },
    {
        "id": "nim-last-stone-v1",
        "game": "nim",
        "config": {"heaps": [1]},
        "seed": 18,
        "max_actions": 1,
    },
    {
        "id": "nim-losing-v1",
        "game": "nim",
        "config": {"heaps": [1, 2, 3]},
        "seed": 19,
        "max_actions": 6,
    },
    {
        "id": "nim-two-ones-v1",
        "game": "nim",
        "config": {"heaps": [1, 1]},
        "seed": 20,
        "max_actions": 2,
    },
    {
        "id": "memory-seed17-v1",
        "game": "memory",
        "config": {"size": 4},
        "seed": 17,
        "max_actions": 64,
    },
    {
        "id": "memory-seed29-v1",
        "game": "memory",
        "config": {"size": 4},
        "seed": 29,
        "max_actions": 64,
    },
    {
        "id": "sokoban-push-v1",
        "game": "sokoban",
        "config": {"board": ["#####", "#@$.#", "#####"]},
        "seed": 17,
        "max_actions": 16,
    },
    {
        "id": "sokoban-turn-v1",
        "game": "sokoban",
        "config": {"board": ["######", "#    #", "# @$ #", "#  . #", "######"]},
        "seed": 18,
        "max_actions": 32,
    },
    {
        "id": "sokoban-route-v1",
        "game": "sokoban",
        "config": {
            "board": ["#######", "#     #", "# .$  #", "#  #@ #", "#     #", "#######"]
        },
        "seed": 19,
        "max_actions": 64,
    },
]


def list_cases() -> list[dict[str, Any]]:
    return copy.deepcopy(CASES)


def manifest_hash() -> str:
    data = {"suite": SUITE_VERSION, "ruleset": RULESET_VERSION, "cases": CASES}
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
