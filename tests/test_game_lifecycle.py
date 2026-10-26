"""Owned CPU operations must finish before an evaluation releases host admission."""

from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest
from venom_core.services.runtime_admission import RuntimeAdmission

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.config import EvaluationRequest
from venom_module_cooperation_lab.evaluation.service import (
    EvaluationJob,
    EvaluationService,
)


class BlockingAdapter:
    def __init__(self, lease):
        self.lease = lease
        self.entered = threading.Event()
        self.released = threading.Event()
        self.close_entered = threading.Event()
        self.close_released = threading.Event()
        self.busy = False
        self.block_close = False
        self.ignore_cancel = False
        self.cancelled = False
        self.close_calls = 0
        self.close_results = []

    def operation(self):
        with self.lease.operation(
            kind="generation", confirm_quiescent=self.is_quiescent
        ):
            self.busy = True
            self.entered.set()
            try:
                self.released.wait(2)
            finally:
                self.busy = False
        return "answer"

    def cancel(self):
        self.cancelled = True
        if not self.ignore_cancel:
            self.released.set()

    def close(self):
        self.close_calls += 1
        self.close_entered.set()
        if self.block_close:
            self.close_released.wait(2)
        if self.close_results:
            value = self.close_results.pop(0)
            if isinstance(value, Exception):
                raise value
            return value
        # Real adapters also enter their own lease cleanup. Nested same-owner
        # cleanup must remain supported after a cancelled generation.
        with self.lease.cleanup(confirm_quiescent=self.is_quiescent):
            return not self.busy

    def is_quiescent(self):
        return not self.busy


@pytest.fixture
async def owned(tmp_path):
    admission = RuntimeAdmission(tmp_path / "admission.sqlite3", enabled=True)
    lease = admission.acquire(
        owner="cooperation_lab",
        run_id="eval-fixture",
        engine="local_component",
        model="fixture",
    )
    service = EvaluationService(SimpleNamespace(store=None, admission=admission))
    service.saved = []
    service._save = lambda job: service.saved.append(dict(job.state))
    service.store = SimpleNamespace(
        terminal=lambda *args: None,
        get=lambda eid: dict(service.jobs[eid].state),
    )
    state = {
        "id": "fixture",
        "status": "running",
        "created": time.time(),
        "episodes": [],
        "error": None,
    }
    job = EvaluationJob(state, lease, time.monotonic() + 5)
    adapter = job.adapter = BlockingAdapter(lease)
    service.jobs["fixture"] = job
    yield service, job, adapter, admission
    adapter.released.set()
    adapter.close_released.set()
    if job.task and not job.task.done():
        await asyncio.wait({job.task}, timeout=2)
    if service.tasks:
        await asyncio.wait(service.tasks, timeout=2)
    if not job.released:
        try:
            await service._cleanup(job)
        except Exception:
            pass


async def entered(event):
    async with asyncio.timeout(1):
        while not event.is_set():
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
async def test_cancel_keeps_lease_owned_until_worker_and_nested_cleanup_finish(owned):
    service, job, adapter, admission = owned
    job.task = asyncio.create_task(service._work(job, adapter.operation))
    await entered(adapter.entered)
    assert admission.snapshot()["status"] != "available"
    value = await service.cancel("fixture")
    assert value["status"] == "cancelling" and job.cancelled
    with pytest.raises(LabError, match="run_cancelled"):
        await job.task
    # A cancelled waiter is not itself proof that model resources were closed.
    assert admission.snapshot()["status"] != "available"
    assert await service._cleanup(job)
    assert admission.snapshot()["status"] == "available"
    assert adapter.cancelled and adapter.close_calls == 1
    assert await service._cleanup(job)
    assert adapter.close_calls == 1


@pytest.mark.asyncio
async def test_deadline_requests_stop_and_cannot_release_an_active_operation(owned):
    service, job, adapter, admission = owned
    adapter.ignore_cancel = True
    with pytest.raises(LabError, match="generation_timeout"):
        await service._work(job, adapter.operation, time.monotonic() + 0.01)
    assert adapter.entered.is_set()
    await entered_cancel(adapter)
    assert admission.snapshot()["status"] != "available"
    assert not job.released and adapter.close_calls == 0
    adapter.released.set()
    assert await service._cleanup(job)
    assert admission.snapshot()["status"] == "available"


async def entered_cancel(adapter):
    async with asyncio.timeout(1):
        while not adapter.cancelled:
            await asyncio.sleep(0.001)


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [False, RuntimeError("close failed")])
async def test_close_failure_can_be_retried_after_real_operation_has_ended(
    owned, first
):
    service, job, adapter, admission = owned
    adapter.close_results = [first, True]
    if isinstance(first, Exception):
        with pytest.raises(RuntimeError, match="close failed"):
            await service._cleanup(job)
    else:
        assert not await service._cleanup(job)
    assert admission.snapshot()["status"] != "available"
    assert await service._cleanup(job)
    assert adapter.close_calls == 2
    assert admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_late_worker_cleanup_is_owned_and_eventually_releases(owned, monkeypatch):
    service, job, adapter, admission = owned
    real_wait = asyncio.wait

    async def short_wait(tasks, *, timeout=None, **kwargs):
        return await real_wait(
            tasks, timeout=0.01 if timeout == 10 else timeout, **kwargs
        )

    monkeypatch.setattr(asyncio, "wait", short_wait)
    adapter.ignore_cancel = True
    work = asyncio.create_task(service._work(job, adapter.operation))
    await entered(adapter.entered)
    job.cancelled = True
    job.lease.cancel()
    with pytest.raises(LabError, match="run_cancelled"):
        await work
    assert not await service._cleanup(job)
    assert admission.snapshot()["status"] != "available"
    assert not job.released
    adapter.released.set()
    async with asyncio.timeout(1):
        while not job.released:
            await asyncio.sleep(0.005)
    assert admission.snapshot()["status"] == "available"
    assert adapter.close_calls == 1
    assert service.saved[-1]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_late_close_cleanup_retains_ownership_until_unload_finishes(
    owned, monkeypatch
):
    service, job, adapter, admission = owned
    real_wait = asyncio.wait

    async def short_wait(tasks, *, timeout=None, **kwargs):
        return await real_wait(
            tasks, timeout=0.01 if timeout == 10 else timeout, **kwargs
        )

    monkeypatch.setattr(asyncio, "wait", short_wait)
    adapter.block_close = True
    assert not await service._cleanup(job)
    # The 10 ms cleanup deadline does not guarantee OS thread scheduling.
    await entered(adapter.close_entered)
    assert adapter.close_entered.is_set() and not job.released
    assert admission.snapshot()["status"] != "available"
    adapter.close_released.set()
    async with asyncio.timeout(1):
        while not job.released:
            await asyncio.sleep(0.005)
    assert admission.snapshot()["status"] == "available"
    assert adapter.close_calls == 1


@pytest.mark.asyncio
async def test_resume_is_rejected_after_module_shutdown_even_for_durable_result(owned):
    service, job, adapter, admission = owned
    job.lease.release()
    job.released = True
    service.closed = True
    request = EvaluationRequest(
        model_id="rwkv7-g1k-2.9b", case_ids=["nim-last-stone-v1"]
    )
    previous = {
        "id": "old",
        "status": "interrupted",
        "created": time.time(),
        "config": {
            "request": request.model_dump(),
            "model_identity": {},
            "manifest_hash": "same",
            "model": {"provider": "local_component"},
        },
        "episodes": [{"block_id": "b", "status": "interrupted", "attempt": 1}],
        "attempt_history": [],
        "block_restarts": 0,
    }
    service.snapshot = lambda eid: previous
    service.preflight = lambda req: {
        "supported": True,
        "configuration": {"model_identity": {}, "manifest_hash": "same"},
    }
    service.store.save = lambda state: None

    async def no_op(job):
        pass

    service._execute = no_op
    with pytest.raises(LabError, match="module_stopping"):
        await service.resume("old")
    assert admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_cancel_before_execute_never_constructs_or_loads_adapter(owned):
    service, job, adapter, admission = owned
    job.adapter = None
    job.cancelled = True
    request = EvaluationRequest(
        model_id="rwkv7-g1k-2.9b", case_ids=["nim-last-stone-v1"]
    )
    job.state["config"] = {
        "request": request.model_dump(),
        "max_new_tokens": request.max_new_tokens,
    }
    constructed = []
    service.runner.adapter_factory = lambda *args: constructed.append(args) or adapter
    await service._execute(job)
    assert not constructed
    assert admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_late_cleanup_preserves_successful_series_outcome(owned, monkeypatch):
    service, job, adapter, admission = owned
    real_wait = asyncio.wait

    async def short_wait(tasks, *, timeout=None, **kwargs):
        return await real_wait(
            tasks, timeout=0.01 if timeout == 10 else timeout, **kwargs
        )

    monkeypatch.setattr(asyncio, "wait", short_wait)
    job.target_status = "completed"
    job.state.update(status="cleanup_pending", error="runtime_quiescence_unconfirmed")
    adapter.block_close = True
    assert not await service._cleanup(job)
    adapter.close_released.set()
    async with asyncio.timeout(1):
        while not job.released or not service.saved:
            await asyncio.sleep(0.005)
    assert service.saved[-1]["status"] == "completed"
    assert service.saved[-1]["error"] is None
    assert admission.snapshot()["status"] == "available"


def payload_session(job):
    from pathlib import Path

    from test_adapters import Process

    from venom_module_cooperation_lab.adapters.registry import RWKV_SPEC
    from venom_module_cooperation_lab.adapters.rwkv import RecurrentAdapter
    from venom_module_cooperation_lab.evaluation.sessions import SessionDriver

    adapter = RecurrentAdapter(RWKV_SPEC, job.lease, Path("/unused"), Path("/unused"))
    process = adapter._process = Process()
    original = process.generate

    def generate(*args):
        value = original(*args)
        value["text"] = '{"heap":0,"take":1}'
        return value

    process.generate = generate
    job.adapter = adapter
    job.session = SessionDriver(adapter, "native_incremental", "carry")
    job.session.begin_episode()
    job.state["config"] = {"generation_applied": {"temperature": 0, "top_p": 1}}
    return adapter, process


@pytest.mark.asyncio
async def test_memory_payload_keeps_exact_reveals_without_rules_or_hidden_cards(
    owned,
):
    import copy
    import json

    from venom_module_cooperation_lab.evaluation.games import MemoryEnvironment

    service, job, _, _ = owned
    adapter, process = payload_session(job)
    request = EvaluationRequest(
        model_id=adapter.spec.model_id,
        case_ids=["memory-seed17-v1"],
        episode_memory="carry",
        observation_mode="native_incremental",
    )
    item = {
        "case_id": "memory-seed17-v1",
        "episode": 1,
        "block_id": "memory:A",
        "attempt": 1,
        "decisions": [],
    }
    env = MemoryEnvironment({}, 17)
    observation = env.observation("A", True)
    before = copy.deepcopy(observation)
    record, _ = await service._response(job, item, "A", observation, request)
    item["decisions"].append(record)
    first = json.loads(adapter._histories["A"][0].content)
    assert (
        observation == before
    )  # Model-facing compaction does not mutate the environment.
    assert "legal_actions" not in first["observation"]
    assert first["observation"]["legal_action_space"]["cards"] == {
        "choose": 2,
        "distinct": True,
        "unmatched": list(range(16)),
    }
    assert first["observation"]["board"] == [None] * 16
    assert first["observation"]["last_reveal"] == []
    assert "rules" in first["observation"] and "action_schema" in first["observation"]
    env.step("A", {"cards": [0, 1]})
    next_observation = env.observation("A", True)
    await service._response(job, item, "A", next_observation, request)
    second = json.loads(adapter._histories["A"][-2].content)
    assert "rules" not in second["observation"]
    assert "action_schema" not in second["observation"]
    assert second["observation"]["last_reveal"] == env.last_reveal
    assert "known_pairs" not in second["observation"]
    assert "_cards" not in second["observation"]
    assert "Solo 4x4 matching" not in process.calls[-1][1]
    assert second["event_id"] != first["event_id"]


@pytest.mark.asyncio
async def test_carry_without_reflection_receives_previous_result_once_on_next_episode(
    owned,
):
    import json

    from venom_module_cooperation_lab.evaluation.config import plan
    from venom_module_cooperation_lab.evaluation.manifest import CASES

    service, job, _, _ = owned
    adapter, process = payload_session(job)
    request = EvaluationRequest(
        model_id=adapter.spec.model_id,
        case_ids=["nim-last-stone-v1"],
        repetitions=2,
        swap_sides=False,
        episode_memory="carry",
        observation_mode="native_incremental",
    )
    items = plan(request, CASES)
    job.state["episodes"] = items
    await service._episode(job, items[0], request)
    assert items[0]["status"] == "game_completed"
    assert job.feedback["A"]["result"] == {
        "winner": "A",
        "draw": False,
        "success": True,
    }
    first = json.loads(adapter._histories["A"][0].content)
    assert "previous_episode" not in first
    job.session.begin_episode()
    await service._episode(job, items[1], request)
    assert items[1]["status"] == "game_completed"
    second = json.loads(adapter._histories["A"][-2].content)
    assert second["previous_episode"]["episode_id"] == "nim-last-stone-v1:1"
    assert second["previous_episode"]["final_state"]["heaps"] == [0]
    assert second["previous_episode"]["result"]["winner"] == "A"
    assert "rules" not in second["observation"]
    assert process.calls[-1][1].count("previous_episode") == 1
    # Worker input is only the next event, not the preceding game's prompt/answer.
    assert "Assistant: {" not in process.calls[-1][1]


@pytest.mark.asyncio
async def test_reflection_uses_retained_private_history_without_copying_own_decisions(
    owned,
):
    import json

    from venom_module_cooperation_lab.evaluation.config import plan
    from venom_module_cooperation_lab.evaluation.manifest import CASES

    service, job, _, _ = owned
    adapter, _ = payload_session(job)
    request = EvaluationRequest(
        model_id=adapter.spec.model_id,
        case_ids=["nim-last-stone-v1"],
        swap_sides=False,
        episode_memory="carry",
        reflection="episode_note",
        observation_mode="native_incremental",
    )
    item = plan(request, CASES)[0]
    job.state["episodes"] = [item]
    await service._episode(job, item, request)
    assert item["status"] == "game_completed"
    assert [d["purpose"] for d in item["decisions"]] == ["action", "reflection"]
    note = json.loads(adapter._histories["A"][-2].content)
    assert note["purpose"] == "reflection"
    assert "own_decisions" not in note["observation"]
    assert note["observation"]["result"]["winner"] == "A"
    assert (
        "A" not in job.feedback
    )  # Already delivered in the separate reflection event.
    assert not adapter._histories["B"]


@pytest.mark.asyncio
async def test_cancel_during_final_unload_reaches_terminal_instead_of_stuck_cancelling(
    owned,
):
    service, job, adapter, admission = owned
    adapter.block_close = True
    adapter.load = lambda deadline: {"state": "ready"}
    service.runner.adapter_factory = lambda *args: adapter
    request = EvaluationRequest(
        model_id="rwkv7-g1k-2.9b", case_ids=["nim-last-stone-v1"]
    )
    job.state["config"] = {
        "request": request.model_dump(),
        "max_new_tokens": request.max_new_tokens,
    }
    job.task = asyncio.create_task(service._execute(job))
    await entered(adapter.close_entered)
    await service.cancel("fixture")
    assert job.cancelled and job.state["status"] == "cancelling"
    adapter.close_released.set()
    await asyncio.wait_for(asyncio.shield(job.task), 1)
    assert job.released and admission.snapshot()["status"] == "available"
    assert job.state["status"] == "cancelled"


@pytest.mark.asyncio
async def test_stop_retries_pending_cleanup_after_execute_task_has_finished(owned):
    service, job, adapter, admission = owned
    adapter.close_results = [False, True]
    job.target_status = "completed"
    assert not await service._cleanup(job)
    assert adapter.close_calls == 1 and not job.released
    job.state.update(status="cleanup_pending", error="runtime_quiescence_unconfirmed")
    job.task = asyncio.create_task(asyncio.sleep(0))
    await job.task
    assert job.task.done() and admission.snapshot()["status"] != "available"

    result = await service.cancel("fixture")
    assert result["status"] == "cancelling"
    async with asyncio.timeout(1):
        while (
            not job.released
            or not service.saved
            or service.saved[-1]["status"] != "cancelled"
        ):
            await asyncio.sleep(0.005)
    assert adapter.close_calls == 2
    assert admission.snapshot()["status"] == "available"
    assert job.state["status"] == "cancelled"
    # Repeating STOP on a released job does not run a third close operation.
    await service.cancel("fixture")
    assert adapter.close_calls == 2
