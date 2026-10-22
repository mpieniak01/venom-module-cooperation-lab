"""Owned, sequential v2 evaluations under the shared host runtime admission."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..adapters.base import GenerationParameters
from ..errors import LabError
from ..runner import MODEL_IDENTITY_FIELDS
from .actions import VERSION as MAPPER_VERSION
from .config import EvaluationRequest, plan, seeded
from .reports import progress, summarize
from .store import EvaluationStore


@dataclass
class EvaluationJob:
    state: dict[str, Any]
    lease: Any
    deadline: float
    adapter: Any = None
    session: Any = None
    task: asyncio.Task[Any] | None = None
    work: asyncio.Task[Any] | None = None
    closing: asyncio.Task[Any] | None = None
    feedback: dict[str, Any] = field(default_factory=dict)
    target_status: str | None = None
    target_error: str | None = None
    cancelled: bool = False
    released: bool = False
    cleanup_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class EvaluationService:
    def __init__(self, runner: Any):
        self.runner = runner
        self.store = EvaluationStore(runner.store)
        self.jobs: dict[str, EvaluationJob] = {}
        self.lock = asyncio.Lock()
        self.closed = False
        self.tasks: set[asyncio.Task[Any]] = set()

    def _own(self, task: asyncio.Task[Any]) -> asyncio.Task[Any]:
        self.tasks.add(task)

        def done(value: asyncio.Task[Any]) -> None:
            self.tasks.discard(value)
            if not value.cancelled():
                value.exception()

        task.add_done_callback(done)
        return task

    def capabilities(self) -> dict[str, Any]:
        from .manifest import SUITE_VERSION, list_cases
        from .sessions import capabilities_for

        models = [{**m, **capabilities_for(m)} for m in self.runner.models()]
        runtime = self.runner.admission.snapshot()
        return {
            "cases": list_cases(),
            "storage": {
                "series_used": self.runner.store.history_count(),
                "evaluation_series": self.store.count(),
                "rotation": "oldest_terminal_first",
                "max_series": self.runner.store.limits.max_runs,
                "retention_days": self.runner.store.limits.retention_days,
            },
            "models": models,
            "games": ["tic_tac_toe", "nim", "memory", "sokoban"],
            "manifest_version": SUITE_VERSION,
            "ready": runtime["status"] == "available" and not self.closed,
            "runtime": runtime,
            "reason_code": "ready"
            if runtime["status"] == "available"
            else "runtime_busy",
            "limits": {
                "episodes": 128,
                "decisions": 384,
                "snapshot_bytes": self.runner.store.limits.run_bytes,
                "context_tokens": 8192,
                "wall_seconds": 1800,
                "snapshot_restore": False,
            },
        }

    def preflight(self, request: EvaluationRequest) -> dict[str, Any]:
        from .manifest import CASES, SUITE_VERSION, manifest_hash
        from .sessions import capabilities_for

        items = plan(request, CASES)
        reasons = []
        try:
            model = self.runner._runnable_model(request.model_id)
        except LabError as exc:
            model = {"model_id": request.model_id}
            reasons.append(exc.code)
        caps = capabilities_for(model)
        if request.observation_mode not in caps["observation_modes"]:
            reasons.append("unsupported_observation_mode")
        if request.max_context_tokens > caps["max_context_tokens"]:
            reasons.append("unsupported_context_budget")
        if request.action_constraint != "none":
            reasons.append("unsupported_action_constraint")
        if request.num_steps != 8 and model.get("architecture") != "huginn_raven":
            reasons.append("unsupported_compute_steps")
        if request.reflection != "off" and request.episode_memory != "carry":
            reasons.append("reflection_requires_carry")
        for item in items:
            if request.opponent == "model" and item["game"] in {"memory", "sokoban"}:
                reasons.append("solo_game_has_no_opponent")
            if request.opponent == "remembering" and item["game"] in {
                "tic_tac_toe",
                "nim",
            }:
                reasons.append("unsupported_reference")
        configuration = {
            **request.model_dump(),
            "schema_version": 2,
            "response_encoding": "compact-game-actions-v1"
            if request.response_mode == "mapped"
            else "json-events-v2",
            "response_mapper": MAPPER_VERSION
            if request.response_mode == "mapped"
            else "strict-json-v2",
            "protocol": "game-eval-v2",
            "manifest_version": SUITE_VERSION,
            "manifest_hash": manifest_hash(),
            "cases": [copy.deepcopy(c) for c in CASES if c["id"] in request.case_ids],
            "model": model,
            "model_identity": {k: model.get(k) for k in MODEL_IDENTITY_FIELDS},
            "snapshot_restore": False,
            "generation_planned": {
                "temperature": 0.0
                if request.decoding == "greedy"
                else request.temperature,
                "top_p": 1.0 if request.decoding == "greedy" else request.top_p,
                "num_steps": request.num_steps
                if model.get("architecture") == "huginn_raven"
                else None,
            },
            "history_policy": "allowed_observations_and_own_actions-v2",
            "observation_encoding": "rules-once-memory-action-space-v1",
            "terminal_feedback": "public-final-state-and-outcome-once-v1",
            "rng_policy": "sha256(seed,case,repeat,player,decision,purpose)-v1",
        }
        return {
            "supported": not reasons,
            "reason_codes": sorted(set(reasons)),
            "planned_episodes": len(items),
            "planned_blocks": len({i["block_id"] for i in items}),
            "planned_decisions": sum(i["max_actions"] for i in items),
            "configuration": configuration,
            "items": items,
        }

    def snapshot(self, eid: str) -> dict[str, Any]:
        stored = self.store.get(eid)
        value = copy.deepcopy(self.jobs[eid].state) if eid in self.jobs else stored
        value["progress"] = progress(value["episodes"])
        value["summary"] = summarize(value)
        value["can_resume"] = (
            not self.closed
            and value["status"]
            not in {"queued", "running", "cancelling", "cleanup_pending"}
            and bool(self._resumable_blocks(value))
        )
        return value

    def list(self) -> list[dict[str, Any]]:
        return [self.snapshot(r["id"]) for r in self.store.list()]

    def _prune_jobs(self) -> None:
        # SQLite is authoritative; keep at most eight completed live snapshots.
        done = [
            key
            for key, job in self.jobs.items()
            if job.released and job.task is not None and job.task.done()
        ]
        for key in done[:-8]:
            del self.jobs[key]

    def _save(self, job: EvaluationJob) -> None:
        job.state["updated"] = time.time()
        job.state["progress"] = progress(job.state["episodes"])
        job.state["summary"] = summarize(job.state)
        self.store.save(job.state)

    async def start(
        self, request: EvaluationRequest, key: str
    ) -> tuple[dict[str, Any], bool]:
        async with self.lock:
            if self.closed:
                raise LabError("module_stopping", 503)
            old = self.store.by_key(key)
            if old:
                if old["config"]["request"] != request.model_dump():
                    raise LabError("idempotency_conflict", 409)
                return self.snapshot(old["id"]), False
            check = self.preflight(request)
            if not check["supported"]:
                raise LabError(check["reason_codes"][0], 422)
            eid = uuid4().hex
            configuration = {**check["configuration"], "request": request.model_dump()}
            state = {
                "id": eid,
                "key": key,
                "created": time.time(),
                "updated": time.time(),
                "status": "queued",
                "error": None,
                "config": configuration,
                "episodes": check["items"],
                "attempt_history": [],
                "block_restarts": 0,
            }
            lease = self.runner.admission.acquire(
                owner="cooperation_lab",
                run_id="evaluation-" + eid,
                engine=configuration["model"]["provider"],
                model=request.model_id,
            )
            try:
                self.store.create(state)
            except BaseException:
                lease.release()
                raise
            job = EvaluationJob(state, lease, time.monotonic() + 1800)
            self._prune_jobs()
            self.jobs[eid] = job
            job.task = self._own(asyncio.create_task(self._execute(job)))
            return self.snapshot(eid), True

    @staticmethod
    def _resumable_blocks(state: dict[str, Any]) -> set[str]:
        retry = {
            "runtime_error",
            "environment_error",
            "cancelled",
            "interrupted",
            "pending",
            "running",
            "storage_full",
        }
        skipped = {
            "cancelled",
            "runtime_error",
            "interrupted",
            "storage_full",
            "decision_timeout",
        }
        return {
            row["block_id"]
            for row in state["episodes"]
            if row["status"] in retry
            or (row["status"] == "skipped" and row.get("reason_code") in skipped)
            or row.get("reflection_error") in {"runtime_error", "storage_full"}
        }

    async def resume(self, eid: str) -> dict[str, Any]:
        async with self.lock:
            if self.closed:
                raise LabError("module_stopping", 503)
            previous = self.snapshot(eid)
            if previous["status"] in {
                "queued",
                "running",
                "cancelling",
                "cleanup_pending",
            }:
                raise LabError("evaluation_active", 409)
            request = EvaluationRequest(**previous["config"]["request"])
            check = self.preflight(request)
            if not check["supported"]:
                raise LabError(check["reason_codes"][0], 422)
            if (
                previous["config"]["model_identity"]
                != check["configuration"]["model_identity"]
                or previous["config"]["manifest_hash"]
                != check["configuration"]["manifest_hash"]
                or previous["config"].get(
                    "response_mapper",
                    "action-map-v1"
                    if request.response_mode == "mapped"
                    else "strict-json-v2",
                )
                != check["configuration"]["response_mapper"]
            ):
                raise LabError("evaluation_identity_changed", 409)
            state = copy.deepcopy(previous)
            state.pop("ended", None)
            groups = self._resumable_blocks(state)
            if not groups:
                raise LabError("nothing_to_resume", 409)
            for block in groups:
                rows = [r for r in state["episodes"] if r["block_id"] == block]
                state["attempt_history"].append(copy.deepcopy(rows))
                attempt = max(r["attempt"] for r in rows) + 1
                for row in rows:
                    row.pop("reflection_error", None)
                    row.update(
                        attempt=attempt,
                        status="pending",
                        reason_code=None,
                        result=None,
                        decisions=[],
                        started_at=None,
                        ended_at=None,
                    )
            state["block_restarts"] += len(groups)
            state.update(status="queued", error=None)
            lease = self.runner.admission.acquire(
                owner="cooperation_lab",
                run_id="evaluation-" + eid,
                engine=state["config"]["model"]["provider"],
                model=request.model_id,
            )
            try:
                self.store.save(state)
            except BaseException:
                lease.release()
                raise
            job = EvaluationJob(state, lease, time.monotonic() + 1800)
            self._prune_jobs()
            self.jobs[eid] = job
            job.task = self._own(asyncio.create_task(self._execute(job)))
            return self.snapshot(eid)

    async def cancel(self, eid: str) -> dict[str, Any]:
        job = self.jobs.get(eid)
        if job and not job.released:
            job.cancelled = True
            job.lease.cancel()
            job.state["status"] = "cancelling"
            if job.adapter:
                self._own(asyncio.create_task(asyncio.to_thread(job.adapter.cancel)))
            self._save(job)
            if job.task is None or job.task.done():
                self._own(asyncio.create_task(self._late_cleanup(job)))
        return self.snapshot(eid)

    async def delete(self, eid: str) -> None:
        async with self.lock:
            state = self.snapshot(eid)
            if state["status"] in {
                "queued",
                "running",
                "cancelling",
                "cleanup_pending",
            }:
                raise LabError("evaluation_active", 409)
            job = self.jobs.get(eid)
            if job is not None and not job.released:
                raise LabError("evaluation_active", 409)
            self.store.delete(eid)
            self.jobs.pop(eid, None)

    def _check(self, job: EvaluationJob) -> None:
        if job.cancelled:
            raise LabError("run_cancelled")
        if time.monotonic() >= job.deadline:
            raise LabError("generation_timeout", 408)

    async def _work(
        self, job: EvaluationJob, fn: Any, deadline: float | None = None
    ) -> Any:
        self._check(job)
        task = self._own(asyncio.create_task(asyncio.to_thread(fn)))
        job.work = task
        while not task.done():
            await asyncio.wait({task}, timeout=0.05)
            if deadline is not None and time.monotonic() >= deadline:
                if job.adapter:
                    self._own(
                        asyncio.create_task(asyncio.to_thread(job.adapter.cancel))
                    )
                raise LabError("generation_timeout", 408)
            self._check(job)
        result = task.result()
        self._check(job)
        return result

    async def _cleanup(self, job: EvaluationJob) -> bool:
        async with job.cleanup_lock:
            if job.released:
                return True
            if job.work and not job.work.done():
                if job.adapter:
                    self._own(
                        asyncio.create_task(asyncio.to_thread(job.adapter.cancel))
                    )
                ready, _ = await asyncio.wait({job.work}, timeout=10)
                if not ready:
                    job.work.add_done_callback(
                        lambda _: self._own(
                            asyncio.create_task(self._late_cleanup(job))
                        )
                    )
                    return False
            if job.adapter:
                if job.closing is None:

                    def close() -> bool:
                        with job.lease.cleanup(
                            confirm_quiescent=job.adapter.is_quiescent
                        ):
                            return bool(job.adapter.close())

                    job.closing = self._own(
                        asyncio.create_task(asyncio.to_thread(close))
                    )
                ready, _ = await asyncio.wait({job.closing}, timeout=10)
                if not ready:
                    job.closing.add_done_callback(
                        lambda _: self._own(
                            asyncio.create_task(self._late_cleanup(job))
                        )
                    )
                    return False
                try:
                    closed = job.closing.result()
                except Exception:
                    job.closing = None
                    raise
                if not closed or not job.adapter.is_quiescent():
                    job.closing = None
                    return False
            job.released = bool(job.lease.release())
            return job.released

    @staticmethod
    def _restore_outcome(job: EvaluationJob) -> None:
        job.state.update(
            status="cancelled" if job.cancelled else (job.target_status or "failed"),
            error="cancelled" if job.cancelled else job.target_error,
        )

    async def _late_cleanup(self, job: EvaluationJob) -> None:
        try:
            if await self._cleanup(job):
                self._restore_outcome(job)
                self._save(job)
        except Exception:
            self.store.terminal(
                job.state["id"], "cleanup_pending", "runtime_quiescence_unconfirmed"
            )

    @staticmethod
    def _reason(exc: Exception) -> str:
        code = getattr(exc, "code", "")
        if code in {"invalid_format", "illegal_action"}:
            return code
        if "context" in code:
            return "context_limit"
        if code in {
            "generation_timeout",
            "generation_deadline_exceeded",
            "run_deadline_exceeded",
        }:
            return "decision_timeout"
        if code == "run_cancelled":
            return "cancelled"
        if code in {
            "payload_too_large",
            "storage_full",
            "run_storage_full",
            "disk_space_low",
        }:
            return "storage_full"
        return "runtime_error"

    async def _execute(self, job: EvaluationJob) -> None:
        request = EvaluationRequest(**job.state["config"]["request"])
        try:
            from .sessions import SessionDriver

            self._check(job)
            job.adapter = self.runner.adapter_factory(request.model_id, job.lease)
            receipt = await self._work(job, lambda: job.adapter.load(job.deadline))
            job.state["runtime_receipt"] = receipt
            job.state["status"] = "running"
            self._save(job)
            block = None
            block_failed = False
            for item in job.state["episodes"]:
                if item["status"] != "pending":
                    continue
                self._check(job)
                if block != item["block_id"]:
                    block = item["block_id"]
                    block_failed = False
                    job.feedback.clear()
                    job.session = SessionDriver(
                        job.adapter,
                        request.observation_mode,
                        request.episode_memory,
                        request.max_context_tokens,
                    )
                if block_failed:
                    item.update(status="skipped", reason_code="block_failed")
                    self._save(job)
                    continue
                await self._work(job, lambda: job.session.begin_episode())
                await self._episode(job, item, request)
                if request.episode_memory == "carry" and (
                    item["status"] != "game_completed" or item.get("reflection_error")
                ):
                    block_failed = True
            job.state["status"] = "completed"
        except asyncio.CancelledError:
            job.cancelled = True
            job.lease.cancel()
            job.state.update(status="interrupted", error="process_stopping")
        except Exception as exc:
            code = self._reason(exc)
            job.state.update(
                status="cancelled" if code == "cancelled" else "failed", error=code
            )
            for item in job.state["episodes"]:
                if item["status"] == "running":
                    item.update(status=code, reason_code=code, ended_at=time.time())
                elif item["status"] == "pending":
                    item.update(status="skipped", reason_code=code)
        finally:
            job.target_status = job.state["status"]
            job.target_error = job.state.get("error")
            job.state["status"] = "cleanup_pending"
            job.state["ended"] = time.time()
            try:
                if await self._cleanup(job):
                    self._restore_outcome(job)
                else:
                    job.state.update(
                        status="cleanup_pending", error="runtime_quiescence_unconfirmed"
                    )
            except Exception:
                job.state.update(
                    status="cleanup_pending", error="runtime_quiescence_unconfirmed"
                )
            try:
                self._save(job)
            except Exception:
                self.store.terminal(
                    job.state["id"],
                    job.state["status"],
                    job.state.get("error") or "storage_full",
                )

    async def _response(
        self,
        job: EvaluationJob,
        item: dict[str, Any],
        player: str,
        observation: dict[str, Any],
        request: EvaluationRequest,
        purpose: str = "action",
    ) -> tuple[dict[str, Any], Any]:
        applied = job.state["config"].get(
            "generation_planned", job.state["config"].get("generation_applied")
        )
        params = GenerationParameters(
            max_new_tokens=min(64, request.max_new_tokens)
            if purpose == "reflection"
            else request.max_new_tokens,
            max_context_tokens=request.max_context_tokens,
            temperature=applied["temperature"],
            top_p=applied["top_p"],
            seed=seeded(
                request.seed,
                item["case_id"],
                item["episode"],
                player,
                len(item["decisions"]),
                purpose,
            ),
            profile="structured",
            num_steps=request.num_steps,
        )
        event_id = ":".join(
            str(v)
            for v in (
                item["block_id"],
                item["attempt"],
                item["case_id"],
                item["episode"],
                len(item["decisions"]),
                purpose,
            )
        )
        action_instruction = (
            "Return exactly one JSON object describing your chosen action. "
            "No markdown or additional text."
        )
        if request.response_mode == "mapped" and purpose == "action":
            if observation.get("game") == "nim":
                action_instruction = (
                    "Reply only: heap=H take=N. H is the zero-based heap index; "
                    "N is the positive number of stones to remove. "
                    "Use actual numbers. No explanation or reasoning."
                )
            elif observation.get("game") == "memory":
                action_instruction = (
                    "Reply only: cards=I,J. I and J must be different unmatched "
                    "indices 0-15, zero-based row-major. Give both actual indices, "
                    "not just 'match'. No explanation or reasoning."
                )
        reflection_instruction = (
            "Write a short private improvement note based only on your observed game. "
            "Do not give a step-by-step reasoning transcript."
        )
        observation = copy.deepcopy(observation)
        if purpose == "action":
            if job.session.has_history(player):
                observation.pop("rules", None)
                observation.pop("action_schema", None)
            if observation.get("game") == "memory" and "legal_actions" in observation:
                observation.pop("legal_actions")
                observation["legal_action_space"] = {
                    "cards": {
                        "choose": 2,
                        "distinct": True,
                        "unmatched": [
                            i for i in range(16) if i not in observation["matched"]
                        ],
                    }
                }
        payload = {
            "event_id": event_id,
            "episode_id": item["case_id"] + ":" + str(item["episode"]),
            "player": player,
            "purpose": purpose,
            "instruction": action_instruction
            if purpose == "action"
            else reflection_instruction,
            "observation": observation,
        }
        if purpose == "action" and player in job.feedback:
            payload["previous_episode"] = job.feedback.pop(player)
        wire_payload = payload
        if (
            request.response_mode == "mapped"
            and purpose == "action"
            and observation.get("game") in {"nim", "memory"}
        ):
            # Identifiers stay in the journal; all game evidence stays on the wire.
            wire_payload = {
                key: value
                for key, value in payload.items()
                if key not in {"event_id", "episode_id"}
            }
            if job.session.has_history(player):
                wire_payload["instruction"] = (
                    "Reply only: heap=H take=N."
                    if observation["game"] == "nim"
                    else "Reply only: cards=I,J."
                )
        encoded = json.dumps(
            wire_payload,
            ensure_ascii=False,
            separators=(",", ":")
            if request.response_mode == "mapped"
            else (", ", ": "),
        )
        started = time.monotonic()
        deadline = min(job.deadline, time.monotonic() + request.decision_timeout_s)
        try:
            result = await self._work(
                job,
                lambda: job.session.generate(player, encoded, params, deadline),
                deadline,
            )
            if not result.quiescent:
                raise LabError("runtime_quiescence_unconfirmed")
            if result.stop_reason in {"cancelled", "deadline"}:
                raise LabError(
                    "run_cancelled" if job.cancelled else "generation_timeout"
                )
        except Exception as exc:
            item["decisions"].append(
                {
                    "actor": "model",
                    "player": player,
                    "purpose": purpose,
                    "observation": payload,
                    "response": None,
                    "raw_response": None,
                    "action": None,
                    "valid": False,
                    "error": self._reason(exc),
                    "seconds": time.monotonic() - started,
                    "usage": {
                        "input_tokens": None,
                        "output_tokens": None,
                        "ttft_s": None,
                        "peak_vram_bytes": None,
                        "effective_parameters": None,
                    },
                    "assessment": {},
                }
            )
            raise
        record = {
            "actor": "model",
            "player": player,
            "purpose": purpose,
            "observation": payload,
            "response": result.text,
            "raw_response": result.raw_text,
            "action": None,
            "valid": False,
            "error": None,
            "seconds": time.monotonic() - started,
            "usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "ttft_s": result.ttft_s,
                "peak_vram_bytes": result.peak_vram_bytes,
                "effective_parameters": dict(result.effective_parameters),
            },
            "assessment": {},
        }
        return record, result

    async def _episode(
        self, job: EvaluationJob, item: dict[str, Any], request: EvaluationRequest
    ) -> None:
        import random

        from .games import make_environment
        from .manifest import CASES
        from .references import assess, reference_action

        case = next(c for c in CASES if c["id"] == item["case_id"])
        try:
            game_config = copy.deepcopy(case["config"])
            if request.opponent == "model" and request.swap_sides:
                game_config["starting_player"] = item["player"]
            item["game_config"] = game_config
            env = make_environment(case["game"], game_config, item["seed"])
        except Exception:
            item.update(
                status="environment_error",
                reason_code="environment_error",
                started_at=time.time(),
                ended_at=time.time(),
            )
            self._save(job)
            return
        item.update(status="running", started_at=time.time())
        self._save(job)
        try:
            for action_index in range(item["max_actions"]):
                self._check(job)
                if env.finished:
                    break
                player = env.current_player
                observation = env.observation(player, request.legal_moves == "listed")
                is_model = (
                    env.game in {"memory", "sokoban"}
                    or request.opponent == "model"
                    or player == item["player"]
                )
                if is_model:
                    record, result = await self._response(
                        job, item, player, observation, request
                    )
                    item["decisions"].append(record)
                    from .actions import parse_action

                    try:
                        action, mapping = parse_action(
                            result.text, env.game, request.response_mode
                        )
                        record["response_mapping"] = mapping
                    except LabError:
                        record["error"] = "invalid_format"
                        raise
                else:
                    start = time.monotonic()
                    action = reference_action(
                        env,
                        request.opponent,
                        random.Random(
                            seeded(
                                request.seed,
                                item["case_id"],
                                item["episode"],
                                player,
                                action_index,
                            )
                        ),
                    )
                    record = {
                        "actor": "reference",
                        "player": player,
                        "observation": observation,
                        "response": None,
                        "action": action,
                        "valid": False,
                        "seconds": time.monotonic() - start,
                        "usage": {},
                        "assessment": {},
                    }
                    item["decisions"].append(record)
                record["action"] = action
                try:
                    assessment = assess(env, player, action)
                    env.step(player, action)
                except LabError as exc:
                    code = (
                        "illegal_action"
                        if exc.code == "illegal_action"
                        else "environment_error"
                    )
                    record["error"] = code
                    raise LabError(
                        code, 422 if code == "illegal_action" else 500
                    ) from exc
                except Exception:
                    record["error"] = "environment_error"
                    raise LabError("environment_error", 500) from None
                record.update(valid=True, assessment=assessment)
                self._save(job)
            if not env.finished:
                item.update(status="action_limit", reason_code="action_limit")
            else:
                result = env.result()
                if env.game in {"tic_tac_toe", "nim"} and request.opponent != "model":
                    result["success"] = result.get("winner") == item["player"]
                item.update(status="game_completed", reason_code=None, result=result)
                participants = (
                    ["A", "B"] if request.opponent == "model" else [item["player"]]
                )
                terminal_state = env.public_state()
                for key in ("rules", "action_schema", "result"):
                    terminal_state.pop(key, None)
                feedback = {
                    "episode_id": item["case_id"] + ":" + str(item["episode"]),
                    "final_state": terminal_state,
                    "result": {k: result.get(k) for k in ("winner", "draw", "success")},
                }
                if request.episode_memory == "carry":
                    job.feedback = {p: copy.deepcopy(feedback) for p in participants}
                if request.reflection == "episode_note":
                    for player in participants:
                        try:
                            note, _ = await self._response(
                                job,
                                item,
                                player,
                                feedback,
                                request,
                                "reflection",
                            )
                            note["valid"] = True
                            item["decisions"].append(note)
                            job.feedback.pop(player, None)
                        except LabError as exc:
                            if job.cancelled:
                                raise
                            item["reflection_error"] = self._reason(exc)
        except LabError as exc:
            code = (
                "environment_error"
                if exc.code == "environment_error"
                else self._reason(exc)
            )
            item.update(status=code, reason_code=code)
            if code in {"cancelled", "storage_full", "decision_timeout"}:
                raise
        finally:
            item["ended_at"] = time.time()
            self._save(job)

    async def close(self) -> None:
        self.closed = True
        for eid, job in list(self.jobs.items()):
            if job.task and not job.task.done():
                await self.cancel(eid)
        pending = {j.task for j in self.jobs.values() if j.task and not j.task.done()}
        if pending:
            await asyncio.wait(pending, timeout=12)
