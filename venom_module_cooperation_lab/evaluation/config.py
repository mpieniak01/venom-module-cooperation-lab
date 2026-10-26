"""Explicit v2 experiment configuration and deterministic episode planning."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..errors import LabError
from ..model_limits import MAX_REQUESTED_TOKENS


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model_id: str = Field(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$"
    )
    case_ids: list[str] = Field(min_length=1, max_length=32)
    repetitions: int = Field(default=1, ge=1, le=10)
    observation_mode: Literal["history_replay", "native_incremental"] = "history_replay"
    episode_memory: Literal["fresh", "carry"] = "fresh"
    reflection: Literal["off", "episode_note"] = "off"
    ttt_variant: Literal["standard", "reflection", "assisted"] = "standard"
    decoding: Literal["greedy", "sampled"] = "greedy"
    temperature: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)
    top_p: float = Field(default=0.9, gt=0, le=1, allow_inf_nan=False)
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    num_steps: Literal[8, 16, 32, 64] = 8
    legal_moves: Literal["hidden", "listed"] = "listed"
    action_constraint: Literal["none", "masked"] = "none"
    response_mode: Literal["strict_json", "mapped"] = "strict_json"
    opponent: Literal["optimal", "random", "remembering", "model"] = "optimal"
    swap_sides: bool = True
    max_new_tokens: int = Field(default=128, ge=8, le=MAX_REQUESTED_TOKENS)
    decision_timeout_s: int = Field(default=30, ge=1, le=300)
    max_context_tokens: int = Field(default=2048, ge=128, le=16384)

    @model_validator(mode="after")
    def valid(self) -> EvaluationRequest:
        if len(set(self.case_ids)) != len(self.case_ids):
            raise ValueError("duplicate_cases")
        if self.decoding == "sampled" and self.temperature <= 0:
            raise ValueError("sampled_requires_temperature")
        return self


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def seeded(*parts: Any) -> int:
    return int(digest(parts)[:8], 16) % (2**31)


def plan(
    request: EvaluationRequest, cases: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    indexed = {c["id"]: c for c in cases}
    if any(cid not in indexed for cid in request.case_ids):
        raise LabError("unknown_case", 422)
    items: list[dict[str, Any]] = []
    for cid in request.case_ids:
        c = indexed[cid]
        sides = (
            ["A", "B"]
            if request.swap_sides and c["game"] in {"tic_tac_toe", "nim"}
            else ["A"]
        )
        for side in sides:
            for rep in range(request.repetitions):
                index = len(items)
                block = (
                    (c["game"] + ":" + side)
                    if request.episode_memory == "carry"
                    else str(index)
                )
                items.append(
                    {
                        "index": index,
                        "case_id": cid,
                        "game": c["game"],
                        "episode": rep + 1,
                        "block_id": block,
                        "attempt": 1,
                        "player": side,
                        "seed": seeded(request.seed, c["seed"], cid, rep),
                        "max_actions": c["max_actions"],
                        "status": "pending",
                        "reason_code": None,
                        "result": None,
                        "decisions": [],
                        "started_at": None,
                        "ended_at": None,
                    }
                )
    if len(items) > 128 or sum(i["max_actions"] for i in items) > 384:
        raise LabError("evaluation_plan_too_large", 422)
    # Stable contiguous blocks, otherwise a later case could inherit another side.
    return sorted(items, key=lambda v: (v["block_id"], v["index"]))
