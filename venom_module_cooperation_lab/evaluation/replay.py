"""Offline replay from an exported manifest and validated actions, without models."""

from __future__ import annotations

from typing import Any

from ..errors import LabError
from .games import make_environment


def replay_episode(snapshot: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
    cases = snapshot["config"]["cases"]
    case = next((c for c in cases if c["id"] == item["case_id"]), None)
    if case is None:
        raise LabError("replay_case_missing", 422)
    env = make_environment(case["game"], case["config"], item["seed"])
    count = 0
    for decision in item["decisions"]:
        if decision.get("purpose", "action") != "action" or not decision["valid"]:
            continue
        env.step(decision["player"], decision["action"])
        count += 1
    result = env.result()
    config = snapshot["config"]
    if env.game in {"tic_tac_toe", "nim"} and config["opponent"] != "model":
        result["success"] = result.get("winner") == item["player"]
    expected = item.get("result")
    if expected is not None and result != expected:
        raise LabError("replay_result_mismatch", 422)
    return {"state": env.public_state(), "result": result, "actions": count}
