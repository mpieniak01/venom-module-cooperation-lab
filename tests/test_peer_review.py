from __future__ import annotations

import asyncio

import pytest
from conftest import SPEC
from pydantic import ValidationError
from test_operator_chat import finish, waiting

from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import OWNER


def request(**values):
    return RunRequest(
        model_id=SPEC.model_id,
        scenario_id="peer_review",
        mode="operator_review",
        **values,
    )


def test_review_has_its_own_scheduler_and_complete_three_turn_rounds():
    config = RunConfig.build(request(communication_language="pl"), {})
    assert config.scheduler == "author-review-revise-v1"
    assert config.schema_version == 3 and config.participant_count == 3
    assert config.budgets.max_turns == 6 and config.budgets.wall_seconds == 360
    assert "etap" in config.prompts[0]
    for count in [1, 2, 4, 5, 7, 8, 9]:
        with pytest.raises(ValidationError):
            request(max_turns=count)
    with pytest.raises(ValidationError):
        RunRequest(model_id=SPEC.model_id, scenario_id="peer_review", mode="dialog")
    with pytest.raises(ValidationError):
        RunRequest(
            model_id=SPEC.model_id,
            scenario_id="operator_conversation",
            mode="operator_review",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["pl", "en"])
async def test_draft_review_and_revision_are_real_context_transfers(rig, language):
    runner, adapters = rig
    row, _ = await runner.start(
        request(max_turns=3, communication_language=language), "review"
    )
    await waiting(runner, row)
    # Even an early model completion claim must not skip review or revision.
    adapters[0].responses = [
        '{"kind":"complete","recipient":"operator","content":"Draft: 2+2=5"}',
        '{"kind":"message","recipient":"all","content":"Review: use 2+2=4"}',
        "Revised: 2+2=4",
    ]
    runner.operator_message(row["id"], "TASK: compute 2+2", "task")
    assert (await finish(runner, row))["status"] == "completed"
    recorded = adapters[0].recorded
    assert [x[0] for x in recorded] == ["A", "B", "A"]
    assert "Draft: 2+2=5" in "\n".join(m.content for m in recorded[1][1])
    assert "Review: use 2+2=4" in "\n".join(m.content for m in recorded[2][1])
    assert all(
        any("TASK: compute 2+2" in m.content for m in history)
        for _, history, _ in recorded
    )
    assert [history[-1].content for _, history, _ in recorded][0] != recorded[2][1][
        -1
    ].content
    events = runner.store.events(row["id"], owner=OWNER)
    messages = [e["payload"] for e in events if e["kind"] == "message"]
    assert [m.get("phase") for m in messages] == [None, "draft", "critique", "revision"]
    assert [m["delivered_to"] for m in messages] == [
        ["A", "B"],
        ["B"],
        ["A"],
        ["operator"],
    ]
    assert messages[2]["in_reply_to"] == messages[1]["message_id"]
    assert messages[3]["in_reply_to"] == messages[2]["message_id"]
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_two_review_tasks_wait_for_operator_between_complete_rounds(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(), "two-rounds")
    await waiting(runner, row)
    runner.operator_message(row["id"], "First task", "first")
    await waiting(runner, row, 1)
    assert len(adapters[0].recorded) == 3
    runner.operator_message(row["id"], "Second task", "second")
    assert (await finish(runner, row))["status"] == "completed"
    assert [x[0] for x in adapters[0].recorded] == ["A", "B", "A", "A", "B", "A"]
    assert all(
        not any("First task" in m.content for m in h)
        for _, h, _ in adapters[0].recorded[3:]
    )
    assert all(
        any("Second task" in m.content for m in h)
        for _, h, _ in adapters[0].recorded[3:]
    )


@pytest.mark.asyncio
async def test_stop_during_review_never_fabricates_final_revision(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(max_turns=3), "stop-review")
    await waiting(runner, row)
    adapter = adapters[0]
    original = adapter.generate

    def controlled(participant, *args):
        if participant == "B":
            adapter.block = True
        return original(participant, *args)

    adapter.generate = controlled
    runner.operator_message(row["id"], "Task", "task")
    async with asyncio.timeout(2):
        while not adapter.entered.is_set():
            await asyncio.sleep(0.001)
    await runner.cancel(row["id"])
    assert (await finish(runner, row))["status"] == "cancelled"
    assert [x[0] for x in adapter.recorded] == ["A", "B"]
    messages = [
        e["payload"]
        for e in runner.store.events(row["id"], owner=OWNER)
        if e["kind"] == "message"
    ]
    assert not any(m.get("phase") == "revision" for m in messages)
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_compact_review_prompts_fit_existing_ollama_byte_bound(rig):
    runner, adapters = rig
    row, _ = await runner.start(
        request(max_turns=3, communication_language="pl"), "byte-bound"
    )
    await waiting(runner, row)
    adapters[0].responses = ["D" * 512, "R" * 512, "Final"]
    runner.operator_message(row["id"], "Oblicz 17 + 25.", "short-task")
    assert (await finish(runner, row))["status"] == "completed"
    for _, history, parameters in adapters[0].recorded:
        conservative = 256 + sum(
            len(message.content.encode()) + 16 for message in history
        )
        assert conservative + parameters.max_new_tokens <= parameters.max_context_tokens
