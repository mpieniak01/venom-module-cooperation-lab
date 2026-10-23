from __future__ import annotations

import asyncio
import csv
import io
import json
from dataclasses import asdict, replace

import httpx
import pytest
from conftest import SPEC
from fastapi import FastAPI

from venom_module_cooperation_lab.api.routes import router
from venom_module_cooperation_lab.evaluation.store import EvaluationStore
from venom_module_cooperation_lab.runner import OWNER

BASE = "/api/v1/cooperation-lab/evaluations"


@pytest.fixture
async def evaluation_client(rig, monkeypatch):
    """Use the existing bounded CPU adapter; never load a real model."""
    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "FEATURE_COOPERATION_LAB", True)
    monkeypatch.setattr(SETTINGS, "RUNTIME_ADMISSION_ENABLED", True)
    runner, _adapters = rig
    spec = replace(SPEC, architecture="hrm_text")
    monkeypatch.setattr(runner, "model_catalog", lambda: [spec])
    runner.store.put_document(
        "qualifications",
        spec.model_id,
        {**asdict(spec), "qualified": True, "receipt_id": "cpu-game-fixture"},
        owner=OWNER,
    )
    original = runner.adapter_factory

    def factory(model, lease):
        adapter = original(model, lease)
        adapter.spec = spec
        adapter.reset = lambda _participant=None: {"state": "reset"}
        adapter.responses = ['{"heap":0,"take":1}']
        return adapter

    monkeypatch.setattr(runner, "adapter_factory", factory)
    app = FastAPI()
    app.include_router(router)
    app.state.cooperation_lab_runner = runner
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 4000)),
        base_url="http://localhost:8800",
    ) as client:
        yield client
    service = getattr(app.state, "cooperation_lab_evaluations", None)
    if service is not None:
        await service.close()
        if service.tasks:
            await asyncio.wait(service.tasks, timeout=2)


def payload(**changes):
    return {
        "model_id": SPEC.model_id,
        "case_ids": ["nim-last-stone-v1"],
        "swap_sides": False,
        **changes,
    }


async def finish(client, eid):
    service = client._transport.app.state.cooperation_lab_evaluations
    await asyncio.wait_for(service.jobs[eid].task, timeout=3)
    response = await client.get(f"{BASE}/{eid}")
    assert response.status_code == 200
    return response.json()["evaluation"]


@pytest.mark.asyncio
async def test_game_api_discovery_preflight_and_list_are_observational(
    evaluation_client, rig
):
    runner, adapters = rig
    store = EvaluationStore(runner.store)
    assert not store.exists()
    caps = await evaluation_client.get(BASE + "/capabilities")
    assert caps.status_code == 200
    body = caps.json()
    assert body["manifest_version"] == "suite-v1"
    assert set(body["games"]) == {"tic_tac_toe", "nim", "memory", "sokoban"}
    assert body["models"][0]["observation_modes"] == ["history_replay"]
    assert body["models"][0]["snapshot_restore"] is False
    check = await evaluation_client.post(BASE + "/preflight", json=payload())
    assert check.status_code == 200
    result = check.json()
    assert result["supported"] and result["reason_codes"] == []
    assert result["planned_episodes"] == result["planned_blocks"] == 1
    assert result["planned_decisions"] == 1
    assert result["configuration"]["generation_planned"] == {
        "temperature": 0.0,
        "top_p": 1.0,
        "num_steps": None,
    }
    unsupported = await evaluation_client.post(
        BASE + "/preflight", json=payload(observation_mode="native_incremental")
    )
    assert unsupported.status_code == 200
    assert not unsupported.json()["supported"]
    assert "unsupported_observation_mode" in unsupported.json()["reason_codes"]
    assert (await evaluation_client.get(BASE)).json() == {"evaluations": []}
    assert adapters == []
    assert not store.exists()
    assert runner.admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"repetitions": 0},
        {"repetitions": 11},
        {"case_ids": []},
        {"case_ids": ["nim-last-stone-v1", "nim-last-stone-v1"]},
        {"case_ids": ["missing-case"]},
        {"num_steps": 7},
        {"max_new_tokens": 7},
        {"decision_timeout_s": 301},
        {"decoding": "sampled", "temperature": 0},
        {"model_id": "../../private"},
        {"unrecognized": "not-a-setting"},
    ],
)
async def test_game_api_rejects_invalid_plans_without_creating_adapters(
    evaluation_client, rig, changes
):
    response = await evaluation_client.post(
        BASE + "/preflight", json=payload(**changes)
    )
    assert response.status_code == 422
    assert rig[1] == []
    assert (await evaluation_client.get(BASE)).json() == {"evaluations": []}


@pytest.mark.asyncio
async def test_game_api_start_idempotency_observe_and_three_export_formats(
    evaluation_client, rig
):
    headers = {"Idempotency-Key": "game-api-start"}
    missing = await evaluation_client.post(BASE, json=payload())
    assert missing.status_code == 422
    result = await evaluation_client.post(BASE, json=payload(), headers=headers)
    assert result.status_code == 202
    assert result.json()["created"]
    eid = result.json()["evaluation"]["id"]
    repeated = await evaluation_client.post(BASE, json=payload(), headers=headers)
    assert repeated.status_code == 202
    assert not repeated.json()["created"]
    assert repeated.json()["evaluation"]["id"] == eid
    conflict = await evaluation_client.post(
        BASE, json=payload(seed=999), headers=headers
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "idempotency_conflict"
    row = await finish(evaluation_client, eid)
    assert row["status"] == "completed"
    assert row["progress"] == {
        "planned": 1,
        "started": 1,
        "terminal": 1,
        "success": 1,
        "skipped": 0,
    }
    assert row["episodes"][0]["status"] == "game_completed"
    assert row["episodes"][0]["result"]["winner"] == "A"
    listing = (await evaluation_client.get(BASE)).json()["evaluations"]
    assert [item["id"] for item in listing] == [eid]
    exported = await evaluation_client.get(f"{BASE}/{eid}/export?format=json")
    assert exported.status_code == 200
    assert exported.json()["id"] == eid
    assert exported.headers["cache-control"] == "no-store"
    assert exported.headers["content-type"].startswith("application/json")
    assert f"evaluation-{eid}.json" in exported.headers["content-disposition"]
    journal = await evaluation_client.get(f"{BASE}/{eid}/export?format=jsonl")
    assert journal.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in journal.text.splitlines()]
    assert lines[0]["kind"] == "configuration"
    assert sum(item["kind"] == "decision" for item in lines) == 1
    assert lines[-1]["kind"] == "episode"
    table = await evaluation_client.get(f"{BASE}/{eid}/export?format=csv")
    assert table.headers["content-type"].startswith("text/csv")
    records = list(csv.DictReader(io.StringIO(table.text)))
    assert records[0]["case_id"] == "nim-last-stone-v1"
    assert records[0]["status"] == "game_completed"
    assert json.loads(records[0]["result"])["success"] is True
    assert (
        await evaluation_client.get(f"{BASE}/{eid}/export?format=html")
    ).status_code == 422
    assert (await evaluation_client.get(f"{BASE}/not-present")).status_code == 404
    assert len(rig[1]) == 1
    assert rig[1][0].closed
    assert rig[0].admission.snapshot()["status"] == "available"


@pytest.mark.asyncio
async def test_game_api_cancel_and_resume_are_explicit_and_preserve_attempt(
    evaluation_client, rig, monkeypatch
):
    runner, adapters = rig
    original = runner.adapter_factory
    block_next = True

    def factory(model, lease):
        adapter = original(model, lease)
        adapter.block = block_next
        return adapter

    monkeypatch.setattr(runner, "adapter_factory", factory)
    started = await evaluation_client.post(
        BASE, json=payload(), headers={"Idempotency-Key": "cancel-game"}
    )
    eid = started.json()["evaluation"]["id"]
    for _ in range(100):
        if adapters and adapters[-1].entered.is_set():
            break
        await asyncio.sleep(0.01)
    assert adapters and adapters[-1].entered.is_set()
    cancelled = await evaluation_client.post(f"{BASE}/{eid}/cancel")
    assert cancelled.status_code == 202
    row = await finish(evaluation_client, eid)
    assert row["status"] == "cancelled"
    assert runner.admission.snapshot()["status"] == "available"
    block_next = False
    resumed = await evaluation_client.post(f"{BASE}/{eid}/resume")
    assert resumed.status_code == 202
    assert resumed.json()["evaluation"]["id"] == eid
    row = await finish(evaluation_client, eid)
    assert row["status"] == "completed"
    assert row["block_restarts"] == 1
    assert row["episodes"][0]["attempt"] == 2
    assert row["attempt_history"][0][0]["status"] == "cancelled"
    assert row["episodes"][0]["result"]["success"]
    assert (await evaluation_client.post(f"{BASE}/{eid}/cancel")).status_code == 202
    nothing = await evaluation_client.post(f"{BASE}/{eid}/resume")
    assert nothing.status_code == 409
    assert nothing.json()["detail"]["code"] == "nothing_to_resume"


@pytest.mark.asyncio
async def test_game_api_guards_remote_cross_site_and_policy_denials(
    evaluation_client, monkeypatch
):
    app = evaluation_client._transport.app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.7", 4000)),
        base_url="http://localhost:8800",
    ) as remote:
        for suffix in ("", "/capabilities"):
            assert (await remote.get(BASE + suffix)).status_code == 403
        assert (
            await remote.post(BASE + "/preflight", json=payload())
        ).status_code == 403
    cross = await evaluation_client.post(
        BASE + "/preflight",
        json=payload(),
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert cross.status_code == 403
    assert cross.json()["detail"]["code"] == "origin_denied"
    from venom_core.core import module_data_policy

    def deny(**_kwargs):
        raise PermissionError("secret local path")

    monkeypatch.setattr(module_data_policy, "ensure_module_mutation_allowed", deny)
    denied = await evaluation_client.post(BASE + "/preflight", json=payload())
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "environment_read_only"
    assert "secret" not in denied.text
    assert (await evaluation_client.get(BASE)).status_code == 200


@pytest.mark.asyncio
async def test_game_api_disabled_module_cannot_reuse_a_cached_service(
    evaluation_client, monkeypatch, rig
):
    from venom_core.config import SETTINGS

    assert (await evaluation_client.get(BASE + "/capabilities")).status_code == 200
    monkeypatch.setattr(SETTINGS, "FEATURE_COOPERATION_LAB", False)
    for suffix in ("", "/capabilities", "/not-present"):
        assert (await evaluation_client.get(BASE + suffix)).status_code == 503
    assert (
        await evaluation_client.post(BASE + "/preflight", json=payload())
    ).status_code == 503
    assert rig[1] == []


@pytest.mark.asyncio
async def test_game_api_catalog_refresh_is_read_only(
    evaluation_client, rig, monkeypatch
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    refresh = AsyncMock()
    catalog = SimpleNamespace(refresh=refresh, available=lambda _model: True)
    monkeypatch.setattr(rig[0], "catalog_service", catalog)
    assert (await evaluation_client.get(BASE + "/capabilities")).status_code == 200
    assert (
        await evaluation_client.post(BASE + "/preflight", json=payload())
    ).status_code == 200
    assert refresh.await_count == 2
    assert rig[1] == []


@pytest.mark.asyncio
async def test_game_api_export_budget_and_unsupported_start_stay_explicit(
    evaluation_client, rig, monkeypatch
):
    unsupported = await evaluation_client.post(
        BASE,
        json=payload(observation_mode="native_incremental"),
        headers={"Idempotency-Key": "unsupported-native"},
    )
    assert unsupported.status_code == 422
    assert unsupported.json()["detail"]["code"] == "unsupported_observation_mode"
    assert rig[1] == []
    started = await evaluation_client.post(
        BASE, json=payload(), headers={"Idempotency-Key": "budget-export"}
    )
    eid = started.json()["evaluation"]["id"]
    await finish(evaluation_client, eid)
    from venom_module_cooperation_lab.evaluation import api

    monkeypatch.setattr(
        api,
        "export",
        lambda *_args: (
            "x" * (rig[0].store.limits.run_bytes * 2 + 1),
            "application/json",
        ),
    )
    result = await evaluation_client.get(f"{BASE}/{eid}/export")
    assert result.status_code == 413
    assert result.json()["detail"]["code"] == "export_too_large"


@pytest.mark.asyncio
async def test_game_api_delete_active_then_export_remove_and_reuse_capacity(
    evaluation_client, rig, monkeypatch
):
    runner, adapters = rig
    runner.store.limits = replace(runner.store.limits, max_runs=1)
    original = runner.adapter_factory
    block = True

    def factory(model, lease):
        adapter = original(model, lease)
        adapter.block = block
        return adapter

    monkeypatch.setattr(runner, "adapter_factory", factory)
    created = await evaluation_client.post(
        BASE, json=payload(), headers={"Idempotency-Key": "delete-api"}
    )
    eid = created.json()["evaluation"]["id"]
    deleted = await evaluation_client.delete(f"{BASE}/{eid}")
    assert deleted.status_code == 409
    assert deleted.json()["detail"]["code"] == "evaluation_active"
    await evaluation_client.post(f"{BASE}/{eid}/cancel")
    await finish(evaluation_client, eid)
    exported = await evaluation_client.get(f"{BASE}/{eid}/export")
    assert exported.status_code == 200 and exported.json()["id"] == eid
    caps = (await evaluation_client.get(BASE + "/capabilities")).json()
    assert caps["storage"]["series_used"] == 1
    removed = await evaluation_client.delete(f"{BASE}/{eid}")
    assert removed.status_code == 200 and removed.json() == {"deleted": True}
    assert (await evaluation_client.get(f"{BASE}/{eid}")).status_code == 404
    assert (await evaluation_client.get(f"{BASE}/{eid}/export")).status_code == 404
    assert (await evaluation_client.delete(f"{BASE}/{eid}")).status_code == 404
    caps = (await evaluation_client.get(BASE + "/capabilities")).json()
    assert caps["storage"]["series_used"] == 0
    assert exported.json()["id"] == eid
    block = False
    again = await evaluation_client.post(
        BASE, json=payload(), headers={"Idempotency-Key": "delete-api"}
    )
    assert again.status_code == 202 and again.json()["created"]
    new_id = again.json()["evaluation"]["id"]
    assert new_id != eid
    assert (await finish(evaluation_client, new_id))["status"] == "completed"


@pytest.mark.asyncio
async def test_model_settings_are_persistent_validated_and_observational(
    evaluation_client, rig
):
    runner, adapters = rig
    path = BASE + "/model-settings/" + SPEC.model_id
    initial = await evaluation_client.get(path)
    assert initial.status_code == 200 and not initial.json()["saved"]
    budgets = {
        "max_context_tokens": 4096,
        "max_new_tokens": 256,
        "decision_timeout_s": 180,
    }
    saved = await evaluation_client.put(path, json=budgets)
    assert saved.status_code == 200 and saved.json()["saved"]
    assert (await evaluation_client.get(path)).json()["budgets"] == budgets
    caps = (await evaluation_client.get(BASE + "/capabilities")).json()
    assert caps["models"][0]["budget_profile"]["budgets"] == budgets
    assert (
        await evaluation_client.put(path, json={**budgets, "max_context_tokens": 8192})
    ).status_code == 422
    assert (
        await evaluation_client.put(path, json={**budgets, "extra": "ignored"})
    ).status_code == 422
    assert (await evaluation_client.get(path)).json()["budgets"] == budgets
    assert not adapters
    assert not EvaluationStore(runner.store).exists()


@pytest.mark.asyncio
async def test_recovery_route_awaits_the_selected_evaluation_verifier(
    evaluation_client, monkeypatch
):
    from unittest.mock import AsyncMock

    await evaluation_client.get(BASE + "/capabilities")
    service = evaluation_client._transport.app.state.cooperation_lab_evaluations
    recovery = AsyncMock(return_value={"id": "selected-run", "status": "interrupted"})
    monkeypatch.setattr(service, "recover_quiescent", recovery)
    response = await evaluation_client.post(BASE + "/selected-run/recover")
    assert response.status_code == 200
    assert response.json()["evaluation"]["id"] == "selected-run"
    recovery.assert_awaited_once_with("selected-run")


@pytest.mark.asyncio
async def test_invalid_request_has_safe_parameter_error_without_prompt_contents(
    evaluation_client,
):
    response = await evaluation_client.post(
        "/api/v1/cooperation-lab/runs",
        headers={"Idempotency-Key": "invalid-form"},
        json={
            "model_id": SPEC.model_id,
            "scenario_id": "tic_tac_toe",
            "max_new_tokens": 2**31,
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_parameters"
    assert detail["fields"] == ["max_new_tokens"]
    assert "input" not in str(detail)


@pytest.mark.asyncio
async def test_ordinary_runs_start_after_clamping_next_budget_for_hf_model(
    evaluation_client, monkeypatch
):
    runner = evaluation_client._transport.app.state.cooperation_lab_runner
    original = runner.adapter_factory

    def conversation(model, lease):
        adapter = original(model, lease)
        adapter.responses = ["Short conversation reply"]
        return adapter

    monkeypatch.setattr(runner, "adapter_factory", conversation)
    for key, tokens in [("ordinary-128", 128), ("ordinary-1024", 1024)]:
        response = await evaluation_client.post(
            "/api/v1/cooperation-lab/runs",
            headers={"Idempotency-Key": key},
            json={
                "model_id": SPEC.model_id,
                "scenario_id": "split_facts",
                "mode": "single",
                "max_turns": 1,
                "max_new_tokens": tokens,
            },
        )
        assert response.status_code == 202, response.text
        row = response.json()["run"]
        runner = evaluation_client._transport.app.state.cooperation_lab_runner
        await asyncio.wait_for(runner.jobs[row["id"]].task, timeout=3)
        assert runner.snapshot(row["id"])["run"]["status"] == "completed"
        assert row["config"]["budgets"]["max_new_tokens"] == min(tokens, 256)


@pytest.mark.asyncio
async def test_evaluation_clamps_before_generation_and_preserves_idempotency(
    evaluation_client, rig
):
    runner, adapters = rig
    original = payload(max_new_tokens=16384)
    preflight = await evaluation_client.post(BASE + "/preflight", json=original)
    assert preflight.status_code == 200
    assert preflight.json()["supported"]
    assert preflight.json()["configuration"]["max_new_tokens"] == 256
    assert adapters == []
    headers = {"Idempotency-Key": "clamped-evaluation"}
    start = await evaluation_client.post(BASE, json=original, headers=headers)
    assert start.status_code == 202, start.text
    eid = start.json()["evaluation"]["id"]
    state = await finish(evaluation_client, eid)
    assert state["config"]["max_new_tokens"] == 256
    assert state["config"]["request"]["max_new_tokens"] == 16384
    assert adapters[-1].recorded[0][2].max_new_tokens == 256
    again = await evaluation_client.post(BASE, json=original, headers=headers)
    assert again.status_code == 202 and not again.json()["created"]
    assert again.json()["evaluation"]["id"] == eid


@pytest.mark.asyncio
async def test_interrupted_evaluation_cannot_be_deleted_while_lease_references_it(
    evaluation_client, rig
):
    runner, _adapters = rig
    created = await evaluation_client.post(
        BASE, json=payload(), headers={"Idempotency-Key": "protected-quarantine-record"}
    )
    eid = created.json()["evaluation"]["id"]
    await finish(evaluation_client, eid)
    service = evaluation_client._transport.app.state.cooperation_lab_evaluations
    state = service.store.get(eid)
    state.update(status="interrupted", error="process_restarted")
    service.store.save(state)
    service.jobs.pop(eid)
    lease = runner.admission.acquire(
        owner="cooperation_lab",
        run_id="evaluation-" + eid,
        engine="ollama",
        model=SPEC.model_id,
    )
    with runner.admission._transaction() as ledger:
        ledger.execute("UPDATE lease SET quarantine=1")
    rejected = await evaluation_client.delete(f"{BASE}/{eid}")
    assert (
        rejected.status_code == 409
        and rejected.json()["detail"]["code"] == "evaluation_active"
    )
    assert (await evaluation_client.get(f"{BASE}/{eid}")).status_code == 200
    assert runner.admission.snapshot()["status"] == "quarantined"
    runner.store.limits = replace(runner.store.limits, max_runs=1)
    blocked = await evaluation_client.post(
        "/api/v1/cooperation-lab/runs",
        headers={"Idempotency-Key": "blocked-start-cannot-evict-recovery"},
        json={
            "model_id": SPEC.model_id,
            "scenario_id": "split_facts",
            "mode": "single",
            "max_turns": 1,
        },
    )
    assert blocked.status_code == 409
    assert runner.store.history_count() == 1
    assert (await evaluation_client.get(f"{BASE}/{eid}")).status_code == 200
    assert lease.recover(confirm_quiescent=lambda: True)
    assert (await evaluation_client.delete(f"{BASE}/{eid}")).status_code == 200
