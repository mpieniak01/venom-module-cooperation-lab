"""CPU-only evaluation orchestration, private observations and lease ownership."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from dataclasses import asdict, replace

import pytest
from conftest import SPEC, FakeAdapter
from venom_core.services.runtime_admission import RuntimeAdmission

from venom_module_cooperation_lab.adapters.base import GenerationResult
from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.config import EvaluationRequest
from venom_module_cooperation_lab.evaluation.service import EvaluationService
from venom_module_cooperation_lab.runner import OWNER, LabRunner
from venom_module_cooperation_lab.storage import LabStore

EVAL_SPEC = replace(SPEC, architecture="hrm_text", runtime="cpu-fixture-hf-v1")


class GameAdapter(FakeAdapter):
    """Action fixture consumes only observations; never receives oracle objects."""

    def __init__(self, lease, spec, settings):
        super().__init__(lease)
        self.spec = spec
        self.settings = settings
        self.resets = []
        self.calls = 0
        self.loads = 0
        self.cursors = {"A": 0, "B": 0}

    def load(self, deadline):
        self.loads += 1
        return super().load(deadline)

    def reset(self, participant=None):
        self.resets.append(participant)
        if participant is None:
            self.cursors = {"A": 0, "B": 0}
        else:
            self.cursors[participant] = 0
        return {"state": "reset"}

    def generate(self, participant, messages, parameters, deadline):
        with self.lease.operation(kind="generation"):
            self.calls += 1
            self.recorded.append((participant, copy.deepcopy(messages), parameters))
            if self.settings.get("block"):
                self._pause()
            if self.calls in self.settings.get("fail_at", set()):
                raise self.settings.get("failure", LabError("fixture_runtime_error"))
            event = json.loads(messages[-1].content)
            if event["purpose"] == "reflection":
                text = "I will compare my next move with the observed outcome."
            else:
                observation = event["observation"]
                legal = observation.get("legal_actions", [])
                if self.settings.get("response") is not None:
                    text = self.settings["response"]
                elif legal:
                    text = json.dumps(legal[0])
                elif observation["game"] == "memory":
                    # A hidden-legal fixture still follows the publicly stated rules.
                    remaining = [
                        i for i in range(16) if i not in observation["matched"]
                    ]
                    text = json.dumps({"cards": remaining[:2]})
                else:
                    raise AssertionError("fixture_requires_visible_actions")
            mode = "append" if self.cursors[participant] else "prefill"
            self.cursors[participant] += 1
            return GenerationResult(
                text=text,
                raw_text=text,
                input_tokens=20,
                output_tokens=8,
                ttft_s=0.001,
                peak_vram_bytes=self.settings.get("peak_vram_bytes"),
                generation_s=0.002,
                stop_reason=self.settings.get("stop_reason", "length"),
                effective_parameters={
                    "context_mode": mode,
                    "temperature": parameters.temperature,
                    "top_p": parameters.top_p,
                    "num_steps": parameters.num_steps,
                },
                quiescent=self.settings.get("quiescent", True),
            )


@pytest.fixture
async def eval_rig(tmp_path):
    settings = {}
    specs = [EVAL_SPEC]
    adapters = []

    def access(owner, _operation):
        if owner != OWNER:
            raise PermissionError("untrusted_owner")

    store = LabStore(tmp_path / "module", lambda _operation: None, access)
    store.open()
    store.put_document(
        "qualifications",
        EVAL_SPEC.model_id,
        {
            **asdict(EVAL_SPEC),
            "qualified": True,
            "receipt_id": "cpu-fixture-not-model-qualification",
        },
        owner=OWNER,
    )
    admission = RuntimeAdmission(tmp_path / "admission.sqlite3", enabled=True)

    def factory(model, lease):
        assert model == specs[0].model_id
        adapter = GameAdapter(lease, specs[0], settings)
        adapters.append(adapter)
        return adapter

    runner = LabRunner(store, admission, lambda: specs, factory, cleanup_seconds=0.3)
    service = EvaluationService(runner)
    yield service, adapters, settings, specs
    for adapter in adapters:
        adapter.released.set()
    await service.close()
    if service.tasks:
        await asyncio.wait(service.tasks, timeout=2)
    await runner.close()
    store.close()


def request(**overrides):
    return EvaluationRequest(
        **{
            "model_id": EVAL_SPEC.model_id,
            "case_ids": ["nim-last-stone-v1"],
            "swap_sides": False,
            **overrides,
        }
    )


async def finish(service, row):
    await asyncio.wait_for(asyncio.shield(service.jobs[row["id"]].task), timeout=4)
    return service.snapshot(row["id"])


async def wait_entered(adapters):
    async with asyncio.timeout(1):
        while not adapters or not adapters[-1].entered.is_set():
            await asyncio.sleep(0.001)
    return adapters[-1]


@pytest.mark.asyncio
async def test_evaluation_completed_roundtrip_idempotency_and_no_hidden_retries(
    eval_rig,
):
    service, adapters, _, _ = eval_rig
    first, second = await asyncio.gather(
        service.start(request(), "same"), service.start(request(), "same")
    )
    assert first[0]["id"] == second[0]["id"]
    assert [first[1], second[1]] == [True, False]
    final = await finish(service, first[0])
    assert final["status"] == "completed"
    assert final["episodes"][0]["status"] == "game_completed"
    assert final["episodes"][0]["result"]["winner"] == "A"
    assert final["episodes"][0]["result"]["success"]
    assert len(adapters) == 1 and adapters[0].calls == 1 and adapters[0].closed
    retry, created = await service.start(request(), "same")
    assert not created and retry["id"] == final["id"]
    with pytest.raises(LabError, match="idempotency_conflict"):
        await service.start(request(seed=3), "same")
    assert service.store.get(final["id"])["episodes"] == final["episodes"]
    final["episodes"].clear()
    assert len(service.snapshot(first[0]["id"])["episodes"]) == 1
    assert service.runner.admission.snapshot()["status"] == "available"
    assert service.list()[0]["id"] == first[0]["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,status",
    [
        ("not JSON", "invalid_format"),
        ("[]", "invalid_format"),
        ('{"heap":NaN,"take":1}', "invalid_format"),
        ('{"heap":0,"take":2}', "illegal_action"),
        ('{"heap":0,"take":1,"extra":2}', "illegal_action"),
    ],
)
async def test_model_errors_end_episode_once_and_remain_in_report(
    eval_rig, text, status
):
    service, adapters, settings, _ = eval_rig
    settings["response"] = text
    row, _ = await service.start(request(), "bad")
    final = await finish(service, row)
    episode = final["episodes"][0]
    assert episode["status"] == status
    assert len(episode["decisions"]) == 1 and adapters[0].calls == 1
    assert episode["decisions"][0]["response"] == text
    assert episode["decisions"][0]["error"] == status
    assert final["summary"]["by_game"][0]["model_errors"] == 1
    assert final["summary"]["by_game"][0]["infrastructure_errors"] == 0
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_side_swap_bots_and_private_model_observations(eval_rig):
    service, adapters, _, _ = eval_rig
    row, _ = await service.start(request(swap_sides=True), "sides")
    final = await finish(service, row)
    assert len(final["episodes"]) == 2
    one, two = final["episodes"]
    assert one["result"]["success"] and not two["result"]["success"]
    assert one["player"] == "A" and two["player"] == "B"
    assert two["decisions"][0]["actor"] == "reference"
    assert adapters[0].calls == 1
    record = one["decisions"][0]
    prompt = record["observation"]
    assert "assessment" not in prompt and "reference_version" not in prompt
    assert "optimal" not in json.dumps(prompt)
    assert record["assessment"]["winning_position_before"]


@pytest.mark.asyncio
async def test_memory_observations_exclude_deck_oracle_and_history_can_end_honestly(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["fail_at"] = {2}
    row, _ = await service.start(request(case_ids=["memory-seed17-v1"]), "memory")
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == "runtime_error"
    first = json.loads(adapters[0].recorded[0][1][-1].content)["observation"]
    second = json.loads(adapters[0].recorded[1][1][-1].content)["observation"]
    assert first["board"] == [None] * 16
    assert first["last_reveal"] == []
    assert len(second["last_reveal"]) == 2
    assert "_cards" not in first and "revealed_knowledge" not in first
    assert "known_pairs_missed" not in first["result"]
    assert "reference_version" not in json.dumps(first)


@pytest.mark.asyncio
async def test_preflight_rejects_unsupported_before_loading_and_reports_capabilities(
    eval_rig,
):
    service, adapters, _, _ = eval_rig
    assert service.capabilities()["ready"]
    assert set(service.capabilities()["games"]) == {
        "tic_tac_toe",
        "nim",
        "memory",
        "sokoban",
    }
    cases = [
        (
            request(observation_mode="native_incremental"),
            "unsupported_observation_mode",
        ),
        (request(action_constraint="masked"), "unsupported_action_constraint"),
        (request(num_steps=16), "unsupported_compute_steps"),
        (request(reflection="episode_note"), "reflection_requires_carry"),
        (request(opponent="remembering"), "unsupported_reference"),
        (
            request(case_ids=["memory-seed17-v1"], opponent="model"),
            "solo_game_has_no_opponent",
        ),
    ]
    for index, (config, code) in enumerate(cases):
        checked = service.preflight(config)
        assert not checked["supported"] and code in checked["reason_codes"]
        with pytest.raises(LabError, match=code):
            await service.start(config, "unsupported" + str(index))
    assert adapters == [] and service.store.list() == []
    service.closed = True
    assert not service.capabilities()["ready"]
    with pytest.raises(LabError, match="module_stopping"):
        await service.start(request(), "closed")


@pytest.mark.asyncio
async def test_cancel_queued_never_loads_and_is_idempotent(eval_rig):
    service, adapters, _, _ = eval_rig
    row, _ = await service.start(request(), "cancel-queued")
    assert (await service.cancel(row["id"]))["status"] == "cancelling"
    final = await finish(service, row)
    assert final["status"] == "cancelled"
    assert all(adapter.loads == 0 for adapter in adapters)
    assert (await service.cancel(row["id"]))["status"] == "cancelled"
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_cancel_live_generation_keeps_owned_thread_and_lease_until_quiescent(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["block"] = True
    row, _ = await service.start(request(repetitions=2), "cancel-live")
    adapter = await wait_entered(adapters)
    adapter.ignore_cancel = True
    job = service.jobs[row["id"]]
    await service.cancel(row["id"])
    assert service.runner.admission.snapshot()["status"] != "available"
    assert job.work is not None and not job.work.cancelled()
    adapter.released.set()
    final = await finish(service, row)
    assert final["status"] == "cancelled" and adapter.closed and adapter.cancelled
    assert final["episodes"][1]["status"] == "skipped"
    assert adapter.calls == 1
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_quota_or_guard_failure_releases_acquired_lease_without_loading(eval_rig):
    service, adapters, _, _ = eval_rig
    row, _ = await service.start(request(), "one")
    await finish(service, row)
    service.runner.store.limits = replace(service.runner.store.limits, max_runs=1)
    with pytest.raises(LabError, match="run_limit_reached"):
        await service.start(request(), "two")
    assert len(adapters) == 1
    assert service.runner.admission.snapshot()["status"] == "available"
    assert len(service.store.list()) == 1
    with pytest.raises(LabError, match="invalid_id"):
        await service.start(request(), "../bad")


@pytest.mark.asyncio
async def test_store_validation_recovery_retention_and_mutation_guards(eval_rig):
    service, _, _, _ = eval_rig
    assert not service.store.exists() and service.store.list() == []
    service.store.recover()
    with pytest.raises(LabError, match="evaluation_not_found"):
        service.store.get("absent")
    row, _ = await service.start(request(), "stored")
    final = await finish(service, row)
    service.jobs.clear()
    state = service.store.get(row["id"])
    state.update(status="running")
    service.store.save(state)
    service.store.recover()
    recovered = service.store.get(row["id"])
    assert (
        recovered["status"] == "interrupted"
        and recovered["error"] == "process_restarted"
    )
    # Quota validation must happen without changing a previously durable result.
    huge = copy.deepcopy(final)
    huge["padding"] = "x" * service.runner.store.limits.run_bytes
    with pytest.raises(LabError, match="payload_too_large"):
        service.store.save(huge)
    assert service.store.get(row["id"])["episodes"] == final["episodes"]
    original = service.runner.store._access
    service.runner.store._access = lambda *_: (_ for _ in ()).throw(
        PermissionError("denied")
    )
    with pytest.raises(PermissionError, match="denied"):
        service.store.get(row["id"])
    service.runner.store._access = original
    old = copy.deepcopy(state)
    old.update(
        id="old-eval",
        key="old-key",
        status="completed",
        created=time.time() - 30 * 86400,
    )
    service.store.create(old)
    # Retention deletes old terminal rows only on the next mutation.
    new = copy.deepcopy(state)
    new.update(id="new-eval", key="new-key", status="running")
    service.store.create(new)
    assert {r["id"] for r in service.store.list()} == {row["id"], "new-eval"}
    service.store.terminal("new-eval", "failed", "fixture")
    assert service.store.get("new-eval")["error"] == "fixture"


@pytest.mark.asyncio
async def test_reflection_is_private_explicit_costed_and_greedy_is_not_sampled(
    eval_rig,
):
    service, adapters, _, _ = eval_rig
    row, _ = await service.start(
        request(repetitions=2, episode_memory="carry", reflection="episode_note"),
        "reflect",
    )
    final = await finish(service, row)
    assert all(r["status"] == "game_completed" for r in final["episodes"])
    assert adapters[0].calls == 4
    purposes = [d["purpose"] for r in final["episodes"] for d in r["decisions"]]
    assert purposes == ["action", "reflection", "action", "reflection"]
    assert all(p.temperature == 0 and p.top_p == 1 for _, _, p in adapters[0].recorded)
    feedback = final["episodes"][0]["decisions"][1]["observation"]["observation"]
    assert feedback["result"]["winner"] == "A"
    assert feedback["final_state"]["heaps"] == [0]
    assert all(
        "assessment" not in d["observation"]["observation"]
        for r in final["episodes"]
        for d in r["decisions"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure,status",
    [
        (LabError("context_budget_exceeded"), "context_limit"),
        (LabError("storage_full", 507), "storage_full"),
        (LabError("generation_deadline_exceeded", 408), "decision_timeout"),
    ],
)
async def test_runtime_failures_are_separate_from_model_actions(
    eval_rig, failure, status
):
    service, adapters, settings, _ = eval_rig
    settings.update(fail_at={1}, failure=failure)
    row, _ = await service.start(request(), "runtime-failure")
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == status
    assert adapters[0].calls == 1 and adapters[0].closed
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setting,value,status",
    [
        ("quiescent", False, "runtime_error"),
        ("stop_reason", "deadline", "decision_timeout"),
    ],
)
async def test_backend_receipts_do_not_masquerade_as_completed_actions(
    eval_rig, setting, value, status
):
    service, _, settings, _ = eval_rig
    settings[setting] = value
    row, _ = await service.start(request(), "bad-receipt")
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == status
    assert final["episodes"][0]["decisions"] == []
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_deadline_cancels_own_generation_and_releases_after_worker_quiescence(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["block"] = True
    row, _ = await service.start(request(decision_timeout_s=1), "deadline")
    final = await finish(service, row)
    assert final["status"] == "failed" and final["error"] == "decision_timeout"
    assert adapters[0].cancelled and adapters[0].closed
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_wall_deadline_before_load_is_honest_and_preflight_unknown_model(
    eval_rig,
):
    service, adapters, _, _ = eval_rig
    invalid = request(model_id="missing-model")
    assert "model_not_allowed" in service.preflight(invalid)["reason_codes"]
    row, _ = await service.start(request(), "expired")
    service.jobs[row["id"]].deadline = time.monotonic() - 1
    final = await finish(service, row)
    assert final["status"] == "failed" and final["error"] == "decision_timeout"
    assert not adapters


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [LabError("environment_solver_limit", 422), ValueError("fixture")]
)
async def test_oracle_failure_is_environment_error_and_never_model_illegal(
    eval_rig, monkeypatch, failure
):
    from venom_module_cooperation_lab.evaluation import references

    service, _, _, _ = eval_rig

    def fail(*_args):
        raise failure

    monkeypatch.setattr(references, "assess", fail)
    row, _ = await service.start(request(), "oracle-failure")
    final = await finish(service, row)
    episode = final["episodes"][0]
    assert episode["status"] == "environment_error"
    assert episode["decisions"][0]["error"] == "environment_error"
    assert final["summary"]["by_game"][0]["infrastructure_errors"] == 1
    assert final["summary"]["by_game"][0]["model_errors"] == 0


@pytest.mark.asyncio
async def test_environment_setup_failure_is_reported_without_generation(
    eval_rig, monkeypatch
):
    from venom_module_cooperation_lab.evaluation import games

    service, adapters, _, _ = eval_rig

    def fail(*_args):
        raise ValueError("broken fixture")

    monkeypatch.setattr(games, "make_environment", fail)
    row, _ = await service.start(request(), "environment")
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == "environment_error"
    assert adapters[0].calls == 0


@pytest.mark.asyncio
async def test_action_limit_and_model_model_rounds_remain_explicit(
    eval_rig, monkeypatch
):
    from venom_module_cooperation_lab.evaluation import manifest

    service, adapters, _, _ = eval_rig
    cases = copy.deepcopy(manifest.CASES)
    next(c for c in cases if c["id"] == "memory-seed17-v1")["max_actions"] = 2
    monkeypatch.setattr(manifest, "CASES", cases)
    row, _ = await service.start(request(case_ids=["memory-seed17-v1"]), "limit")
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == "action_limit"
    assert adapters[0].calls == 2
    ttt, _ = await service.start(
        request(case_ids=["ttt-opening-v1"], opponent="model"), "two-models"
    )
    game = await finish(service, ttt)
    assert game["episodes"][0]["status"] == "game_completed"
    assert {p for p, _, _ in adapters[1].recorded} == {"A", "B"}
    assert all(d["actor"] == "model" for d in game["episodes"][0]["decisions"])


@pytest.mark.asyncio
async def test_close_stops_active_owned_jobs_and_duplicate_cleanup_is_idempotent(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["block"] = True
    row, _ = await service.start(request(), "shutdown")
    await wait_entered(adapters)
    await service.close()
    final = await finish(service, row)
    assert final["status"] == "cancelled" and service.closed
    assert await service._cleanup(service.jobs[row["id"]])
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_reflection_failure_is_visible_and_stops_carry_block(eval_rig):
    service, _, settings, _ = eval_rig
    settings["fail_at"] = {2}
    row, _ = await service.start(
        request(repetitions=2, episode_memory="carry", reflection="episode_note"),
        "reflect-error",
    )
    final = await finish(service, row)
    assert final["episodes"][0]["status"] == "game_completed"
    assert final["episodes"][0]["reflection_error"] == "runtime_error"
    assert final["episodes"][1]["status"] == "skipped"


@pytest.mark.asyncio
async def test_available_vram_is_retained_and_missing_is_not_zero(eval_rig):
    service, _adapters, settings, _specs = eval_rig
    settings["peak_vram_bytes"] = 12345
    row, _ = await service.start(request(), "vram-receipt")
    result = await finish(service, row)
    assert result["episodes"][0]["decisions"][0]["usage"]["peak_vram_bytes"] == 12345
    assert result["summary"]["by_game"][0]["peak_vram_bytes"] == 12345
