"""Owned sequential experiments: durable messages and isolated participant history."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from typing import Any
from uuid import uuid4

from .errors import LabError
from .game_series import GameSeries
from .live_game_strategy import LiveGameStrategy
from .peer_review import review_step
from .run_config import OPERATOR_MODES, STRATEGIC_MODES, Budgets, RunConfig, RunRequest
from .storage import TERMINAL, LabStore, _identifier
from .tic_tac_toe import TicTacToe, parse_move

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
    series: GameSeries | None = None
    coaching: LiveGameStrategy | None = None
    qualifying: bool = False
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
    operator_waiting: bool = False
    operator_signal: asyncio.Event = field(default_factory=asyncio.Event)
    operator_submissions: dict[str, dict[str, Any]] = field(default_factory=dict)
    operator_message_id: str | None = None
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
        catalog_service: Any = None,
    ) -> None:
        self.store, self.admission = store, admission
        self.model_catalog, self.adapter_factory = model_catalog, adapter_factory
        self.cleanup_seconds = cleanup_seconds
        self.catalog_service = catalog_service
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
        if self.catalog_service is not None and not self.catalog_service.available(
            model_id
        ):
            raise LabError("model_unavailable", 409)
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

    def _runnable_model(self, model_id: str) -> dict[str, Any]:
        try:
            return self._qualified_model(model_id)
        except LabError as exc:
            if exc.code != "model_not_qualified" or self.catalog_service is None:
                raise
            spec = self.catalog_service.candidate(model_id)
            return {
                **asdict(spec),
                "can_run": True,
                "availability_reason": "available_unchecked",
            }

    def models(self) -> list[dict[str, Any]]:
        result = []
        for spec in self.model_catalog():
            try:
                result.append(self._qualified_model(spec.model_id))
            except LabError as exc:
                result.append({**asdict(spec), "availability_reason": exc.code})
        if self.catalog_service is not None:
            for model in result:
                model["can_run"] = self.catalog_service.available(
                    model["model_id"]
                ) and (model["provider"] == "ollama" or model["qualified"])
        return result

    async def start(
        self, request: RunRequest, idempotency_key: str, *, qualification: bool = False
    ) -> tuple[dict[str, Any], bool]:
        started = time.monotonic()
        _identifier(idempotency_key)
        async with self._lock:
            if self._closed:
                raise LabError("module_stopping", 503)
            previous = self.store.find_run_by_key(idempotency_key, owner=OWNER)
            if previous is not None:
                if not self._same_request(previous["config"], request, qualification):
                    raise LabError("idempotency_conflict", 409)
                return previous, False
            if self.catalog_service is not None:
                await self.catalog_service.refresh()
            config = (
                self._qualification_config(request.model_id)
                if qualification
                else RunConfig.build(request, self._runnable_model(request.model_id))
            )
            run_id = uuid4().hex
            try:
                model = config.public()["model"]
                lease = self.admission.acquire(
                    owner="cooperation_lab",
                    run_id=run_id,
                    engine=model["provider"],
                    model=request.model_id,
                )
            except Exception as exc:
                raise LabError(getattr(exc, "code", "runtime_busy")) from exc
            try:
                # Admission precedes insertion/rotation: a quarantined lease's
                # recovery record must never be evicted by a rejected start.
                row = self.store.create_run(
                    run_id,
                    config.public(),
                    owner=OWNER,
                    idempotency_key=idempotency_key,
                )
            except BaseException:
                lease.release()
                raise
            created = row["id"] == run_id
            if not created:
                lease.release()
                return row, False
            job = _Job(run_id, config, lease, started + config.budgets.wall_seconds)
            job.qualifying = qualification
            if config.scenario_id == "tic_tac_toe":
                job.game = TicTacToe()
                if config.mode in STRATEGIC_MODES:
                    job.coaching = LiveGameStrategy(config.mode)
                if config.game_count > 1:
                    job.series = GameSeries(config.game_count, config.remember_games)
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

    @staticmethod
    def _same_request(
        config: dict[str, Any], request: RunRequest, qualification: bool
    ) -> bool:
        # Compare the normalized operator input, never a rebuilt config using
        # today's weights, templates, prompts or qualification receipt.
        model_id = config["model"]["model_id"]
        if qualification:
            return (
                config["scenario_id"] == "model_qualification"
                and model_id == request.model_id
            )
        stored = {
            name: config.get(name)
            for name in (
                "scenario_id",
                "communication_language",
                "mode",
                "seed",
                "temperature",
                "top_p",
            )
        }
        stored.update(
            model_id=model_id,
            reflection_max_new_tokens=config.get("reflection_max_new_tokens", 128),
            game_count=config.get("game_count", 1),
            remember_games=config.get("remember_games", True),
            max_turns=config["budgets"]["max_turns"],
            max_new_tokens=config.get(
                "requested_max_new_tokens", config["budgets"]["max_new_tokens"]
            ),
        )
        return stored == request.model_dump()

    def _qualification_config(self, model_id: str) -> RunConfig:
        if self.catalog_service is None:
            raise LabError("model_unavailable", 409)
        spec = self.catalog_service.candidate(model_id)
        return RunConfig(
            model_json=json.dumps(asdict(spec), sort_keys=True),
            scenario_id="model_qualification",
            scenario_version="1",
            scenario_goal="Reply with a short greeting.",
            mode="no_contact",
            prompts=("You are A. Answer briefly.", "You are B. Answer briefly."),
            budgets=Budgets(
                max_turns=2,
                max_new_tokens=32,
                total_input_tokens=4096,
                total_output_tokens=64,
                processing_steps=4160,
                wall_seconds=120,
            ),
            seed=0,
            temperature=0.0,
            top_p=1.0,
            schema_version=3,
            scheduler="technical-qualification-v1",
        )

    def _record_qualification(self, job: _Job) -> None:
        model = job.config.public()["model"]
        self.store.put_document(
            "qualifications",
            model["model_id"],
            {
                **model,
                "qualified": True,
                "receipt_id": job.run_id,
                "qualification_run_id": job.run_id,
                "timestamp": time.time(),
                "scope": "two_generations_reset_cleanup_not_quality",
            },
            owner=OWNER,
        )

    def _emit(self, job: _Job, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.store.append_event(job.run_id, kind, payload, owner=OWNER)

    def snapshot(self, run_id: str) -> dict[str, Any]:
        row = self.store.get_run(run_id, owner=OWNER)
        job = self.jobs.get(run_id)
        if job and job.failure:
            row["failure_code"] = job.failure
        return {"run": row}

    def operator_message(
        self, run_id: str, content: str, idempotency_key: str
    ) -> dict[str, Any]:
        _identifier(idempotency_key)
        row = self.store.get_run(run_id, owner=OWNER)
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        previous = self.store.find_operator_submission(run_id, key_hash, owner=OWNER)
        if previous is not None:
            if previous["payload"]["content"] != content:
                raise LabError("idempotency_conflict", 409)
            return {"event": previous, "created": False}
        job = self.jobs.get(run_id)
        if job is None or job.config.mode not in OPERATOR_MODES:
            raise LabError("operator_chat_unavailable", 409)
        self._check(job)
        if row["status"] != "running" or not job.operator_waiting:
            raise LabError("operator_chat_not_waiting", 409)
        from .adapters.base import ChatMessage

        recipients = ["A"] if job.config.mode == "operator_relay" else ["A", "B"]
        message_id = uuid4().hex
        message = {
            "schema_version": 1,
            "run_id": run_id,
            "message_id": message_id,
            "sender": "operator",
            "submission_key_hash": key_hash,
            "recipient": "A" if job.config.mode == "operator_relay" else "all",
            "kind": "message",
            "content": content,
            "delivered_to": recipients,
            "timestamp": time.time(),
            "in_reply_to": None,
            "sequence": row["last_seq"] + 1,
        }
        # Persist before acknowledging or exposing the text to either context.
        event = self._emit(job, "message", message)
        for participant in recipients:
            prefix = (
                "Wiadomość operatora: "
                if job.config.communication_language == "pl"
                else "Operator message: "
            )
            job.histories[participant].append(ChatMessage("user", prefix + content))
            job.last_delivered[participant] = message_id
        job.messages.add(message_id)
        job.operator_message_id = message_id
        job.operator_submissions[idempotency_key] = event
        job.operator_waiting = False
        job.operator_signal.set()
        return {"event": event, "created": True}

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
                self._emit(job, "game", self._game_state(job, job.game.public()))
            if job.config.mode in OPERATOR_MODES:
                await self._operator_turns(job)
            else:
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
            if job.qualifying and outcome == "completed" and clean:
                try:
                    self._record_qualification(job)
                except (LabError, PermissionError):
                    outcome, job.failure = "failed", "storage_unavailable"
            self._finish(job, outcome)
            job.histories.clear()

    def _prepare_histories(self, job: _Job) -> None:
        from .adapters.base import ChatMessage

        for participant, prompt in zip(("A", "B"), job.config.prompts, strict=True):
            memory = (
                (
                    job.series.outcome_memory(
                        participant, job.config.communication_language
                    )
                    if job.coaching
                    else job.series.memory(
                        participant, job.config.communication_language
                    )
                )
                if job.series
                else ""
            )
            if job.coaching:
                memory += job.coaching.memory(
                    participant, job.config.communication_language
                )
            job.histories[participant] = [
                ChatMessage("system", prompt + ("\n" + memory if memory else ""))
            ]
            if job.config.mode != "operator_review" and job.game is None:
                job.histories[participant].append(
                    ChatMessage("user", job.config.scenario_goal)
                )

    def _charge(
        self, job: _Job, result: Any, *, output_limit: int | None = None
    ) -> dict[str, Any]:
        budgets = job.config.budgets
        limit = budgets.max_new_tokens if output_limit is None else output_limit
        input_charge = (
            budgets.max_context_tokens
            if result.input_tokens is None
            else result.input_tokens
        )
        output_charge = limit if result.output_tokens is None else result.output_tokens
        if any(
            type(value) is not int or value < 0
            for value in (input_charge, output_charge)
        ):
            raise LabError("invalid_usage")
        if input_charge > budgets.max_context_tokens or output_charge > limit:
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

    def _reserve_turn(self, job: _Job, *, output_limit: int | None = None) -> None:
        budget = job.config.budgets
        limit = budget.max_new_tokens if output_limit is None else output_limit
        if (
            job.input_tokens + budget.max_context_tokens > budget.total_input_tokens
            or job.output_tokens + limit > budget.total_output_tokens
            or job.processing_steps + budget.max_context_tokens + limit
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
            "peak_vram_bytes",
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
        if mode == "operator_review":
            return review_step(index, None).participant
        return "A" if mode in {"single", "self_correction"} else ("A", "B")[index % 2]

    def _turn_context(self, job: _Job, participant: str) -> list[Any]:
        from .adapters.base import ChatMessage

        history = job.histories[participant]
        if (
            job.game is not None
            and job.config.public()["model"]["architecture"] == "rwkv7"
        ):
            observation = job.game.recurrent_prompt(
                participant, job.config.communication_language
            )
            if history[-1].role == "user":
                history[-1] = ChatMessage(
                    "user", history[-1].content + "\n" + observation
                )
            else:
                history.append(ChatMessage("user", observation))
            return history
        if job.game is not None:
            # The authoritative board already contains every accepted move.
            # Keep the last actual peer message for causal delivery/reply tracing,
            # but never append obsolete full boards to the next request.
            last_id = job.last_delivered[participant]
            incoming = next(
                (
                    message
                    for message in reversed(history)
                    if last_id and message.role == "user" and last_id in message.content
                ),
                None,
            )
            compact = [history[0]]
            if incoming is not None:
                compact.append(incoming)
            compact.append(
                ChatMessage(
                    "user",
                    job.game.prompt(participant, job.config.communication_language),
                )
            )
            job.histories[participant] = compact
            return compact
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
        if (
            job.game is not None
            and job.coaching is None
            and config.public()["model"]["architecture"]
            in {
                "rwkv7",
                "hrm_text",
                "huginn_raven",
            }
        ):
            parameters = GenerationParameters(
                max_new_tokens=config.budgets.max_new_tokens,
                max_context_tokens=config.budgets.max_context_tokens,
                temperature=0.0,
                top_p=0.0,
                seed=config.seed,
                profile="structured",
            )
        if job.qualifying and config.public()["model"]["architecture"] == "hrm_text":
            parameters = replace(
                parameters, profile="structured", temperature=0.0, top_p=0.0
            )
        if job.coaching:
            parameters = replace(
                parameters, profile="structured", session_protocol="game-eval-v2"
            )
        completed: set[str] = set()
        turns = 1 if config.mode == "single" else config.budgets.max_turns
        for game_index in range(config.game_count):
            if game_index:
                # Keep loaded weights, reset private runtime state and replay only
                # bounded public experience. Identical memory policy for all engines.
                self._check(job)
                await self._work(job, lambda: job.adapter.reset())
                job.game = TicTacToe()
                if job.coaching:
                    job.coaching.begin()
                if job.series:
                    job.series.begin(game_index + 1)
                self._prepare_histories(job)
                job.last_delivered = {"A": None, "B": None}
                self._emit(job, "game", self._game_state(job, job.game.public()))
            for index in range(turns):
                message = await self._generate_turn(
                    job, parameters, game_index * turns + index
                )
                if job.game is not None:
                    if job.game.finished:
                        if config.mode == "game_reflection":
                            await self._reflect_game(job, parameters)
                        break
                    continue
                if message["kind"] == "complete":
                    completed.add(message["sender"])
                    if config.mode in {"single", "self_correction"} or completed == {
                        "A",
                        "B",
                    }:
                        break

    async def _reflect_game(self, job: _Job, parameters: Any) -> None:
        from .adapters.base import ChatMessage

        assert job.coaching is not None and job.game is not None
        from .reflection import validate_note

        note_tokens = job.config.reflection_max_new_tokens or 128
        for player in ("A", "B"):
            self._check(job)
            self._reserve_turn(job, output_limit=note_tokens)
            feedback = job.coaching.feedback(job.game, player)
            instruction = (
                'Zwróć wyłącznie JSON z jednym polem "rule". Napisz jedną krótką '
                "ogólną zasadę na następną partię na podstawie własnego błędu. "
                "Bez konkretnych współrzędnych, kopiowania polecenia i rozumowania."
                if job.config.communication_language == "pl"
                else 'Return only JSON with one field "rule". Write one short general '
                "rule for the next game based on your own mistake. "
                "No square coordinates, instruction copies or reasoning."
            )
            params = replace(
                parameters,
                max_new_tokens=note_tokens,
                allowed_outputs=(),
                response_format="text",
            )
            turn_id = f"reflection-{job.series.number if job.series else 1}-{player}"
            self._emit(
                job,
                "turn",
                {
                    "turn_id": turn_id,
                    "participant_id": player,
                    "purpose": "reflection",
                    "status": "generating",
                },
            )
            result = await self._work(
                job,
                partial(
                    job.adapter.generate,
                    player,
                    (
                        ChatMessage("system", instruction),
                        ChatMessage("user", job.coaching.encode_feedback(feedback)),
                    ),
                    params,
                    job.deadline,
                ),
            )
            if not result.quiescent:
                job.lease.cancel()
                raise LabError("runtime_quiescence_unconfirmed")
            self._emit(
                job,
                "usage",
                {
                    "purpose": "reflection",
                    "turn_id": turn_id,
                    "player": player,
                    **self._charge(job, result, output_limit=note_tokens),
                },
            )
            note = validate_note(result.text, instruction)
            if note.accepted:
                job.coaching.notes[player] = note.rule
                job.coaching.accepted_notes += 1
            else:
                job.coaching.rejected_notes += 1
            self._emit(
                job,
                "reflection",
                {
                    "player": player,
                    "content": note.rule,
                    "accepted": note.accepted,
                    "reason_code": note.reason,
                    "raw_content": result.raw_text or result.text,
                    "feedback": feedback,
                    "max_new_tokens": note_tokens,
                    "game_number": job.series.number if job.series else 1,
                },
            )
            self._emit(
                job,
                "turn",
                {
                    "turn_id": turn_id,
                    "participant_id": player,
                    "purpose": "reflection",
                    "status": "completed",
                },
            )
        self._emit(job, "game", self._game_state(job, job.game.public()))

    @staticmethod
    def _game_state(job: _Job, board: dict[str, Any]) -> dict[str, Any]:
        return {
            **board,
            **({"series": job.series.public()} if job.series else {}),
            **({"strategy": job.coaching.public()} if job.coaching else {}),
        }

    async def _operator_turns(self, job: _Job) -> None:
        from .adapters.base import GenerationParameters

        config = job.config
        parameters = GenerationParameters(
            max_new_tokens=config.budgets.max_new_tokens,
            max_context_tokens=config.budgets.max_context_tokens,
            temperature=config.temperature,
            top_p=config.top_p,
            seed=config.seed,
        )
        round_size = 3 if config.mode == "operator_review" else 2
        for index in range(0, config.budgets.max_turns, round_size):
            self._check(job)
            if index and config.mode == "operator_review":
                # Each new review task is independent; keep the journal, not
                # the previous task's KV/history in this bounded context.
                await self._work(job, lambda: job.adapter.reset())
                self._prepare_histories(job)
                job.last_delivered = {"A": None, "B": None}
            job.operator_signal.clear()
            job.operator_waiting = True
            self._emit(
                job, "operator", {"waiting": True, "round": index // round_size + 1}
            )
            while not job.operator_signal.is_set():
                # Bounded wait keeps STOP and the original wall deadline effective.
                try:
                    await asyncio.wait_for(job.operator_signal.wait(), timeout=0.1)
                except TimeoutError:
                    pass
                self._check(job)
            self._emit(
                job, "operator", {"waiting": False, "round": index // round_size + 1}
            )
            for turn in range(index, index + round_size):
                await self._generate_turn(job, parameters, turn)
        job.operator_waiting = False

    async def _generate_turn(
        self, job: _Job, parameters: Any, index: int
    ) -> dict[str, Any]:
        self._check(job)
        self._reserve_turn(job)
        participant = (
            ("A" if job.game.moves % 2 == 0 else "B")
            if job.game
            else self._participant(job.config.mode, index)
        )
        history = self._turn_context(job, participant)
        turn_id = f"turn-{index + 1:04d}"
        phase = None
        if job.config.mode == "operator_review":
            from .adapters.base import ChatMessage

            step = review_step(index, job.config.communication_language)
            phase = step.phase
            history = [*history, ChatMessage("user", step.instruction)]
        self._emit(
            job,
            "turn",
            {
                "turn_id": turn_id,
                "participant_id": participant,
                "status": "generating",
                **({"phase": phase} if phase else {}),
            },
        )
        if (
            job.game is not None
            and job.coaching is None
            and job.config.public()["model"]["architecture"]
            in {
                "rwkv7",
                "hrm_text",
                "huginn_raven",
            }
        ):
            parameters = replace(
                parameters,
                allowed_outputs=tuple(
                    "ABC"[i // 3] + str(i % 3 + 1)
                    for i, value in enumerate(job.game.board)
                    if not value
                ),
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
        return self._publish_result(job, participant, turn_id, result)

    def _publish_result(
        self, job: _Job, participant: str, turn_id: str, result: Any
    ) -> dict[str, Any]:
        from .adapters.base import ChatMessage

        if not result.quiescent:
            job.lease.cancel()
            raise LabError("runtime_quiescence_unconfirmed")
        usage = self._charge(job, result)
        self._emit(job, "usage", {"turn_id": turn_id, **usage})
        strategy = None
        if job.coaching and job.game:
            try:
                strategy = job.coaching.choose(
                    job.game, participant, result.text, job.config.seed + job.game.moves
                )
            except LabError:
                invalid = self._message(job, participant, turn_id, "invalid")
                invalid.update(
                    content=result.text, raw_content=result.text, delivered_to=[]
                )
                self._emit(job, "message", invalid)
                raise
            message = self._message(
                job, participant, turn_id, strategy["action"]["square"]
            )
            message.update(
                model_move=strategy["model_action"]["square"],
                assessment=strategy["assessment"],
                assistance=strategy.get("assistance"),
                execution_assessment=strategy.get("execution_assessment"),
                raw_content=result.raw_text or result.text,
            )
        else:
            message = self._message(job, participant, turn_id, result.text)
        if getattr(result, "raw_text", None) is not None:
            message["raw_content"] = result.raw_text
        board = None
        if job.game is not None:
            message["raw_content"] = getattr(result, "raw_text", None) or result.text
            try:
                move, move_format = parse_move(message["content"])
                message["game_move"] = move
                message["move_format"] = move_format
                board = job.game.play(participant, move)
                if job.series:
                    message["game_number"] = job.series.number
                    job.series.record(participant, move, board)
            except LabError:
                message["delivered_to"] = []
                self._emit(job, "message", message)
                raise
        self._emit(job, "message", message)
        if board is not None:
            self._emit(job, "game", self._game_state(job, board))
        job.histories[participant].append(ChatMessage("assistant", message["content"]))
        for recipient in message["delivered_to"]:
            if recipient == "operator":
                continue
            job.histories[recipient].append(
                ChatMessage(
                    "user",
                    (
                        (
                            f"Przeciwnik zagrał {board['last_move']}."
                            if job.config.communication_language == "pl"
                            else f"Opponent played {board['last_move']}."
                        )
                        if board is not None
                        and job.config.public()["model"]["architecture"] == "rwkv7"
                        else (
                            f"Wiadomość {message['message_id']} od {participant}: "
                            if job.config.communication_language == "pl"
                            else f"Message {message['message_id']} from {participant}: "
                        )
                        + message["content"]
                    ),
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
        recipient = (
            "operator"
            if job.config.mode in OPERATOR_MODES
            else ("B" if sender == "A" else "A")
        )
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
                or payload.get("recipient")
                not in (
                    {"A", "B", "all", "operator"}
                    if job.config.mode in OPERATOR_MODES
                    else {"A", "B", "all"}
                )
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
        if job.config.mode == "operator_relay":
            recipient = "B" if sender == "A" else "operator"
        phase_fields = {}
        if job.config.mode == "operator_review":
            step = review_step(
                int(turn_id.removeprefix("turn-")) - 1,
                job.config.communication_language,
            )
            recipient = step.recipient
            in_reply_to = job.last_delivered[sender]
            reply_source = "host_review_context" if in_reply_to else None
            phase_fields = {"phase": step.phase}
        delivered = self._delivery_recipients(job.config.mode, sender, recipient)
        if (
            job.config.mode == "operator_chat"
            or (job.config.mode == "operator_relay" and sender == "B")
            or (job.config.mode == "operator_review" and recipient == "operator")
        ):
            delivered.append("operator")
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
            **phase_fields,
            **(
                {"operator_message_id": job.operator_message_id}
                if job.config.mode in OPERATOR_MODES
                else {}
            ),
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
