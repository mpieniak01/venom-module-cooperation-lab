from __future__ import annotations

import asyncio
import json
import time

import pytest
from conftest import SPEC
from pydantic import ValidationError

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER


def request(**values):
    return RunRequest(
        model_id=SPEC.model_id,
        scenario_id="operator_conversation",
        communication_language="pl",
        mode="operator_chat",
        **values,
    )


async def waiting(runner, row, count=0):
    job = runner.jobs[row["id"]]
    async with asyncio.timeout(2):
        while not job.operator_waiting or len(job.operator_submissions) != count:
            await asyncio.sleep(0.001)
    return job


async def finish(runner, row):
    await asyncio.wait_for(asyncio.shield(runner.jobs[row["id"]].task), 2)
    return runner.snapshot(row["id"])["run"]


def test_operator_config_is_separate_bounded_and_not_a_frozen_benchmark():
    config = RunConfig.build(request(), {})
    assert config.schema_version == 3 and config.participant_count == 3
    assert config.scheduler == "operator-rounds-v1"
    assert config.budgets.wall_seconds == 360
    assert "trzecim uczestnikiem" in config.prompts[0]
    english = RunConfig.build(
        request().model_copy(update={"communication_language": "en"}), {}
    )
    assert "third participant" in english.prompts[1]
    for values in ({"max_turns": 1}, {"max_turns": 3}, {"max_turns": 9}):
        with pytest.raises(ValidationError):
            request(**values)
    with pytest.raises(ValidationError):
        RunRequest(
            model_id=SPEC.model_id, scenario_id="tic_tac_toe", mode="operator_chat"
        )


@pytest.mark.asyncio
async def test_both_models_receive_each_operator_prompt_exactly_once_and_replay(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(max_turns=4), "operator")
    job = await waiting(runner, row)
    assert not adapters[0].recorded
    first = runner.operator_message(row["id"], "Pierwsze pytanie", "first")
    assert first["created"] and first["event"]["payload"]["delivered_to"] == ["A", "B"]
    retry = runner.operator_message(row["id"], "Pierwsze pytanie", "first")
    assert retry == {"event": first["event"], "created": False}
    with pytest.raises(LabError, match="idempotency_conflict"):
        runner.operator_message(row["id"], "Inne pytanie", "first")
    await waiting(runner, row, 1)
    assert len(adapters[0].recorded) == 2
    runner.operator_message(row["id"], "Drugie pytanie", "second")
    assert (await finish(runner, row))["status"] == "completed"
    assert [part for part, _, _ in adapters[0].recorded] == ["A", "B", "A", "B"]
    for index, (_, history, _) in enumerate(adapters[0].recorded):
        assert sum("Pierwsze pytanie" in item.content for item in history) == 1
        assert sum("Drugie pytanie" in item.content for item in history) == int(
            index >= 2
        )
    events = runner.store.events(row["id"], owner=OWNER)
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    assert len(messages) == 6 and messages[0]["sender"] == "operator"
    assert all(
        m["recipient"] == "operator" and m["delivered_to"] == ["operator"]
        for m in messages
        if m["sender"] != "operator"
    )
    assert (
        messages[1]["operator_message_id"]
        == messages[2]["operator_message_id"]
        == messages[0]["message_id"]
    )
    assert messages[1]["in_reply_to"] == messages[0]["message_id"]
    assert messages[2]["in_reply_to"] == messages[0]["message_id"]
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert b"operator" in runner.store.export_run(row["id"], owner=OWNER)
    assert job.histories == {} and runner.admission.snapshot()["status"] == "available"
    assert not runner.operator_message(row["id"], "Pierwsze pytanie", "first")[
        "created"
    ]
    with pytest.raises(LabError, match="operator_chat_not_waiting"):
        runner.operator_message(row["id"], "Too late", "third")


@pytest.mark.asyncio
async def test_operator_can_stop_while_waiting_without_generation(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(), "waiting-stop")
    await waiting(runner, row)
    await runner.cancel(row["id"])
    assert (await finish(runner, row))["status"] == "cancelled"
    assert not adapters[0].recorded
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_idle_operator_wait_keeps_deadline(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(), "deadline")
    job = await waiting(runner, row)
    job.deadline = time.monotonic() - 1
    assert (await finish(runner, row))["status"] == "failed"
    assert job.failure == "run_deadline_exceeded" and not adapters[0].recorded
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_busy_cancelled_unavailable_and_missing_run_input(rig):
    runner, adapters = rig
    with pytest.raises(LabError, match="run_not_found"):
        runner.operator_message("missing", "test", "x")
    row, _ = await runner.start(request(), "busy")
    with pytest.raises(LabError, match="operator_chat_not_waiting"):
        runner.operator_message(row["id"], "Too early", "early")
    await waiting(runner, row)
    adapters[0].block = True
    runner.operator_message(row["id"], "Pytanie", "question")
    with pytest.raises(LabError, match="operator_chat_not_waiting"):
        runner.operator_message(row["id"], "Next", "next")
    await runner.cancel(row["id"])
    assert (await finish(runner, row))["status"] == "cancelled"
    with pytest.raises(LabError, match="run_cancelled"):
        runner.operator_message(row["id"], "Next", "next")
    other, _ = await runner.start(
        request().model_copy(update={"mode": "dialog"}), "other"
    )
    with pytest.raises(LabError, match="operator_chat_unavailable"):
        runner.operator_message(other["id"], "Not a manual run", "manual")
    await finish(runner, other)


@pytest.mark.asyncio
async def test_structured_models_can_address_operator_and_peer(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(max_turns=2), "structured")
    await waiting(runner, row)
    adapters[0].responses = [
        '{"kind":"message","recipient":"all","content":"Plan A"}',
        '{"kind":"complete","recipient":"operator","content":"Plan B"}',
    ]
    runner.operator_message(row["id"], "Uzgodnijcie plan", "plan")
    assert (await finish(runner, row))["status"] == "completed"
    assert "Plan A" in adapters[0].recorded[1][1][-1].content
    messages = [
        e["payload"]
        for e in runner.store.events(row["id"], owner=OWNER)
        if e["kind"] == "message"
    ]
    assert messages[1]["delivered_to"] == ["B", "operator"]
    assert messages[2]["delivered_to"] == ["operator"]


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en"])
async def test_telephone_only_a_receives_original_b_receives_a_retelling(rig, language):
    runner, adapters = rig
    config = request(max_turns=4).model_copy(
        update={"mode": "operator_relay", "communication_language": language}
    )
    row, _ = await runner.start(config, "telephone")
    assert row["config"]["scheduler"] == "operator-relay-v1"
    await waiting(runner, row)
    adapters[0].responses = [
        "Retold by A one",
        "Retold by B one",
        "Retold by A two",
        "Retold by B two",
    ]
    runner.operator_message(row["id"], "SECRET ORIGINAL ONE", "story1")
    await waiting(runner, row, 1)
    runner.operator_message(row["id"], "SECRET ORIGINAL TWO", "story2")
    assert (await finish(runner, row))["status"] == "completed"
    for participant, history, _ in adapters[0].recorded:
        content = "\n".join(item.content for item in history)
        if participant == "A":
            assert "SECRET ORIGINAL ONE" in content
        else:
            assert "SECRET ORIGINAL" not in content
            assert "Retold by A" in content
    messages = [
        e["payload"]
        for e in runner.store.events(row["id"], owner=OWNER)
        if e["kind"] == "message"
    ]
    assert [m["sender"] for m in messages] == [
        "operator",
        "A",
        "B",
        "operator",
        "A",
        "B",
    ]
    assert [m["delivered_to"] for m in messages] == [
        ["A"],
        ["B"],
        ["operator"],
        ["A"],
        ["B"],
        ["operator"],
    ]
    assert messages[2]["in_reply_to"] == messages[1]["message_id"]
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_operator_retry_survives_pruned_job_and_storage_restart(rig):
    runner, _ = rig
    row, _ = await runner.start(request(max_turns=2), "durable-operator-run")
    await waiting(runner, row)
    original = runner.operator_message(row["id"], "Trwały wpis", "durable-message-key")
    await finish(runner, row)
    runner.jobs.clear()
    runner.store.close()
    runner.store.open()
    replay = runner.operator_message(row["id"], "Trwały wpis", "durable-message-key")
    assert replay == {"event": original["event"], "created": False}
    assert "durable-message-key" not in json.dumps(original)
    with pytest.raises(LabError, match="idempotency_conflict"):
        runner.operator_message(row["id"], "Inny wpis", "durable-message-key")
    assert (
        sum(
            e["payload"].get("sender") == "operator"
            for e in runner.store.events(row["id"], owner=OWNER)
        )
        == 1
    )
