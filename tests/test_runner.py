from __future__ import annotations

import asyncio
import json
import time
from dataclasses import FrozenInstanceError, asdict, replace

import pytest
from conftest import SPEC
from pydantic import ValidationError

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.run_config import RunConfig, RunRequest
from venom_module_cooperation_lab.runner import MODEL_IDENTITY_FIELDS, OWNER, LabRunner
from venom_module_cooperation_lab.scenarios import get_scenario


def request(**overrides):
    values = {"model_id": SPEC.model_id, "scenario_id": "split_facts", "max_turns": 4}
    return RunRequest(**(values | overrides))


def configure(runner, **attributes):
    original = runner.adapter_factory

    def factory(model, lease):
        adapter = original(model, lease)
        for key, value in attributes.items():
            setattr(adapter, key, value)
        return adapter

    runner.adapter_factory = factory


async def finish(runner, row):
    await asyncio.wait_for(asyncio.shield(runner.jobs[row["id"]].task), timeout=2)
    return runner.store.get_run(row["id"], owner=OWNER)


async def adapter_ready(adapters):
    async with asyncio.timeout(1):
        while not adapters:
            await asyncio.sleep(0.001)
    return adapters[0]


def test_config_immutable_reproducible_and_private_information():
    model = {"model_id": SPEC.model_id, "digest": "digest1"}
    first = RunConfig.build(request(), model)
    model["digest"] = "changed"
    assert first.public()["model"]["digest"] == "digest1"
    same = RunConfig.build(request(), {"model_id": SPEC.model_id, "digest": "digest1"})
    other_seed = RunConfig.build(
        request(seed=1), {"model_id": SPEC.model_id, "digest": "digest1"}
    )
    assert first.public()["config_hash"] == same.public()["config_hash"]
    assert first.public()["config_hash"] != other_seed.public()["config_hash"]
    assert "The first letter is R" in first.prompts[0]
    assert "The second letter is K" not in first.prompts[0]
    assert "The second letter is K" in first.prompts[1]
    with pytest.raises(FrozenInstanceError):
        first.mode = "single"
    baseline = RunConfig.build(request(mode="single"), {})
    assert "The second letter is K" in baseline.prompts[0]
    assert get_scenario("organization").expected == "42"
    with pytest.raises(LabError, match="scenario_not_allowed"):
        get_scenario("missing")
    for values in [
        {"owner": "model"},
        {"max_turns": 9},
        {"max_new_tokens": 2**31},
        {"temperature": float("nan")},
        {"seed": True},
    ]:
        with pytest.raises(ValidationError):
            request(**values)


@pytest.mark.asyncio
async def test_real_delivery_separate_histories_journal_and_fair_scheduler(rig):
    runner, adapters = rig
    row, created = await runner.start(request(), "key1")
    assert created and row["status"] == "queued"
    result = await finish(runner, row)
    assert result["status"] == "completed"
    adapter = adapters[0]
    assert [entry[0] for entry in adapter.recorded] == ["A", "B", "A", "B"]
    assert "second letter is K" not in adapter.recorded[0][1][0].content
    assert "Message from A" in adapter.recorded[1][1][-1].content
    assert "Message from B" in adapter.recorded[2][1][-1].content
    assert adapter.closed
    assert runner.jobs[row["id"]].histories == {}
    events = runner.store.events(row["id"], owner=OWNER)
    assert [item["seq"] for item in events] == list(range(1, len(events) + 1))
    messages = [event for event in events if event["kind"] == "message"]
    assert all(event["payload"]["sequence"] == event["seq"] for event in messages)
    assert messages[1]["payload"]["in_reply_to"] == messages[0]["payload"]["message_id"]
    assert messages[0]["payload"]["delivered_to"] == ["B"]
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_idempotency_two_starts_and_incompatible_retry(rig):
    runner, adapters = rig
    first, second = await asyncio.gather(
        runner.start(request(), "same"), runner.start(request(), "same")
    )
    assert first[0]["id"] == second[0]["id"]
    assert [first[1], second[1]] == [True, False]
    with pytest.raises(LabError, match="idempotency_conflict"):
        await runner.start(request(seed=1), "same")
    await finish(runner, first[0])
    assert len(adapters) == 1
    retry, created = await runner.start(request(), "same")
    assert not created and retry["status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected",
    [
        ("single", ["A"]),
        ("self_correction", ["A"] * 4),
        ("no_contact", ["A", "B", "A", "B"]),
    ],
)
async def test_controls_have_no_interparticipant_delivery(rig, mode, expected):
    runner, adapters = rig
    row, _ = await runner.start(request(mode=mode), "control")
    assert (await finish(runner, row))["status"] == "completed"
    assert [entry[0] for entry in adapters[0].recorded] == expected
    for _participant, history, _ in adapters[0].recorded:
        assert all(
            "Message from " not in item.content
            for item in history
            if item.role == "user"
        )
    assert all(
        not item["payload"]["delivered_to"]
        for item in runner.store.events(row["id"], owner=OWNER)
        if item["kind"] == "message"
    )


@pytest.mark.asyncio
async def test_unqualified_changed_identity_and_closed_runner(rig):
    runner, _ = rig
    runner.store.put_document(
        "qualifications", SPEC.model_id, {"qualified": True}, owner=OWNER
    )
    assert runner.models()[0]["qualified"] is False
    with pytest.raises(LabError, match="model_not_qualified"):
        await runner.start(request(), "none")
    with pytest.raises(LabError, match="model_not_allowed"):
        await runner.start(
            RunRequest(model_id="other", scenario_id="split_facts"), "none"
        )
    runner._closed = True
    with pytest.raises(LabError, match="module_stopping"):
        await runner.start(request(), "none")


@pytest.mark.asyncio
async def test_cancel_queued_is_terminal_only_after_release(rig):
    runner, adapters = rig
    row, _ = await runner.start(request(), "queued")
    await runner.cancel(row["id"])
    await runner.cancel(row["id"])
    result = await finish(runner, row)
    assert result["status"] == "cancelled"
    assert adapters == []
    assert runner.admission.snapshot()["status"] == "available"
    assert (await runner.cancel(row["id"]))["run"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_generation_waits_for_actual_thread(rig):
    runner, adapters = rig
    configure(runner, block=True)
    row, _ = await runner.start(request(), "blocked")
    adapter = await adapter_ready(adapters)
    async with asyncio.timeout(1):
        while not adapter.entered.is_set():
            await asyncio.sleep(0.001)
    snapshot = await runner.cancel(row["id"])
    assert snapshot["run"]["status"] == "cancelling"
    result = await finish(runner, row)
    assert result["status"] == "cancelled"
    assert len(adapter.recorded) == 1
    assert adapter.cancelled and adapter.closed
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_late_thread_keeps_lease_busy_until_verified_cleanup(rig):
    runner, adapters = rig
    runner.cleanup_seconds = 0.02
    configure(runner, block=True, ignore_cancel=True)
    row, _ = await runner.start(request(), "late")
    adapter = await adapter_ready(adapters)
    async with asyncio.timeout(1):
        while not adapter.entered.is_set():
            await asyncio.sleep(0.001)
    job = runner.jobs[row["id"]]
    job.deadline = time.monotonic() - 1
    await runner.cancel(row["id"])
    # Cancellation is not allowed to cancel the wait or release a live thread.
    assert runner.admission.snapshot()["status"] in {"cancelling", "owned"}
    assert (await finish(runner, row))["status"] == "failed"
    assert runner.admission.snapshot()["status"] != "available"
    adapter.released.set()
    async with asyncio.timeout(1):
        while not job.cleanup_complete:
            await asyncio.sleep(0.001)
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,code",
    [
        ("", "empty_model_output"),
        ("{bad", "malformed_model_message"),
        (
            '{"sender":"A","kind":"message","recipient":"B","content":"bad"}',
            "malformed_model_message",
        ),
        ('{"kind":"ask","recipient":"C","content":"bad"}', "malformed_model_message"),
        (
            '{"kind":"message","recipient":"B","content":"x","in_reply_to":"foreign"}',
            "unknown_reply",
        ),
    ],
)
async def test_model_output_is_validated_not_trusted_identity(rig, text, code):
    runner, adapters = rig
    configure(runner, responses=[text])
    row, _ = await runner.start(request(), "malformed")
    result = await finish(runner, row)
    assert result["status"] == "failed"
    assert runner.snapshot(row["id"])["run"]["failure_code"] == code
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_proposal_and_accept_come_only_from_model_messages(rig):
    runner, adapters = rig
    configure(
        runner,
        responses=[
            json.dumps(
                {
                    "kind": "proposal",
                    "recipient": "B",
                    "content": "Please provide the second letter.",
                }
            ),
            json.dumps({"kind": "accept", "recipient": "A", "content": "K"}),
        ],
    )
    row, _ = await runner.start(request(), "organization")
    assert (await finish(runner, row))["status"] == "completed"
    organization = [
        item["payload"]
        for item in runner.store.events(row["id"], owner=OWNER)
        if item["kind"] == "organization"
    ]
    assert [item["kind"] for item in organization] == ["proposal", "accept"]


@pytest.mark.asyncio
async def test_unknown_usage_is_conservatively_charged(rig):
    runner, adapters = rig
    configure(runner, unknown_usage=True)
    row, _ = await runner.start(request(), "unknown")
    assert (await finish(runner, row))["status"] == "completed"
    usage = [
        item["payload"]
        for item in runner.store.events(row["id"], owner=OWNER)
        if item["kind"] == "usage"
    ]
    assert all(
        item["usage_known"] is False and item["input_tokens"] is None for item in usage
    )
    assert usage[-1]["total_charged_input"] == 4 * 2048


@pytest.mark.asyncio
async def test_runtime_busy_and_actor_guards(rig):
    runner, _ = rig
    external = runner.admission.acquire(
        owner="chat", run_id="other", engine="ollama", model="other"
    )
    with pytest.raises(LabError, match="runtime_busy"):
        await runner.start(request(), "busy")
    assert runner.store.list_runs(owner=OWNER)[0]["status"] == "failed"
    assert external.release()
    with pytest.raises(PermissionError):
        runner.store.list_runs(owner="from-model")


@pytest.mark.asyncio
async def test_deadline_before_preparation_and_orphan_restart(rig):
    runner, _ = rig
    row, _ = await runner.start(request(), "expired")
    runner.jobs[row["id"]].deadline = time.monotonic() - 1
    assert (await finish(runner, row))["status"] == "failed"
    assert runner.snapshot(row["id"])["run"]["failure_code"] == "run_deadline_exceeded"
    runner.store.create_run("orphan", {}, owner=OWNER, idempotency_key="orphan")
    assert (await runner.cancel("orphan"))["run"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_start_journal_failure_releases_preparation_reservation(rig, monkeypatch):
    runner, _ = rig

    def fail(*args, **kwargs):
        raise LabError("storage_full", 507)

    with monkeypatch.context() as patch:
        patch.setattr(runner.store, "append_event", fail)
        with pytest.raises(LabError, match="storage_full"):
            await runner.start(request(), "no-journal")
    assert runner.admission.snapshot()["status"] == "available"
    row = runner.store.list_runs(owner=OWNER)[0]
    assert row["status"] == "failed"
    assert runner.snapshot(row["id"])["run"]["failure_code"] == "storage_unavailable"


@pytest.mark.asyncio
async def test_successful_second_run_prunes_only_volatile_job_history(rig):
    runner, _ = rig
    row, _ = await runner.start(request(mode="single"), "one")
    await finish(runner, row)
    following, _ = await runner.start(request(mode="single"), "two")
    await finish(runner, following)
    assert row["id"] not in runner.jobs
    assert len(runner.store.list_runs(owner=OWNER)) == 2


@pytest.mark.asyncio
async def test_failure_is_sanitized_and_terminal_status_survives_full_quota(rig):
    runner, _ = rig
    configure(runner, fail=RuntimeError("private filesystem /home/name"))
    row, _ = await runner.start(request(), "fail")
    result = await finish(runner, row)
    assert result["status"] == "failed"
    assert runner.snapshot(row["id"])["run"]["failure_code"] == "generation_failed"
    assert (
        "private filesystem"
        not in runner.store.export_run(row["id"], owner=OWNER).decode()
    )
    runner.store.limits = replace(runner.store.limits, database_bytes=1)
    runner.store.set_run_status(row["id"], "failed", owner=OWNER)
    runner.store.delete_run(row["id"], owner=OWNER)


@pytest.mark.asyncio
async def test_complete_turn_is_journalled_before_terminal_and_requires_both(rig):
    runner, _ = rig
    configure(
        runner,
        responses=[
            json.dumps({"kind": "complete", "recipient": "B", "content": "R"}),
            json.dumps({"kind": "complete", "recipient": "A", "content": "RK"}),
        ],
    )
    row, _ = await runner.start(request(), "complete")
    assert (await finish(runner, row))["status"] == "completed"
    turns = [
        event
        for event in runner.store.events(row["id"], owner=OWNER)
        if event["kind"] == "turn"
    ]
    assert [event["payload"]["status"] for event in turns] == [
        "generating",
        "completed",
        "generating",
        "completed",
    ]


@pytest.mark.asyncio
async def test_invalid_and_over_budget_usage_and_reserved_steps(rig):
    from types import SimpleNamespace

    runner, _ = rig
    row, _ = await runner.start(request(mode="single"), "budget")
    await finish(runner, row)
    job = runner.jobs[row["id"]]
    with pytest.raises(LabError, match="invalid_usage"):
        runner._charge(job, SimpleNamespace(input_tokens=True, output_tokens=1))
    with pytest.raises(LabError, match="generation_budget_exceeded"):
        runner._charge(job, SimpleNamespace(input_tokens=1, output_tokens=999))
    job.input_tokens = job.config.budgets.total_input_tokens
    with pytest.raises(LabError, match="run_budget_exhausted"):
        runner._reserve_turn(job)
    job.input_tokens = 0
    runner.store.limits = replace(runner.store.limits, run_bytes=1)
    with pytest.raises(LabError, match="run_storage_full"):
        runner._reserve_turn(job)


@pytest.mark.asyncio
async def test_cleanup_false_and_exception_keep_resource_busy(rig):
    runner, adapters = rig
    configure(runner, close=lambda: False)
    row, _ = await runner.start(request(mode="single"), "not-closed")
    assert (await finish(runner, row))["status"] == "failed"
    assert runner.admission.snapshot()["status"] != "available"
    job = runner.jobs[row["id"]]
    adapters[0].close = lambda: (_ for _ in ()).throw(RuntimeError("private"))
    assert await runner._cleanup(job) is False
    adapters[0].close = lambda: True
    assert await runner._cleanup(job) is True
    assert await runner._cleanup(job) is True
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_cancel_preparation_and_owned_task_shutdown(rig):
    runner, adapters = rig
    configure(runner, block_load=True)
    row, _ = await runner.start(request(), "prepare-cancel")
    adapter = await adapter_ready(adapters)
    async with asyncio.timeout(1):
        while not adapter.entered.is_set():
            await asyncio.sleep(0.001)
    await runner.close()
    assert (await finish(runner, row))["status"] == "cancelled"
    assert adapter.cancelled
    assert adapter.recorded == []
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_late_close_is_single_owned_task_then_releases_and_journals(rig):
    import threading

    runner, adapters = rig
    runner.cleanup_seconds = 0.02
    closing_entered = threading.Event()
    release_close = threading.Event()
    calls = []

    def slow_close():
        calls.append("close")
        closing_entered.set()
        return release_close.wait(2)

    configure(runner, close=slow_close)
    row, _ = await runner.start(request(mode="single"), "late-close")
    try:
        async with asyncio.timeout(1):
            while not closing_entered.is_set():
                await asyncio.sleep(0.001)
        result = await finish(runner, row)
        assert result["status"] == "failed"
        job = runner.jobs[row["id"]]
        assert not job.cleanup_complete
        assert runner.admission.snapshot()["status"] != "available"
        assert await runner._cleanup(job) is False
        assert calls == ["close"]
        release_close.set()
        async with asyncio.timeout(1):
            while not job.cleanup_complete:
                await asyncio.sleep(0.001)
        assert await runner._cleanup(job) is True
        assert calls == ["close"]
        assert runner.admission.snapshot()["status"] == "available"
        assert runner.snapshot(row["id"])["run"]["status"] == "failed"
        late = [
            event
            for event in runner.store.events(row["id"], owner=OWNER)
            if event["payload"].get("cleanup_late")
        ]
        assert len(late) == 1
        assert late[0]["payload"] == {
            "status": "failed",
            "quiescent": True,
            "cleanup_late": True,
        }
        assert len(adapters[0].recorded) == 1
    finally:
        release_close.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", MODEL_IDENTITY_FIELDS)
@pytest.mark.parametrize("missing", [False, True])
async def test_qualification_requires_every_immutable_identity_field(
    rig, field, missing
):
    runner, adapters = rig
    receipt = {
        **asdict(SPEC),
        "qualified": True,
        "receipt_id": "old-runtime-must-not-qualify-new-spec",
    }
    if missing:
        receipt.pop(field)
    else:
        receipt[field] += "-different"
    runner.store.put_document("qualifications", SPEC.model_id, receipt, owner=OWNER)
    assert runner.models()[0]["qualified"] is False
    with pytest.raises(LabError, match="model_not_qualified"):
        await runner.start(request(), "wrong-identity")
    assert adapters == []
    assert runner.admission.snapshot()["status"] == "available"


def test_runtime_receipt_retains_security_overlay_versions_without_private_fields():
    assert LabRunner._runtime_receipt(
        {
            "certifi_version": "2026.10.19",
            "filelock_version": "4.2.1",
            "private_path": "/private/runtime",
            "model_prompts": ["must not journal"],
        }
    ) == {"certifi_version": "2026.10.19", "filelock_version": "4.2.1"}


@pytest.mark.asyncio
async def test_default_cleanup_grace_accepts_close_after_two_seconds(rig, monkeypatch):
    import threading

    fixture, adapters = rig
    # Use the production default, not the short injected timeout of the fixture.
    runner = LabRunner(
        fixture.store, fixture.admission, fixture.model_catalog, fixture.adapter_factory
    )
    entered = threading.Event()
    release = threading.Event()
    calls = []

    def close_after_release():
        calls.append("close")
        adapters[0].busy = True
        entered.set()
        try:
            return release.wait(1)
        finally:
            adapters[0].busy = False

    configure(runner, close=close_after_release)
    loop = asyncio.get_running_loop()
    actual_clock = loop.time
    elapsed = [0.0]
    monkeypatch.setattr(loop, "time", lambda: actual_clock() + elapsed[0])
    try:
        row, _ = await runner.start(request(mode="single"), "normal-close-grace")
        job = runner.jobs[row["id"]]
        generation_deadline = job.deadline
        async with asyncio.timeout(1):
            while not entered.is_set():
                await asyncio.sleep(0.001)
        # Advance asyncio's real timeout scheduler past the observed 2.16 s close
        # without sleeping two seconds or completing/cancelling the owned thread.
        elapsed[0] = 2.16
        await asyncio.sleep(0.01)
        assert job.task is not None and not job.task.done()
        assert not job.cleanup_complete
        assert runner.admission.snapshot()["status"] != "available"
        assert job.deadline == generation_deadline
        release.set()
        result = await finish(runner, row)
        assert result["status"] == "completed"
        assert job.cleanup_complete
        assert runner.admission.snapshot()["status"] == "available"
        assert calls == ["close"]
        events = runner.store.events(row["id"], owner=OWNER)
        assert events[-1]["kind"] == "end"
        assert events[-1]["payload"]["quiescent"] is True
        assert not any(event["payload"].get("cleanup_late") for event in events)
    finally:
        release.set()
        await runner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("ignore_cancel", [False, True])
async def test_owned_task_cancellation_propagates_after_bounded_cleanup(
    rig, ignore_cancel
):
    runner, adapters = rig
    runner.cleanup_seconds = 0.02 if ignore_cancel else 0.3
    configure(runner, block=True, ignore_cancel=ignore_cancel)
    row, _ = await runner.start(request(), "cancel-owned-task")
    adapter = await adapter_ready(adapters)
    async with asyncio.timeout(1):
        while not adapter.entered.is_set():
            await asyncio.sleep(0.001)
    job = runner.jobs[row["id"]]
    assert job.task is not None
    job.task.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(job.task), timeout=1)
        assert job.task.cancelled()
        assert job.cancelled
        assert job.work is not None and not job.work.cancelled()
        assert len(adapter.recorded) == 1
        assert job.histories == {}
        if ignore_cancel:
            assert not job.cleanup_complete
            assert not job.work.done()
            assert runner.store.get_run(row["id"], owner=OWNER)["status"] == "failed"
            assert runner.admission.snapshot()["status"] != "available"
            events = runner.store.events(row["id"], owner=OWNER)
            assert events[-1]["kind"] == "end"
            assert events[-1]["payload"]["quiescent"] is False
            adapter.released.set()
            async with asyncio.timeout(1):
                while not job.cleanup_complete:
                    await asyncio.sleep(0.001)
            assert runner.store.get_run(row["id"], owner=OWNER)["status"] == "failed"
        else:
            assert job.cleanup_complete
            assert adapter.closed
            assert runner.store.get_run(row["id"], owner=OWNER)["status"] == "cancelled"
        assert runner.admission.snapshot()["status"] == "available"
    finally:
        adapter.released.set()


@pytest.mark.asyncio
async def test_next_ordinary_run_clamps_1024_to_selected_model_limit(rig):
    runner, adapters = rig
    first, _ = await runner.start(request(max_turns=1), "ordinary-first")
    assert (await finish(runner, first))["status"] == "completed"
    second, _ = await runner.start(
        request(max_turns=1, max_new_tokens=1024), "ordinary-more-tokens"
    )
    final = await finish(runner, second)
    assert final["status"] == "completed"
    assert final["config"]["budgets"]["max_new_tokens"] == 256
    assert final["config"]["requested_max_new_tokens"] == 1024
    repeated, created = await runner.start(
        request(max_turns=1, max_new_tokens=1024), "ordinary-more-tokens"
    )
    assert repeated["id"] == second["id"] and not created
    assert adapters[-1].recorded[0][2].max_new_tokens == 256
    larger = RunConfig.build(
        request(max_turns=8, max_new_tokens=16384), {"architecture": "rwkv7"}
    )
    assert larger.budgets.total_output_tokens == 8192
    assert larger.budgets.processing_steps == 24576
