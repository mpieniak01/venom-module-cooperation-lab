from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from conftest import SPEC
from fastapi import FastAPI

from venom_module_cooperation_lab.api.routes import router
from venom_module_cooperation_lab.runner import OWNER


@pytest.fixture
async def client(rig, monkeypatch):
    from venom_core.config import SETTINGS

    monkeypatch.setattr(SETTINGS, "FEATURE_COOPERATION_LAB", True)
    monkeypatch.setattr(SETTINGS, "RUNTIME_ADMISSION_ENABLED", True)
    app = FastAPI()
    app.include_router(router)
    app.state.cooperation_lab_runner = rig[0]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("127.0.0.1", 4000)),
        base_url="http://localhost:8800",
    ) as value:
        yield value


def payload():
    return {
        "model_id": SPEC.model_id,
        "scenario_id": "split_facts",
        "mode": "dialog",
        "max_turns": 2,
    }


@pytest.mark.asyncio
async def test_operator_can_discover_start_observe_export_and_delete(client, rig):
    runner, adapters = rig
    caps = (await client.get("/api/v1/cooperation-lab/capabilities")).json()
    assert caps["ready"] and caps["generation"]
    assert caps["qualified_models"] == [SPEC.model_id]
    assert len(caps["scenarios"]) == 3
    assert adapters == []
    started = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "api1"},
    )
    assert started.status_code == 202
    run_id = started.json()["run"]["id"]
    retry = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "api1"},
    )
    assert not retry.json()["created"]
    await asyncio.wait_for(runner.jobs[run_id].task, timeout=2)
    snapshot = (await client.get(f"/api/v1/cooperation-lab/runs/{run_id}")).json()
    assert snapshot["run"]["status"] == "completed"
    assert snapshot["run"]["owner"] == OWNER
    listed = await client.get("/api/v1/cooperation-lab/runs?owner=untrusted")
    assert len(listed.json()["runs"]) == 1
    events = await client.get(
        f"/api/v1/cooperation-lab/runs/{run_id}/events?after=0&limit=2"
    )
    assert len(events.json()["events"]) == 2
    exported = await client.get(f"/api/v1/cooperation-lab/runs/{run_id}/export")
    assert exported.headers["content-type"].startswith("application/json")
    assert exported.json()["run"]["id"] == run_id
    assert (await client.post(f"/api/v1/cooperation-lab/runs/{run_id}/cancel")).json()[
        "run"
    ]["status"] == "completed"
    assert (
        await client.delete(f"/api/v1/cooperation-lab/runs/{run_id}")
    ).status_code == 204
    assert (
        await client.get(f"/api/v1/cooperation-lab/runs/{run_id}")
    ).status_code == 404


@pytest.mark.asyncio
async def test_sse_replays_exact_persisted_sequences_and_cursor_recovery(client, rig):
    runner, _ = rig
    response = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "stream"},
    )
    run_id = response.json()["run"]["id"]
    await asyncio.wait_for(runner.jobs[run_id].task, timeout=2)
    sse = await client.get(
        f"/api/v1/cooperation-lab/runs/{run_id}/events/stream?after=1",
        headers={"Last-Event-ID": "3"},
    )
    assert sse.headers["content-type"].startswith("text/event-stream")
    assert sse.headers["x-accel-buffering"] == "no"
    data = [
        json.loads(line.removeprefix("data: "))
        for line in sse.text.splitlines()
        if line.startswith("data: ")
    ]
    expected = runner.store.events(run_id, owner=OWNER, after=3)
    assert data == expected
    assert all(item["seq"] > 3 for item in data)
    assert data[-1]["kind"] == "end"
    bad = await client.get(
        f"/api/v1/cooperation-lab/runs/{run_id}/events/stream",
        headers={"Last-Event-ID": "not-int"},
    )
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_cursor"
    gap = await client.get(f"/api/v1/cooperation-lab/runs/{run_id}/events?after=99999")
    assert gap.status_code == 409 and gap.json()["detail"]["code"] == "resync_required"
    gap = await client.get(
        f"/api/v1/cooperation-lab/runs/{run_id}/events/stream?after=99999"
    )
    assert gap.status_code == 409


@pytest.mark.asyncio
async def test_payload_owner_endpoints_budget_and_key_are_not_model_controlled(client):
    for extra in [{"owner": "model"}, {"url": "http://example.com"}, {"max_turns": 99}]:
        response = await client.post(
            "/api/v1/cooperation-lab/runs",
            json=payload() | extra,
            headers={"Idempotency-Key": "invalid"},
        )
        assert response.status_code == 422
    missing = await client.post("/api/v1/cooperation-lab/runs", json=payload())
    assert missing.status_code == 422
    invalid = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "../invalid"},
    )
    assert invalid.status_code == 400
    assert (
        await client.get("/api/v1/cooperation-lab/runs?limit=101")
    ).status_code == 422
    assert (
        await client.get("/api/v1/cooperation-lab/runs/!invalid")
    ).status_code == 400
    cross = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "cross", "Sec-Fetch-Site": "cross-site"},
    )
    assert cross.status_code == 403


@pytest.mark.asyncio
async def test_mutation_policy_denial_is_sanitized_but_reads_remain(
    client, monkeypatch
):
    from venom_core.core import module_data_policy

    def deny(**_kwargs):
        raise PermissionError("private path and policy")

    monkeypatch.setattr(module_data_policy, "ensure_module_mutation_allowed", deny)
    response = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "denied"},
    )
    assert response.status_code == 403
    assert "private path" not in response.text
    assert response.json()["detail"]["code"] == "environment_read_only"
    assert (await client.get("/api/v1/cooperation-lab/runs")).status_code == 200


@pytest.mark.asyncio
async def test_remote_api_access_is_denied_before_run_data(client, rig):
    app = client._transport.app
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("198.51.100.8", 4000)),
        base_url="http://localhost:8800",
    ) as remote:
        assert (await remote.get("/api/v1/cooperation-lab/runs")).status_code == 403
        assert (
            await remote.get("/api/v1/cooperation-lab/capabilities")
        ).status_code == 403
