"""Live v3: model-selected tactical rules grounded in the player's own mistake.

The host validates a catalog policy, not the model's future compliance with it.
Legacy free-text note parsing and batch evaluation remain unchanged.
"""

from __future__ import annotations

import json
from typing import Any

from .evaluation.games import TicTacToeEnvironment
from .evaluation.references import _winning_squares, assess

RULES = {
    "win_now": (
        "Najpierw wykonaj ruch natychmiast wygrywający, "
        "nawet jeśli przeciwnik też grozi wygraną.",
        "Take an immediate winning move before blocking an opponent threat.",
    ),
    "block_win": (
        "Jeśli nie możesz wygrać teraz, zablokuj bezpośrednią wygraną przeciwnika.",
        "If you cannot win immediately, block the opponent's immediate winning move.",
    ),
}
VERSION = "tactical-rule-evidence-v1"


def _transform(
    board: list[str], square: str, rotation: int, mirror: bool
) -> tuple[list[str], str]:
    def index(i: int) -> int:
        r, c = divmod(i, 3)
        if mirror:
            c = 2 - c
        for _ in range(rotation):
            r, c = c, 2 - r
        return 3 * r + c

    result = [""] * 9
    for i, cell in enumerate(board):
        result[index(i)] = cell
    mapped = index((ord(square[0]) - 65) * 3 + int(square[1]) - 1)
    return result, "ABC"[mapped // 3] + str(mapped % 3 + 1)


def policy_actions(
    env: TicTacToeEnvironment, player: str, rule_id: str
) -> list[dict[str, str]]:
    board = tuple(env.board)
    mark = env.symbol(player)
    wins = _winning_squares(board, mark)
    threats = _winning_squares(board, "O" if mark == "X" else "X")
    if rule_id == "win_now":
        squares = wins
    elif rule_id == "block_win" and not wins and len(threats) == 1:
        squares = threats
    else:
        squares = set()
    return [{"square": "ABC"[i // 3] + str(i % 3 + 1)} for i in sorted(squares)]


def supported_rules(feedback: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Require a real tactical mistake and optimal policy on all D4 transforms."""
    supported: dict[str, dict[str, Any]] = {}
    for lesson in feedback["lessons"]:
        for rule_id in RULES:
            if rule_id in supported:
                continue
            checked = 0
            for mirror in (False, True):
                for rotation in range(4):
                    board, square = _transform(
                        lesson["board"],
                        lesson["model_action"]["square"],
                        rotation,
                        mirror,
                    )
                    env = TicTacToeEnvironment({"board": board})
                    score = assess(env, feedback["player"], {"square": square})
                    actions = policy_actions(env, feedback["player"], rule_id)
                    if (
                        (
                            score.get("worse_move")
                            or score.get("missed_win")
                            or score.get("missed_block")
                        )
                        and actions
                        and all(
                            assess(env, feedback["player"], action).get("optimal")
                            for action in actions
                        )
                        and {"square": square} not in actions
                    ):
                        checked += 1
            if checked == 8:
                supported[rule_id] = {
                    "version": VERSION,
                    "orientations_checked": checked,
                    "source_board": list(lesson["board"]),
                    "source_action": lesson["model_action"],
                    "scope": "catalog_policy_on_own_mistake_and_symmetries",
                    "future_model_behavior_verified": False,
                }
    return supported


def instruction(language: str | None) -> str:
    descriptions = "\n".join(
        key + ": " + text[0 if language == "pl" else 1] for key, text in RULES.items()
    )
    return (
        (
            "Wybierz jedną regułę z supported_rules pasującą do własnego błędu. "
            "Zwróć wyłącznie JSON z jednym polem rule_id. Nie wymyślaj nowej reguły.\n"
            if language == "pl"
            else "Select one rule from supported_rules "
            "that addresses your own mistake. "
            "Return only JSON with one field rule_id. Do not invent a new rule.\n"
        )
        + descriptions
        + '\nFormat examples:\n{"rule_id":"win_now"}\n{"rule_id":"block_win"}'
    )


def parse_choice(
    raw: str, supported: dict[str, dict[str, Any]]
) -> tuple[str | None, str]:
    text = raw.strip()
    if not text:
        return None, "empty_note"
    if len(text.encode()) > 8192:
        return None, "invalid_note_format"
    if text.startswith("<think>"):
        if "</think>" not in text:
            return None, "unfinished_note"
        text = text.split("</think>", 1)[1].strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    try:
        payload = json.loads(text, object_pairs_hook=pairs)
    except (ValueError, RecursionError):
        if text in RULES:
            payload = text
        else:
            return None, "invalid_note_format"
    if isinstance(payload, str):
        return (
            (payload, "evidence_checked_mapped")
            if payload in supported
            else (None, "unsupported_rule")
        )
    if (
        not isinstance(payload, dict)
        or set(payload) != {"rule_id"}
        or not isinstance(payload["rule_id"], str)
    ):
        return None, "invalid_note_format"
    rule_id = payload["rule_id"]
    if rule_id not in supported:
        return None, "unsupported_rule"
    return rule_id, "evidence_checked"


def rule_text(rule_id: str, language: str | None) -> str:
    return RULES[rule_id][0 if language == "pl" else 1]
