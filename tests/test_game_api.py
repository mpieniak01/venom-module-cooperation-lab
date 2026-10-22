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
    assert result["configuration"]["generation_applied"] == {
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
        {"decision_timeout_s": 91},
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
