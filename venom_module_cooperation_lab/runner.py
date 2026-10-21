"""Owned sequential experiments: durable messages and isolated participant history."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from functools import partial
from typing import Any
from uuid import uuid4

from .errors import LabError
from .run_config import RunConfig, RunRequest
from .storage import TERMINAL, LabStore, _identifier
from .tic_tac_toe import TicTacToe

OWNER = "local_operator"
_ALLOWED_KINDS = {"message", "proposal", "accept", "ask", "evidence", "complete"}
MODEL_IDENTITY_FIELDS = (
    "model_id",
    "architecture",
    "provider",
    "artifact",
    "revision",
    "digest",
    "tokenizer_hash",
    "template_hash",
    "runtime",
    "quantization",
)


@dataclass
class _Job:
    run_id: str
    config: RunConfig
    lease: Any
    deadline: float
    adapter: Any = None
    task: asyncio.Task[None] | None = None
    work: asyncio.Task[Any] | None = None
    closing: asyncio.Task[bool] | None = None
    watched_work: asyncio.Task[Any] | None = None
    game: TicTacToe | None = None
    cleanup_pending: bool = False
    late_cleanup_recorded: bool = False
    cancelled: bool = False
    failure: str | None = None
    cleanup_complete: bool = False
    cleanup_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    histories: dict[str, list[Any]] = field(default_factory=dict)
    messages: set[str] = field(default_factory=set)
    last_delivered: dict[str, str | None] = field(
        default_factory=lambda: {"A": None, "B": None}
    )
    input_tokens: int = 0
    output_tokens: int = 0
    processing_steps: int = 0


class LabRunner:
    def __init__(
        self,
        store: LabStore,
        admission: Any,
        model_catalog: Callable[[], list[Any]],
        adapter_factory: Callable[[str, Any], Any],
        *,
        cleanup_seconds: float = 10.0,
    ) -> None:
        self.store, self.admission = store, admission
        self.model_catalog, self.adapter_factory = model_catalog, adapter_factory
        self.cleanup_seconds = cleanup_seconds
        self.jobs: dict[str, _Job] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        self._tasks: set[asyncio.Task[Any]] = set()

    def _own(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        self._tasks.add(task)

        def done(finished: asyncio.Task[Any]) -> None:
            self._tasks.discard(finished)
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(done)
        return task

    def _qualified_model(self, model_id: str) -> dict[str, Any]:
        for spec in self.model_catalog():
            if spec.model_id != model_id:
                continue
            result = asdict(spec)
            receipt = self.store.get_document("qualifications", model_id, owner=OWNER)
            valid = (
                receipt
                and receipt.get("qualified") is True
                and isinstance(receipt.get("receipt_id"), str)
                and bool(receipt.get("receipt_id"))
                and all(
                    key in receipt and receipt[key] == result[key]
                    for key in MODEL_IDENTITY_FIELDS
                )
            )
            if not valid or receipt is None:
                raise LabError("model_not_qualified", 503)
            result.update(
                qualified=True,
                qualification=receipt["receipt_id"],
                availability_reason="qualified",
            )
            return result
        raise LabError("model_not_allowed", 422)

    def models(self) -> list[dict[str, Any]]:
        result = []
        for spec in self.model_catalog():
            try:
                result.append(self._qualified_model(spec.model_id))
            except LabError:
                result.append(asdict(spec))
        return result

    async def start(
        self, request: RunRequest, idempotency_key: str
    ) -> tuple[dict[str, Any], bool]:
        started = time.monotonic()
        _identifier(idempotency_key)
        async with self._lock:
            if self._closed:
                raise LabError("module_stopping", 503)
            config = RunConfig.build(request, self._qualified_model(request.model_id))
            run_id = uuid4().hex
            row = self.store.create_run(
                run_id, config.public(), owner=OWNER, idempotency_key=idempotency_key
            )
            created = row["id"] == run_id
            if not created:
                return row, False
            try:
                model = config.public()["model"]
                lease = self.admission.acquire(
                    owner="cooperation_lab",
                    run_id=run_id,
                    engine=model["provider"],
                    model=request.model_id,
                )
            except Exception as exc:
                self.store.set_run_status(run_id, "failed", owner=OWNER)
                self.store.append_event(
                    run_id,
                    "error",
                    {
                        "code": getattr(exc, "code", "runtime_busy"),
                        "reason_code": getattr(exc, "code", "runtime_busy"),
                    },
                    owner=OWNER,
                )
                raise LabError(getattr(exc, "code", "runtime_busy")) from exc
            job = _Job(run_id, config, lease, started + config.budgets.wall_seconds)
            if config.scenario_id == "tic_tac_toe":
                job.game = TicTacToe()
            self.jobs[run_id] = job
            try:
                self.store.set_run_status(run_id, "queued", owner=OWNER)
                self._emit(
                    job,
                    "run",
                    {"status": "queued", "config_hash": config.public()["config_hash"]},
                )
            except (LabError, PermissionError):
                job.failure = "storage_unavailable"
                await self._cleanup(job)
                self._finish(job, "failed")
                raise
            job.task = self._own(asyncio.create_task(self._execute(job)))
            # Completed runs live in SQLite; avoid retaining private histories forever.
            for old_id, old in list(self.jobs.items()):
                if (
                    old_id != run_id
                    and old.cleanup_complete
                    and old.task
                    and old.task.done()
                ):
                    self.jobs.pop(old_id)
            return self.store.get_run(run_id, owner=OWNER), True

    def _emit(self, job: _Job, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.append_event(job.run_id, kind, payload, owner=OWNER)

    def snapshot(self, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id, owner=OWNER)
        job = self.jobs.get(run_id)
        if job and job.failure:
            row["failure_code"] = job.failure
        return {"run": row}

    async def cancel(self, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id, owner=OWNER)
        if row["status"] in TERMINAL:
            return {"run": row}
        job = self.jobs.get(run_id)
        if job is None:
            self.store.set_run_status(run_id, "interrupted", owner=OWNER)
            return self.snapshot(run_id)
        if not job.cancelled:
            job.cancelled = True
            job.lease.cancel()
            if job.adapter is not None:
                # This task is retained; cancellation never relies on the HTTP
                # caller staying connected or on terminating its awaiter.
                self._own(asyncio.create_task(asyncio.to_thread(job.adapter.cancel)))
            try:
                self.store.set_run_status(run_id, "cancelling", owner=OWNER)
                self._emit(job, "run", {"status": "cancelling"})
            except LabError:
                job.failure = "storage_unavailable"
        return self.snapshot(run_id)

    def _check(self, job: _Job) -> None:
        if job.cancelled:
            raise LabError("run_cancelled")
        if time.monotonic() >= job.deadline:
            raise LabError("run_deadline_exceeded", 408)

    async def _work(self, job: _Job, function: Callable[[], Any]) -> Any:
        self._check(job)
        work = self._own(asyncio.create_task(asyncio.to_thread(function)))
        job.work = work
        while not work.done():
            remaining = max(0, job.deadline - time.monotonic())
            await asyncio.wait({work}, timeout=min(0.05, remaining))
            self._check(job)
        result = work.result()
        self._check(job)
        return result

    async def _execute(self, job: _Job) -> None:
        outcome = "failed"
        try:
            self._check(job)
            self.store.set_run_status(job.run_id, "preparing", owner=OWNER)
            self._emit(job, "run", {"status": "preparing"})
            job.adapter = self.adapter_factory(
                job.config.public()["model"]["model_id"], job.lease
            )
            receipt = await self._work(job, lambda: job.adapter.load(job.deadline))
            self._emit(
                job,
                "run",
                {
                    "status": "preparing",
                    "runtime_receipt": self._runtime_receipt(receipt),
                },
            )
            await self._work(job, lambda: job.adapter.reset())
            self._prepare_histories(job)
            self.store.set_run_status(job.run_id, "running", owner=OWNER)
            self._emit(job, "run", {"status": "running"})
            if job.game is not None:
                self._emit(job, "game", job.game.public())
            await self._turns(job)
            outcome = "completed"
        except LabError as exc:
            job.failure = exc.code
            outcome = "cancelled" if exc.code == "run_cancelled" else "failed"
        except asyncio.CancelledError:
            # Shutdown cancellation is not proof of an ended worker.
            job.cancelled = True
            job.failure = "run_interrupted"
            job.lease.cancel()
            # Propagate task cancellation after the finally block owns cleanup;
            # the actual worker is retained until its quiescence is confirmed.
            raise
        except Exception:
            job.failure = "generation_failed"
        finally:
            if job.cancelled:
                outcome = "cancelled"
            clean = await self._cleanup(job)
            if job.cancelled and clean:
                outcome = "cancelled"
            if not clean:
                outcome, job.failure = "failed", "runtime_quiescence_unconfirmed"
            self._finish(job, outcome)
            job.histories.clear()

    def _prepare_histories(self, job: _Job) -> None:
        from .adapters.base import ChatMessage

        for participant, prompt in zip(("A", "B"), job.config.prompts, strict=True):
            job.histories[participant] = [
                ChatMessage("system", prompt),
                ChatMessage("user", job.config.scenario_goal),
            ]

    def _charge(self, job: _Job, result: Any) -> dict[str, Any]:
        budgets = job.config.budgets
        input_charge = (
            budgets.max_context_tokens
            if result.input_tokens is None
            else result.input_tokens
        )
        output_charge = (
            budgets.max_new_tokens
            if result.output_tokens is None
            else result.output_tokens
        )
        if any(
            type(value) is not int or value < 0
            for value in (input_charge, output_charge)
        ):
            raise LabError("invalid_usage")
        if (
            input_charge > budgets.max_context_tokens
            or output_charge > budgets.max_new_tokens
        ):
            raise LabError("generation_budget_exceeded")
        job.input_tokens += input_charge
        job.output_tokens += output_charge
        job.processing_steps += input_charge + output_charge
        return {
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "charged_input_tokens": input_charge,
            "charged_output_tokens": output_charge,
            "usage_known": result.input_tokens is not None
            and result.output_tokens is not None,
            "total_charged_input": job.input_tokens,
            "total_charged_output": job.output_tokens,
            "processing_steps": job.processing_steps,
            "generation_s": result.generation_s,
            "ttft_s": result.ttft_s,
            "stop_reason": result.stop_reason,
            "effective_parameters": dict(result.effective_parameters),
        }

    def _reserve_turn(self, job: _Job) -> None:
        budget = job.config.budgets
        if (
            job.input_tokens + budget.max_context_tokens > budget.total_input_tokens
            or job.output_tokens + budget.max_new_tokens > budget.total_output_tokens
            or job.processing_steps + budget.max_context_tokens + budget.max_new_tokens
            > budget.processing_steps
        ):
            raise LabError("run_budget_exhausted")
        row = self.store.get_run(job.run_id, owner=OWNER)
        if (
            row["bytes"] + self.store.limits.event_bytes + 4096
            > self.store.limits.run_bytes
        ):
            raise LabError("run_storage_full", 507)

    @staticmethod
    def _runtime_receipt(value: Any) -> dict[str, Any]:
        allowed = {
            "state",
            "load_s",
            "runtime",
            "runtime_version",
            "torch_version",
            "certifi_version",
            "filelock_version",
            "strategy",
            "precision",
            "device",
            "model_digest",
            "quantization",
            "weights_loaded",
            "metadata_verified",
            "think",
        }
        if not isinstance(value, dict):
            raise LabError("invalid_runtime_receipt")
        return {
            key: item
            for key, item in value.items()
            if key in allowed
            and (item is None or type(item) in {str, int, float, bool})
        }

    @staticmethod
    def _participant(mode: str, index: int) -> str:
        return "A" if mode in {"single", "self_correction"} else ("A", "B")[index % 2]

    def _turn_context(self, job: _Job, participant: str) -> list[Any]:
        from .adapters.base import ChatMessage

        history = job.histories[participant]
        if job.game is not None:
            history.append(
                ChatMessage(
                    "user",
                    job.game.prompt(participant, job.config.communication_language),
                )
            )
            return history
        if history[-1].role != "user":
            followup = (
                "Verify your previous answer."
                if job.config.mode == "self_correction"
                else "Continue using only the information in your own context."
            )
            if job.config.communication_language == "pl":
                followup = (
                    "Sprawdź swoją poprzednią odpowiedź."
                    if job.config.mode == "self_correction"
                    else (
                        "Kontynuuj, korzystając wyłącznie z informacji "
                        "we własnym kontekście."
                    )
                )
            history.append(ChatMessage("user", followup))
        return history

    async def _turns(self, job: _Job) -> None:
        from .adapters.base import GenerationParameters

        config = job.config
        parameters = GenerationParameters(
            max_new_tokens=config.budgets.max_new_tokens,
            max_context_tokens=config.budgets.max_context_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            seed=config.seed,
        )
        completed: set[str] = set()
        turns = 1 if config.mode == "single" else config.budgets.max_turns
        for index in range(turns):
            self._check(job)
            self._reserve_turn(job)
            participant = self._participant(config.mode, index)
            history = self._turn_context(job, participant)
            turn_id = f"turn-{index + 1:04d}"
            self._emit(
                job,
                "turn",
                {
                    "turn_id": turn_id,
                    "participant_id": participant,
                    "status": "generating",
                },
            )
            result = await self._work(
                job,
                partial(
                    job.adapter.generate,
                    participant,
                    tuple(history),
                    parameters,
                    job.deadline,
                ),
            )
            message = self._publish_result(job, participant, turn_id, result)
            if job.game is not None:
                if job.game.finished:
                    break
                continue
            if message["kind"] == "complete":
                completed.add(participant)
                if config.mode in {"single", "self_correction"} or completed == {
                    "A",
                    "B",
                }:
                    break

    def _publish_result(
        self, job: _Job, participant: str, turn_id: str, result: Any
    ) -> dict[str, Any]:
        from .adapters.base import ChatMessage

        if not result.quiescent:
            job.lease.cancel()
            raise LabError("runtime_quiescence_unconfirmed")
        usage = self._charge(job, result)
        self._emit(job, "usage", {"turn_id": turn_id, **usage})
        message = self._message(job, participant, turn_id, result.text)
        board = None
        if job.game is not None:
            try:
                board = job.game.play(participant, message["content"])
            except LabError:
                message["delivered_to"] = []
                self._emit(job, "message", message)
                raise
        self._emit(job, "message", message)
        if board is not None:
            self._emit(job, "game", board)
        job.histories[participant].append(ChatMessage("assistant", message["content"]))
        for recipient in message["delivered_to"]:
            job.histories[recipient].append(
                ChatMessage(
                    "user",
                    (
                        f"Wiadomość {message['message_id']} od {participant}: "
                        if job.config.communication_language == "pl"
                        else f"Message {message['message_id']} from {participant}: "
                    )
                    + message["content"],
                )
            )
            job.last_delivered[recipient] = message["message_id"]
        job.messages.add(message["message_id"])
        if message["kind"] in {"proposal", "accept"}:
            self._emit(
                job,
                "organization",
                {
                    "message_id": message["message_id"],
                    "sender": participant,
                    "kind": message["kind"],
                    "content": message["content"],
                },
            )
        self._emit(
            job,
            "turn",
            {"turn_id": turn_id, "participant_id": participant, "status": "completed"},
        )
        return message

    @staticmethod
    def _delivery_recipients(mode: str, sender: str, recipient: str) -> list[str]:
        if mode in {"single", "self_correction", "no_contact"}:
            return []
        return [
            name for name in ("A", "B") if name != sender and recipient in {name, "all"}
        ]

    def _message(
        self, job: _Job, sender: str, turn_id: str, text: str
    ) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip():
            raise LabError("empty_model_output")
        content, kind = text.strip(), "message"
        recipient = "B" if sender == "A" else "A"
        in_reply_to = job.last_delivered[sender]
        reply_source = "host_context" if in_reply_to else None
        if content.startswith(("{", "[")):
            try:
                payload = json.loads(content)
            except (ValueError, RecursionError) as exc:
                raise LabError("malformed_model_message") from exc
            if (
                not isinstance(payload, dict)
                or set(payload) - {"kind", "recipient", "content", "in_reply_to"}
                or payload.get("kind") not in _ALLOWED_KINDS
                or payload.get("recipient") not in {"A", "B", "all"}
                or payload.get("recipient") == sender
                or not isinstance(payload.get("content"), str)
                or not payload["content"].strip()
            ):
                raise LabError("malformed_model_message")
            content, kind, recipient = (
                payload["content"],
                payload["kind"],
                payload["recipient"],
            )
            in_reply_to, reply_source = payload.get("in_reply_to"), "model"
            if in_reply_to is not None and (
                not isinstance(in_reply_to, str) or in_reply_to not in job.messages
            ):
                raise LabError("unknown_reply")
        delivered = self._delivery_recipients(job.config.mode, sender, recipient)
        sequence = self.store.get_run(job.run_id, owner=OWNER)["last_seq"] + 1
        return {
            "schema_version": 1,
            "run_id": job.run_id,
            "message_id": uuid4().hex,
            "sender": sender,
            "recipient": recipient,
            "in_reply_to": in_reply_to,
            "reply_source": reply_source,
            "sequence": sequence,
            "turn_id": turn_id,
            "timestamp": time.time(),
            "kind": kind,
            "content": content,
            "delivered_to": delivered,
        }

    def _schedule_late_cleanup(self, job: _Job) -> None:
        self._own(asyncio.create_task(self._cleanup(job)))

    async def _wait_owned_work(self, job: _Job) -> bool:
        if job.work is None or job.work.done():
            return True
        if job.adapter:
            self._own(asyncio.create_task(asyncio.to_thread(job.adapter.cancel)))
        finished, _ = await asyncio.wait({job.work}, timeout=self.cleanup_seconds)
        if not finished:
            job.cleanup_pending = True
            if job.watched_work is not job.work:
                job.watched_work = job.work
                job.work.add_done_callback(
                    lambda _done: self._schedule_late_cleanup(job)
                )
        return bool(finished)

    def _close_finished(self, job: _Job, task: asyncio.Task[bool]) -> None:
        if not job.cleanup_pending or task.cancelled():
            return
        try:
            closed = task.result()
        except Exception:
            return
        if closed:
            self._schedule_late_cleanup(job)

    async def _close_owned_adapter(self, job: _Job) -> bool:
        if job.adapter is None:
            return True
        if job.closing is None:

            def close() -> bool:
                with job.lease.cleanup(confirm_quiescent=job.adapter.is_quiescent):
                    return bool(job.adapter.close())

            job.closing = self._own(asyncio.create_task(asyncio.to_thread(close)))
            job.closing.add_done_callback(lambda done: self._close_finished(job, done))
        closing = job.closing
        finished, _ = await asyncio.wait({closing}, timeout=self.cleanup_seconds)
        if not finished:
            job.cleanup_pending = True
            return False
        try:
            closed = closing.result()
        except Exception:
            # A later explicit recovery may retry after this close really ended.
            job.closing = None
            raise
        if not closed or not job.adapter.is_quiescent():
            job.closing = None
            return False
        return True

    def _record_late_cleanup(self, job: _Job) -> None:
        if not job.cleanup_pending or job.late_cleanup_recorded:
            return
        try:
            row = self.store.get_run(job.run_id, owner=OWNER)
            if row["status"] not in TERMINAL:
                return
            self._emit(
                job,
                "run",
                {"status": row["status"], "quiescent": True, "cleanup_late": True},
            )
            job.late_cleanup_recorded = True
        except (LabError, PermissionError):
            # Resource proof remains true; never invent a persisted event.
            pass

    async def _cleanup(self, job: _Job) -> bool:
        async with job.cleanup_lock:
            if job.cleanup_complete:
                self._record_late_cleanup(job)
                return True
            if not await self._wait_owned_work(job):
                return False
            try:
                if not await self._close_owned_adapter(job):
                    job.cleanup_pending = True
                    return False
                job.cleanup_complete = bool(job.lease.release())
                if job.cleanup_complete:
                    self._record_late_cleanup(job)
                return job.cleanup_complete
            except Exception:
                job.cleanup_pending = True
                return False

    def _finish(self, job: _Job, status: str) -> None:
        try:
            if job.failure and status != "cancelled":
                self._emit(
                    job, "error", {"code": job.failure, "reason_code": job.failure}
                )
            self.store.set_run_status(job.run_id, status, owner=OWNER)
            self._emit(job, "run", {"status": status})
            self._emit(
                job,
                "end",
                {
                    "status": status,
                    "reason_code": job.failure,
                    "quiescent": job.cleanup_complete,
                },
            )
        except (LabError, PermissionError):
            # Failure is exposed in snapshot even if a full disk cannot append
            # another journal record. Terminal status uses reclamation allowance.
            job.failure = job.failure or "storage_unavailable"
            try:
                self.store.set_run_status(job.run_id, "failed", owner=OWNER)
            except (LabError, PermissionError):
                pass

    async def close(self) -> None:
        self._closed = True
        for run_id in list(self.jobs):
            try:
                await self.cancel(run_id)
            except (LabError, PermissionError):
                continue
        tasks = {
            job.task for job in self.jobs.values() if job.task and not job.task.done()
        }
        if tasks:
            await asyncio.wait(tasks, timeout=self.cleanup_seconds)
