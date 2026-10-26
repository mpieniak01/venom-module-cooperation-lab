"""Bounded final-note contract; rejected model text never becomes memory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReflectionNote:
    accepted: bool
    reason: str
    rule: str = ""


def validate_note(raw: str, instruction: str) -> ReflectionNote:
    text = raw.strip()
    if not text:
        return ReflectionNote(False, "empty_note")
    if len(text.encode()) > 8192:
        return ReflectionNote(False, "invalid_note_format")
    # Only a completed reasoning envelope may precede a final answer.
    if text.startswith("<think>"):
        end = text.find("</think>")
        if end < 0:
            return ReflectionNote(False, "unfinished_note")
        text = text[end + len("</think>") :].strip()
    if "<think>" in text or "</think>" in text:
        return ReflectionNote(False, "unfinished_note")
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        payload = None
    if isinstance(payload, dict) and set(payload) == {"rule"}:
        rule = payload["rule"]
    elif text.upper().startswith(("RULE:", "ZASADA:")):
        rule = text.split(":", 1)[1].strip()
        if not rule.endswith((".", "!", "?")):
            return ReflectionNote(False, "unfinished_note")
    else:
        normalized = " ".join(text.casefold().split())
        prompt = " ".join(instruction.casefold().split())
        reason = (
            "instruction_echo"
            if len(normalized) >= 20 and normalized in prompt
            else "invalid_note_format"
        )
        return ReflectionNote(False, reason)
    if not isinstance(rule, str):
        return ReflectionNote(False, "invalid_note_format")
    rule = " ".join(rule.split())
    if not 20 <= len(rule) <= 280 or len(rule.split()) < 3:
        return ReflectionNote(False, "invalid_note_format")
    normalized = rule.casefold()
    prompt = " ".join(instruction.casefold().split())
    if normalized in prompt or any(
        " ".join(normalized.split()[i : i + 8]) in prompt
        for i in range(max(0, len(normalized.split()) - 7))
    ):
        return ReflectionNote(False, "instruction_echo")
    if any(marker in rule for marker in ("<", ">", "```", "{", "}")):
        return ReflectionNote(False, "invalid_note_format")
    if re.search(r"\b[ABC][123]\b", rule, re.IGNORECASE):
        return ReflectionNote(False, "position_specific_note")
    return ReflectionNote(True, "accepted", rule)
