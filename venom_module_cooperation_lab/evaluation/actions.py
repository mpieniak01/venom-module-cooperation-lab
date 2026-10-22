"""Versioned, deterministic action mapping; never selects or repairs a move."""

from __future__ import annotations

import json
import re
from typing import Any

from ..errors import LabError

VERSION = "action-map-v2"


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _json(text: str) -> Any:
    value = json.loads(text, object_pairs_hook=_pairs)
    # Non-finite numbers are never valid game actions.
    json.dumps(value, allow_nan=False)
    return value


def _unwrap(text: str) -> str:
    text = text.strip()
    if text.startswith("<think>"):
        end = text.find("</think>")
        if end < 0:
            raise ValueError("unfinished_reasoning")
        text = text[end + len("</think>") :].strip()
    text = re.sub(
        r"^(?:final answer|answer|odpowiedź|action):\s*", "", text, flags=re.I
    )
    fence = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    return fence[1].strip() if fence else text


def _object(game: str, action: dict[str, Any]) -> tuple[dict[str, Any], str]:
    keys = set(action)
    if game == "sokoban":
        if keys == {"move"}:
            return action, "json"
        if (
            keys in ({"action", "move"}, {"action", "value"})
            and action["action"] == "move"
        ):
            return {"move": action.get("move", action.get("value"))}, "move_envelope"
    if game == "nim":
        if keys == {"heap", "count"}:
            return {"heap": action["heap"], "take": action["count"]}, "nim_count"
        if keys in ({"action", "heap", "take"}, {"action", "heap", "count"}) and action[
            "action"
        ] in {"take", "remove"}:
            return {
                "heap": action["heap"],
                "take": action.get("take", action.get("count")),
            }, "nim_envelope"
    if game == "memory":
        if keys == {"card1", "card2"}:
            return {"cards": [action["card1"], action["card2"]]}, "memory_pair"
        if keys == {"action", "cards"} and action["action"] in {
            "reveal",
            "match",
            "flip",
        }:
            return {"cards": action["cards"]}, "memory_envelope"
    return action, "json"


def _plain(game: str, text: str) -> dict[str, Any]:
    if game == "sokoban":
        match = re.fullmatch(r"(?:move\s+)?(up|down|left|right)[.!]?", text, re.I)
        if match:
            return {"move": match[1].lower()}
    elif game == "nim":
        compact = re.fullmatch(r"heap\s*=\s*(\d+)\s+take\s*=\s*(\d+)[.!]?", text, re.I)
        if compact:
            return {"heap": int(compact[1]), "take": int(compact[2])}
        match = re.fullmatch(
            r"take\s+(\d+)\s+stones?\s+from\s+heap\s+(\d+)[.!]?", text, re.I
        )
        if match:
            return {"heap": int(match[2]), "take": int(match[1])}
    elif game == "memory":
        match = re.fullmatch(
            r"(?:cards?|reveal|flip|match)\s*[:=]?\s*(\d+)\s*(?:,|and)\s*(\d+)[.!]?",
            text,
            re.I,
        )
        if match:
            return {"cards": [int(match[1]), int(match[2])]}
    elif game == "tic_tac_toe":
        match = re.fullmatch(r"(?:move\s+)?([ABC][123])[.!]?", text, re.I)
        if match:
            return {"square": match[1].upper()}
    raise ValueError("ambiguous_or_missing_action")


def parse_action(
    text: str, game: str, mode: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map one explicit answer only. The environment still validates legality."""
    try:
        if mode == "strict_json":
            # Keep the historical v2 parser unchanged, including duplicate-key handling.
            value = json.loads(
                text, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v))
            )
            if not isinstance(value, dict):
                raise ValueError("object_required")
            return value, {"version": "strict-json-v2", "mapped": False, "rule": "json"}
        if mode != "mapped":
            raise ValueError("unknown_mode")
        cleaned = _unwrap(text)
        try:
            action = _json(cleaned)
        except json.JSONDecodeError:
            action = _plain(game, cleaned)
            rule = "explicit_text"
        else:
            if isinstance(action, list) and game == "memory" and len(action) == 2:
                action, rule = {"cards": action}, "memory_pair_array"
            elif isinstance(action, dict):
                action, rule = _object(game, action)
            else:
                raise ValueError("object_required")
        mapped = rule != "json" or cleaned != text.strip()
        return action, {"version": VERSION, "mapped": mapped, "rule": rule}
    except (ValueError, TypeError, RecursionError):
        raise LabError("invalid_format", 422) from None
