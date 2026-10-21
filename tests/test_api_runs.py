from __future__ import annotations

import asyncio
import json
import threading

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
    assert len(caps["scenarios"]) == 6
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
@pytest.mark.parametrize("late_cleanup", [False, True])
async def test_sse_replays_exact_persisted_sequences_and_cursor_recovery(
    client, rig, late_cleanup
):
    runner, _ = rig
    release_close = threading.Event()
    original_factory = runner.adapter_factory

    def factory(model, lease):
        adapter = original_factory(model, lease)
        original_close = adapter.close

        def controlled_close():
            if not release_close.wait(5):
                return False
            return original_close()

        adapter.close = controlled_close
        return adapter

    # Nominal replay is not a 300 ms CI scheduling test. The second case
    # deliberately holds the owned close past its deadline, then releases it.
    runner.cleanup_seconds = 0.02 if late_cleanup else 10.0
    if late_cleanup:
        runner.adapter_factory = factory
    response = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload(),
        headers={"Idempotency-Key": "stream"},
    )
    run_id = response.json()["run"]["id"]
    job = runner.jobs[run_id]
    try:
        await asyncio.wait_for(job.task, timeout=5)
        if late_cleanup:
            assert not job.cleanup_complete
            assert runner.snapshot(run_id)["run"]["status"] == "failed"
            release_close.set()
            async with asyncio.timeout(5):
                while not job.late_cleanup_recorded:
                    await asyncio.sleep(0.001)
        else:
            assert runner.snapshot(run_id)["run"]["status"] == "completed"
        assert job.cleanup_complete
        assert runner.admission.snapshot()["status"] == "available"
    finally:
        release_close.set()
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
    endings = [event for event in data if event["kind"] == "end"]
    assert len(endings) == 1
    if late_cleanup:
        assert endings[0]["payload"]["quiescent"] is False
        assert data[-1]["kind"] == "run"
        assert data[-1]["payload"] == {
            "status": "failed",
            "quiescent": True,
            "cleanup_late": True,
        }
    else:
        assert data[-1] == endings[0]
        assert endings[0]["payload"]["quiescent"] is True
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


@pytest.mark.asyncio
async def test_operator_input_api_validation_delivery_idempotency_and_access(
    client, rig
):
    from test_operator_chat import waiting

    runner, _ = rig
    result = await client.post(
        "/api/v1/cooperation-lab/runs",
        json=payload()
        | {"mode": "operator_chat", "scenario_id": "operator_conversation"},
        headers={"Idempotency-Key": "operator-api"},
    )
    row = result.json()["run"]
    await waiting(runner, row)
    url = f"/api/v1/cooperation-lab/runs/{row['id']}/messages"
    headers = {"Idempotency-Key": "prompt"}
    for body in (
        {"content": " "},
        {"content": "x" * 2001},
        {"content": 123},
        {"content": "test", "sender": "A"},
    ):
        assert (await client.post(url, json=body, headers=headers)).status_code == 422
    assert (await client.post(url, json={"content": "test"})).status_code == 422
    assert (
        await client.post(
            url,
            json={"content": "test"},
            headers=headers | {"Sec-Fetch-Site": "cross-site"},
        )
    ).status_code == 403
    accepted = await client.post(
        url, json={"content": "<b>Wiadomość</b>"}, headers=headers
    )
    assert accepted.status_code == 202
    assert accepted.json()["event"]["payload"]["sender"] == "operator"
    repeated = await client.post(
        url, json={"content": "<b>Wiadomość</b>"}, headers=headers
    )
    assert not repeated.json()["created"]
    assert (
        await client.post(url, json={"content": "changed"}, headers=headers)
    ).status_code == 409
    await asyncio.wait_for(runner.jobs[row["id"]].task, 2)
    replay = (await client.get(url.removesuffix("/messages") + "/events")).json()
    assert sum(e["kind"] == "message" for e in replay["events"]) == 3


@pytest.mark.asyncio
async def test_catalog_qualification_api_and_denial(client, rig):
    from test_catalog import install

    runner, _ = rig
    catalog, spec, adapters = install(runner)
    caps = (await client.get("/api/v1/cooperation-lab/capabilities")).json()
    assert len(caps["engines"]) == 3
    assert next(m for m in caps["models"] if m["model_id"] == spec.model_id)[
        "can_qualify"
    ]
    assert not adapters
    path = "/api/v1/cooperation-lab/qualifications"
    body = {"model_id": spec.model_id}
    denied = await client.post(
        path,
        json=body,
        headers={"Idempotency-Key": "cross", "Sec-Fetch-Site": "cross-site"},
    )
    assert denied.status_code == 403
    invalid = await client.post(
        path, json={**body, "endpoint": "remote"}, headers={"Idempotency-Key": "bad"}
    )
    assert invalid.status_code == 422
    result = await client.post(
        path, json=body, headers={"Idempotency-Key": "check-api"}
    )
    assert result.status_code == 202
    run_id = result.json()["run"]["id"]
    await runner.jobs[run_id].task
    caps = (await client.get("/api/v1/cooperation-lab/capabilities")).json()
    assert spec.model_id in caps["qualified_models"]
    started = await client.post(
        "/api/v1/cooperation-lab/runs",
        json={**body, "scenario_id": "split_facts", "max_turns": 1},
        headers={"Idempotency-Key": "after-check"},
    )
    assert started.status_code == 202
    await runner.jobs[started.json()["run"]["id"]].task
    runner.catalog_service = None
    result = await client.post(
        path, json=body, headers={"Idempotency-Key": "no-catalog"}
    )
    assert result.status_code == 409


@pytest.mark.asyncio
async def test_installed_ollama_starts_directly_without_qualification_receipt(
    client, rig
):
    from test_catalog import install

    runner, _ = rig
    _, spec, _ = install(runner)
    caps = (await client.get("/api/v1/cooperation-lab/capabilities")).json()
    model = next(m for m in caps["models"] if m["model_id"] == spec.model_id)
    assert model["can_run"] and not model["qualified"]
    assert caps["ready"]
    for index in range(2):
        result = await client.post(
            "/api/v1/cooperation-lab/runs",
            json={
                "model_id": spec.model_id,
                "scenario_id": "split_facts",
                "max_turns": 1,
            },
            headers={"Idempotency-Key": "direct-api-" + str(index)},
        )
        assert result.status_code == 202
        await runner.jobs[result.json()["run"]["id"]].task
        assert runner.admission.snapshot()["status"] == "available"
    assert (
        runner.store.get_document("qualifications", spec.model_id, owner=OWNER) is None
    )
