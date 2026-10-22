"""Resume at durable fresh episodes or whole carry blocks, never fake continuity."""

from __future__ import annotations

import copy
from dataclasses import asdict, replace

import pytest
from test_game_service import eval_rig as shared_eval_rig
from test_game_service import finish, request

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation import manifest
from venom_module_cooperation_lab.evaluation.service import EvaluationService
from venom_module_cooperation_lab.runner import OWNER

eval_rig = shared_eval_rig


def qualify_new_fixture(service, specs, **changes):
    specs[0] = replace(specs[0], **changes)
    service.runner.store.put_document(
        "qualifications",
        specs[0].model_id,
        {
            **asdict(specs[0]),
            "qualified": True,
            "receipt_id": "cpu-fixture-not-model-qualification",
        },
        owner=OWNER,
    )


@pytest.mark.asyncio
async def test_fresh_resume_preserves_completed_episode_and_retries_only_failed(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["fail_at"] = {2}
    row, _ = await service.start(request(repetitions=2), "fresh")
    first = await finish(service, row)
    assert [r["status"] for r in first["episodes"]] == [
        "game_completed",
        "runtime_error",
    ]
    committed = copy.deepcopy(first["episodes"][0])
    settings["fail_at"] = set()
    resumed = await service.resume(row["id"])
    assert resumed["id"] == row["id"]
    final = await finish(service, resumed)
    assert final["episodes"][0] == committed
    assert [r["attempt"] for r in final["episodes"]] == [1, 2]
    assert [r["status"] for r in final["episodes"]] == [
        "game_completed",
        "game_completed",
    ]
    assert len(adapters) == 2 and adapters[0].calls == 2 and adapters[1].calls == 1
    assert final["block_restarts"] == 1
    assert len(final["attempt_history"]) == 1
    assert final["attempt_history"][0][0]["status"] == "runtime_error"
    assert final["progress"] == {
        "planned": 2,
        "started": 2,
        "terminal": 2,
        "success": 2,
        "skipped": 0,
    }
    with pytest.raises(LabError, match="nothing_to_resume"):
        await service.resume(row["id"])


@pytest.mark.asyncio
async def test_carry_resume_archives_and_restarts_whole_block_including_earlier_success(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    settings["fail_at"] = {2}
    row, _ = await service.start(
        request(repetitions=3, episode_memory="carry"), "carry"
    )
    first = await finish(service, row)
    assert [r["status"] for r in first["episodes"]] == [
        "game_completed",
        "runtime_error",
        "skipped",
    ]
    assert first["episodes"][2]["reason_code"] == "block_failed"
    settings["fail_at"] = set()
    resumed = await service.resume(row["id"])
    final = await finish(service, resumed)
    assert all(
        r["status"] == "game_completed" and r["attempt"] == 2 for r in final["episodes"]
    )
    assert adapters[1].calls == 3
    assert len(final["attempt_history"]) == 1
    assert final["attempt_history"][0] == first["episodes"]
    assert final["block_restarts"] == 1
    # A new driver starts new memory, without pretending native state survived.
    assert adapters[1].resets[0] is None
    second_history = adapters[1].recorded[1][1]
    assert len(second_history) > len(adapters[1].recorded[0][1])


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["manifest", "model"])
async def test_resume_rejects_changed_manifest_or_qualified_model_identity(
    eval_rig, monkeypatch, changed
):
    service, adapters, settings, specs = eval_rig
    settings["fail_at"] = {1}
    row, _ = await service.start(request(), "immutable")
    await finish(service, row)
    if changed == "manifest":
        updated = copy.deepcopy(manifest.CASES)
        updated[0]["seed"] += 1
        monkeypatch.setattr(manifest, "CASES", updated)
    else:
        qualify_new_fixture(service, specs, digest="new-digest")
    with pytest.raises(LabError, match="evaluation_identity_changed"):
        await service.resume(row["id"])
    assert len(adapters) == 1
    assert service.runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_resume_guard_failure_releases_lease_and_leaves_original_snapshot(
    eval_rig, monkeypatch
):
    service, adapters, settings, _ = eval_rig
    settings["fail_at"] = {1}
    row, _ = await service.start(request(), "guard")
    original = await finish(service, row)

    def fail(_state):
        raise LabError("storage_full", 507)

    monkeypatch.setattr(service.store, "save", fail)
    with pytest.raises(LabError, match="storage_full"):
        await service.resume(row["id"])
    assert service.snapshot(row["id"])["episodes"] == original["episodes"]
    assert (
        len(adapters) == 1
        and service.runner.admission.snapshot()["status"] == "available"
    )


@pytest.mark.asyncio
async def test_resume_is_rejected_while_active_and_cancelled_pending_episodes_restart(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    row, _ = await service.start(request(repetitions=2), "queued-resume")
    with pytest.raises(LabError, match="evaluation_active"):
        await service.resume(row["id"])
    await service.cancel(row["id"])
    cancelled = await finish(service, row)
    assert all(r["status"] == "skipped" for r in cancelled["episodes"])
    settings["fail_at"] = set()
    resumed = await service.resume(row["id"])
    final = await finish(service, resumed)
    assert all(
        r["status"] == "game_completed" and r["attempt"] == 2 for r in final["episodes"]
    )
    assert len(adapters) <= 2


@pytest.mark.asyncio
async def test_recovery_from_durable_snapshot_does_not_rerun_committed_fresh_episode(
    eval_rig,
):
    service, adapters, settings, _ = eval_rig
    row, _ = await service.start(request(repetitions=2), "restart")
    first = await finish(service, row)
    durable = copy.deepcopy(first)
    durable.update(status="running")
    durable["episodes"][1].update(status="running", result=None)
    service.store.save(durable)
    service.jobs.clear()
    service.store.recover()
    recovered = service.store.get(row["id"])
    assert recovered["status"] == "interrupted"
    restarted = EvaluationService(service.runner)
    resumed = await restarted.resume(row["id"])
    final = await finish(restarted, resumed)
    assert final["episodes"][0] == first["episodes"][0]
    assert final["episodes"][1]["attempt"] == 2
    assert len(adapters) == 2 and adapters[1].calls == 1
    await restarted.close()


@pytest.mark.asyncio
async def test_native_carry_fixture_uses_separate_backend_cursors_and_one_initial_reset(
    eval_rig,
):
    service, adapters, _, specs = eval_rig
    qualify_new_fixture(service, specs, architecture="rwkv7", runtime="rwkv-chat-v2")
    row, _ = await service.start(
        request(
            repetitions=3, episode_memory="carry", observation_mode="native_incremental"
        ),
        "native",
    )
    final = await finish(service, row)
    assert all(r["status"] == "game_completed" for r in final["episodes"])
    adapter = adapters[0]
    assert adapter.resets == [None]
    assert [len(history) for _, history, _ in adapter.recorded] == [1, 3, 5]
    effective = [
        r["decisions"][0]["usage"]["effective_parameters"] for r in final["episodes"]
    ]
    assert [r["event_cursor"] for r in effective] == [1, 2, 3]
    assert [r["context_mode"] for r in effective] == ["prefill", "append", "append"]
    assert all(r["memory_kind"] == "native_state" for r in effective)


@pytest.mark.asyncio
async def test_carry_reflection_runtime_failure_can_restart_block_without_stale_error(
    eval_rig,
):
    service, _, settings, _ = eval_rig
    settings["fail_at"] = {2}
    row, _ = await service.start(
        request(repetitions=2, episode_memory="carry", reflection="episode_note"),
        "reflect-resume",
    )
    first = await finish(service, row)
    assert first["episodes"][0]["reflection_error"] == "runtime_error"
    settings["fail_at"] = set()
    resumed = await service.resume(row["id"])
    final = await finish(service, resumed)
    assert all(
        r["status"] == "game_completed" and r["attempt"] == 2 for r in final["episodes"]
    )
    assert all(not r.get("reflection_error") for r in final["episodes"])


@pytest.mark.asyncio
async def test_storage_reclaim_resume_preserves_committed_fresh_episode(
    eval_rig,
):
    service, _, settings, _ = eval_rig
    settings.update(fail_at={2}, failure=LabError("storage_full", 507))
    row, _ = await service.start(request(repetitions=2), "storage-resume")
    first = await finish(service, row)
    assert first["episodes"][0]["status"] == "game_completed"
    assert first["episodes"][1]["status"] == "storage_full"
    settings["fail_at"] = set()
    resumed = await service.resume(row["id"])
    final = await finish(service, resumed)
    assert final["episodes"][0] == first["episodes"][0]
    assert final["episodes"][1]["status"] == "game_completed"
