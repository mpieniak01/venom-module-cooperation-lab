from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace

import pytest
from conftest import SPEC

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.experiments import (
    RUBRICS,
    aggregate,
    build_plan,
    evaluate_export,
)
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER


def exported(scenario="split_facts", mode="dialog_encouraged", answers=("R", "RK")):
    config = RunConfig.build(
        RunRequest(
            model_id=SPEC.model_id,
            scenario_id=scenario,
            mode=mode,
            max_turns=4,
            max_new_tokens=32,
        ),
        asdict(SPEC),
    ).public()
    events = []

    def emit(kind, payload):
        event = {
            "run_id": "run1",
            "seq": len(events) + 1,
            "timestamp": 100 + len(events) * 0.1,
            "kind": kind,
            "payload": payload,
        }
        events.append(event)
        return event

    emit(
        "run",
        {
            "status": "preparing",
            "runtime_receipt": {
                "load_s": 0.1,
                "device": "fixture_cpu",
                "precision": "fixture",
                "model_path": "/private/path",
            },
        },
    )
    previous = None
    for index, answer in enumerate(answers):
        sender = "A" if mode in {"single", "self_correction"} else ("A", "B")[index % 2]
        recipient = "B" if sender == "A" else "A"
        emit("turn", {"participant_id": sender, "status": "generating"})
        emit(
            "usage",
            {
                "input_tokens": 20,
                "output_tokens": 8,
                "charged_input_tokens": 20,
                "charged_output_tokens": 8,
                "generation_s": 0.3,
                "ttft_s": 0.05,
            },
        )
        message = {
            "schema_version": 1,
            "run_id": "run1",
            "sequence": len(events) + 1,
            "message_id": f"message{index}",
            "sender": sender,
            "recipient": recipient,
            "kind": "message",
            "content": answer,
            "delivered_to": [recipient] if mode.startswith("dialog") else [],
            "in_reply_to": previous if mode.startswith("dialog") else None,
            "reply_source": "host_context",
        }
        emit("message", message)
        previous = message["message_id"]
    emit("end", {"status": "completed", "quiescent": True})
    return {
        "schema_version": 1,
        "run": {
            "id": "run1",
            "status": "completed",
            "last_seq": len(events),
            "config": config,
        },
        "events": events,
    }


def test_small_frozen_plan_is_bounded_and_does_not_start_models():
    assert len(build_plan()) == 2
    full = build_plan(matrix=True)
    assert len(full) == 30
    assert all(
        item["max_turns"] == 4
        and item["max_new_tokens"] == 32
        and item["temperature"] == 0
        for item in full
    )
    for kwargs in (
        {"max_turns": 8},
        {"max_new_tokens": 33},
        {"seed": True},
        {"model_ids": []},
        {"model_ids": ["remote"]},
    ):
        with pytest.raises(LabError):
            build_plan(**kwargs)


@pytest.mark.parametrize(
    "scenario,answer",
    [("split_facts", "RK"), ("organization", "42"), ("correction", "42")],
)
def test_ground_truth_is_independent_of_consensus(scenario, answer):
    data = exported(scenario, answers=(answer, answer))
    report = evaluate_export(data)
    assert report["task_success"] is True
    assert report["technical_completion_confirmed"] is True
    assert report["input_partition_verified"] is True
    assert report["communication_observed"] is True
    assert report["usage"]["input_tokens"] == 40
    assert report["runtime"]["device"] == "fixture_cpu"
    assert "/private/path" not in json.dumps(report)
    assert report["organization"]["commitment_execution"] == "unscorable"
    assert report["quality_gain_claim"] is False


@pytest.mark.parametrize(
    "content,outcome",
    [
        ("41", "incorrect"),
        ("The sum is 42.", "correct"),
        ("17 + 25 = 42", "correct"),
        ('{"answer":42}', "correct"),
        ("We agree: 41 or 42", "unscorable"),
        ("Final: 41\nFinal: 42", "unscorable"),
        ("Discussion 41\nFinal answer: 42", "correct"),
        ('{"answer":42,"explanation":"not frozen"}', "unscorable"),
        ("{broken", "unscorable"),
        ("I think 42", "unscorable"),
    ],
)
def test_strict_answers_do_not_select_best_fragment(content, outcome):
    result = evaluate_export(exported("correction", answers=(content,)))
    assert result["task_outcome"] == outcome
    assert result["task_success"] is (
        True if outcome == "correct" else False if outcome == "incorrect" else None
    )


def test_no_contact_and_privileged_controls_are_explicit():
    for mode in ("single", "self_correction", "no_contact"):
        result = evaluate_export(exported(mode=mode, answers=("RK",)))
        assert result["task_success"] is True
        assert not result["communication_observed"]
        assert result["information"] == (
            "partitioned" if mode == "no_contact" else "privileged_full_information"
        )


def test_proposal_accept_are_declarations_and_delivery_requires_later_turn():
    data = exported(answers=("R", "RK"))
    messages = [event for event in data["events"] if event["kind"] == "message"]
    messages[0]["payload"]["kind"] = "proposal"
    messages[1]["payload"].update(kind="accept", reply_source="model")
    result = evaluate_export(data)
    assert result["organization"]["proposals_declared"] == 1
    assert result["organization"]["acceptances_declared"] == 1
    assert result["organization"]["explicit_acceptance_links"] == 1
    proof = result["peer_deliveries"][0]
    assert proof["source_seq"] < proof["recipient_turn_seq"] < proof["reply_seq"]
    assert result["organization"]["commitment_execution"] == "unscorable"
    # A final outgoing message with no recipient turn is not consumed evidence.
    assert result["peer_deliveries"][-1]["host_context_consumed"] is False


def test_unknown_usage_is_not_zero_and_charged_is_preserved():
    data = exported()
    usage = next(
        event["payload"] for event in data["events"] if event["kind"] == "usage"
    )
    usage["input_tokens"], usage["output_tokens"] = None, None
    result = evaluate_export(data)
    assert result["usage"]["input_tokens"] is None
    assert result["usage"]["output_tokens"] is None
    assert result["usage"]["charged_input_tokens"] == 40


def test_unsupported_input_partition_or_failed_run_is_unscorable():
    data = exported(answers=("RK",))
    data["run"]["config"]["prompts"] = []
    assert evaluate_export(data)["task_success"] is None
    data = exported(answers=("RK",))
    data["run"]["status"] = "failed"
    assert evaluate_export(data)["scoring_reason"] == "run_not_completed"
    data["run"]["config"]["scenario_version"] = "2"
    with pytest.raises(LabError, match="unsupported_experiment_version"):
        evaluate_export(data)


def test_event_deduplication_conflict_gaps_and_huge_sequence_are_bounded():
    data = exported()
    data["events"].append(copy.deepcopy(data["events"][-1]))
    assert evaluate_export(data)["usage"]["turns"] == 2
    data["events"][-1]["payload"]["status"] = "failed"
    with pytest.raises(LabError, match="conflicting_experiment_event"):
        evaluate_export(data)
    data = exported()
    data["events"][-1]["seq"] = 2**60
    with pytest.raises(LabError, match="incomplete_experiment_events"):
        evaluate_export(data)


@pytest.mark.parametrize(
    "location,value",
    [
        ("run_id", "other"),
        ("seq", 0),
        ("timestamp", float("nan")),
        ("payload", []),
        ("kind", None),
    ],
)
def test_malformed_events_are_explicit(location, value):
    data = exported()
    data["events"][0][location] = value
    with pytest.raises(LabError):
        evaluate_export(data)


@pytest.mark.parametrize(
    "location,value",
    [
        ("sender", "C"),
        ("sequence", 10),
        ("message_id", "../secret"),
        ("content", 5),
        ("delivered_to", ["A"]),
        ("in_reply_to", "unknown"),
    ],
)
def test_invalid_identity_or_delivery_not_scored(location, value):
    data = exported()
    message = next(
        event["payload"] for event in data["events"] if event["kind"] == "message"
    )
    message[location] = value
    with pytest.raises(LabError):
        evaluate_export(data)


def test_invalid_usage_and_missing_journal():
    data = exported()
    usage = next(
        event["payload"] for event in data["events"] if event["kind"] == "usage"
    )
    usage["charged_input_tokens"] = 1
    with pytest.raises(LabError, match="invalid_experiment_usage"):
        evaluate_export(data)
    data = exported()
    data["events"], data["run"]["last_seq"] = [], 0
    result = evaluate_export(data)
    assert result["task_success"] is None and result["quiescent"] is None
    assert result["usage"]["input_tokens"] is None


def test_aggregate_does_not_assert_improvement():
    records = [
        evaluate_export(exported(mode=mode, answers=("RK",)))
        for mode in ("single", "dialog")
    ]
    result = aggregate(records)
    assert result["runs"] == 2 and not result["quality_gain_claim"]
    assert result["by_mode"]["single"]["correct"] == 1
    with pytest.raises(LabError):
        aggregate(records * 16)


def test_rubric_is_not_read_from_runner_expected(monkeypatch):
    from venom_module_cooperation_lab import scenarios

    monkeypatch.setattr(
        scenarios,
        "SCENARIOS",
        tuple(replace(item, expected="WRONG") for item in scenarios.SCENARIOS),
    )
    assert RUBRICS[0].expected == "RK"
    assert evaluate_export(exported(answers=("RK",)))["task_success"] is True


@pytest.mark.asyncio
async def test_real_runner_export_contract_without_real_inference(rig):
    import asyncio

    runner, adapters = rig
    factory = runner.adapter_factory

    def controlled(model, lease):
        adapter = factory(model, lease)
        adapter.responses = ["R", "RK"]
        return adapter

    runner.adapter_factory = controlled
    row, created = await runner.start(
        RunRequest(
            model_id=SPEC.model_id,
            scenario_id="split_facts",
            max_turns=2,
            max_new_tokens=32,
        ),
        "l5-contract",
    )
    assert created
    await asyncio.wait_for(asyncio.shield(runner.jobs[row["id"]].task), 2)
    report = evaluate_export(
        json.loads(runner.store.export_run(row["id"], owner=OWNER))
    )
    assert report["task_success"] and report["communication_observed"]
    assert report["quiescent"] is True
