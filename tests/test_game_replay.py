import copy

import pytest
from pydantic import ValidationError

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.config import (
    EvaluationRequest,
    plan,
    seeded,
)
from venom_module_cooperation_lab.evaluation.manifest import CASES
from venom_module_cooperation_lab.evaluation.replay import replay_episode


def test_planning_reproducible_bounded_and_isolated():
    request = EvaluationRequest(
        model_id="rwkv7",
        case_ids=["nim-last-stone-v1"],
        repetitions=3,
        episode_memory="carry",
    )
    rows = plan(request, CASES)
    assert rows == plan(request.model_copy(update={"model_id": "huginn"}), CASES)
    assert len(rows) == 6
    assert {r["player"] for r in rows} == {"A", "B"}
    assert len({r["seed"] for r in rows}) == 3
    assert len({r["block_id"] for r in rows}) == 2
    assert seeded(1, "a") != seeded(1, "b")
    with pytest.raises(LabError, match="unknown_case"):
        plan(request.model_copy(update={"case_ids": ["absent"]}), CASES)
    with pytest.raises(LabError, match="evaluation_plan_too_large"):
        plan(
            request.model_copy(
                update={"case_ids": [c["id"] for c in CASES], "repetitions": 10}
            ),
            CASES,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"case_ids": ["x", "x"]},
        {"decoding": "sampled", "temperature": 0.0},
        {"temperature": float("nan")},
        {"repetitions": True},
        {"unknown": 2},
    ],
)
def test_strict_game_request(changes):
    with pytest.raises(ValidationError):
        EvaluationRequest(
            **{"model_id": "test", "case_ids": ["nim-last-stone-v1"], **changes}
        )


def test_offline_replay_validated_actions_only_and_detects_tamper():
    snapshot = {"config": {"cases": CASES, "opponent": "optimal"}}
    item = {
        "case_id": "nim-last-stone-v1",
        "seed": 3,
        "player": "A",
        "result": None,
        "decisions": [
            {"valid": True, "player": "A", "action": {"heap": 0, "take": 1}},
            {"valid": True, "purpose": "reflection", "action": None},
            {"valid": False, "action": {"heap": 9, "take": 2}},
        ],
    }
    first = replay_episode(snapshot, item)
    assert first["result"]["success"] and first["actions"] == 1
    item["result"] = first["result"]
    assert replay_episode(snapshot, item) == first
    bad = copy.deepcopy(item)
    bad["result"]["success"] = False
    with pytest.raises(LabError, match="replay_result_mismatch"):
        replay_episode(snapshot, bad)
    with pytest.raises(LabError, match="replay_case_missing"):
        replay_episode(snapshot, {**item, "case_id": "absent"})


@pytest.mark.parametrize(
    "cid", ["ttt-win-v1", "nim-last-stone-v1", "memory-seed17-v1", "sokoban-turn-v1"]
)
def test_reference_transcripts_replay_each_game_without_a_model(cid):
    import random

    from venom_module_cooperation_lab.evaluation.games import make_environment
    from venom_module_cooperation_lab.evaluation.references import reference_action

    case = next(c for c in CASES if c["id"] == cid)
    env = make_environment(case["game"], case["config"], case["seed"])
    item = {"case_id": cid, "seed": case["seed"], "player": "A", "decisions": []}
    for _ in range(128):
        if env.finished:
            break
        player = env.current_player
        opponent = "remembering" if env.game == "memory" else "optimal"
        action = reference_action(env, opponent, random.Random(17))
        env.step(player, action)
        item["decisions"].append({"player": player, "action": action, "valid": True})
    assert env.finished
    result = env.result()
    if env.game in {"tic_tac_toe", "nim"}:
        result["success"] = result["winner"] == "A"
    item["result"] = result
    snapshot = {"config": {"cases": CASES, "opponent": "optimal"}}
    replayed = replay_episode(snapshot, item)
    assert replayed["result"] == result
    assert replayed["state"] == env.public_state()
