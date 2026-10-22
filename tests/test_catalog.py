from __future__ import annotations

import hashlib
from dataclasses import asdict, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from conftest import FakeAdapter
from test_adapters import Lease

from venom_module_cooperation_lab.adapters.registry import OLLAMA_SPEC
from venom_module_cooperation_lab.catalog import (
    ModelCatalog,
    host_local_catalog,
    ollama_metadata,
)
from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.run_config import RunRequest
from venom_module_cooperation_lab.runner import OWNER


def fixture_catalog():
    runtimes = [
        {
            "runtime_id": "ollama",
            "status": "online",
            "models": [{"name": "small:1b", "chat_compatible": True}],
        },
        {
            "runtime_id": "multi_runtime",
            "status": "offline",
            "models": [{"name": "gemma"}, {"name": ""}],
        },
        {"runtime_id": "cloud", "status": "online", "models": [{"name": "not-local"}]},
    ]
    entry = {
        "name": "small:1b",
        "digest": "a" * 64,
        "size": 123,
        "show": {
            "template": "template",
            "capabilities": ["completion"],
            "details": {"family": "llama", "quantization_level": "Q4"},
        },
    }
    metadata = {"version": "0.40.6", "models": [entry]}
    return (
        ModelCatalog(AsyncMock(return_value=runtimes), lambda: metadata),
        runtimes,
        metadata,
    )


@pytest.mark.asyncio
async def test_catalog_read_only_cache_identity_dedup_and_failure():
    catalog, runtimes, metadata = fixture_catalog()
    metadata["models"] += [
        metadata["models"][0],
        {"name": "small:1b", "digest": "bad"},
        {"name": "outside", "digest": "b" * 64},
    ]
    await catalog.refresh()
    candidates = [s for s in catalog.specs() if s.model_id.startswith("ollama-")]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert catalog.candidate(candidate.model_id) == candidate
    with pytest.raises(LabError, match="runtime_lease_required"):
        catalog.adapter(candidate.model_id, None)
    assert (
        catalog.adapter(
            candidate.model_id, SimpleNamespace(operation=lambda: None)
        ).spec
        == candidate
    )
    with pytest.raises(LabError, match="model_unavailable"):
        catalog.candidate("anything")
    models = catalog.public_models([asdict(s) for s in catalog.specs()])
    assert next(m for m in models if m["model_id"] == candidate.model_id)["can_qualify"]
    assert models[-1]["availability_reason"] == "adapter_not_supported"
    assert len(catalog.engines) == 3
    await catalog.refresh()
    assert catalog.loader.await_count == 1
    metadata["version"] = "0.40.7"
    await catalog.refresh(force=True)
    assert not catalog.available(candidate.model_id)
    metadata["version"] = "invalid"
    await catalog.refresh(force=True)
    assert catalog.error == "catalog_unavailable"
    assert not any(
        catalog.available(s.model_id) for s in catalog.specs() if s.provider == "ollama"
    )
    runtimes[0]["status"] = "offline"
    await catalog.refresh(force=True)
    assert catalog.error is None
    assert not catalog.available(OLLAMA_SPEC.model_id)
    catalog.loader.side_effect = RuntimeError("private diagnostic")
    await catalog.refresh(force=True)
    assert catalog.error == "catalog_unavailable"


def test_filter_non_chat_empty_template_and_pinned_baseline():
    c, runtimes, metadata = fixture_catalog()
    rows = runtimes[0]["models"]
    rows.append({"name": "embedding", "chat_compatible": False})
    metadata["models"] += [
        {"name": "embedding", "digest": "b" * 64},
        {
            "name": "small:1b",
            "digest": "c" * 64,
            "show": {"capabilities": ["completion"], "template": ""},
        },
        {
            "name": "small:1b",
            "digest": "d" * 64,
            "show": {"capabilities": ["embedding"], "template": "a"},
        },
    ]
    c._apply(runtimes, metadata)
    assert len(c.specs()) == 6
    c._ollama([], {"version": "0.40.6", "models": []}, False)
    from venom_module_cooperation_lab import catalog as module

    spec = replace(
        OLLAMA_SPEC,
        artifact="small:1b",
        digest="a" * 64,
        template_hash=hashlib.sha256(b"template").hexdigest(),
    )
    old = module.OLLAMA_SPEC
    try:
        module.OLLAMA_SPEC = spec
        c._apply(runtimes, metadata)
        assert c.candidate(spec.model_id) == spec
        alias = metadata["models"][0]
        alias["name"] = "small:latest"
        runtimes[0]["models"] = [{"name": "small:latest", "chat_compatible": True}]
        c._apply(runtimes, {"version": "0.40.6", "models": [alias]})
        assert not c.available(spec.model_id)
        assert any(
            s.artifact == "small:latest" and s.model_id.startswith("ollama-")
            for s in c.specs()
        )
    finally:
        module.OLLAMA_SPEC = old


@pytest.mark.asyncio
async def test_host_bridge_uses_read_only_local_helpers(monkeypatch):
    from venom_core.api.routes import system_llm as host

    manager = SimpleNamespace(list_local_models=AsyncMock(return_value=["local"]))
    monkeypatch.setattr(host.system_deps, "get_model_manager", lambda: manager)
    grouping = AsyncMock(return_value=({"ollama": []}, []))
    monkeypatch.setattr(host, "_local_models_by_runtime", grouping)
    monkeypatch.setattr(
        host, "_runtime_server_status_snapshot", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        host,
        "_local_runtime_targets",
        lambda **kwargs: [{"runtime_id": "ollama", **kwargs}],
    )
    monkeypatch.setattr(host, "get_active_llm_runtime", lambda: "ollama")
    monkeypatch.setattr(
        host,
        "_apply_vllm_runtime_autofix",
        lambda *a, **k: pytest.fail("global mutation"),
    )
    result = await host_local_catalog()
    assert result[0]["local_models"] == {"ollama": []}
    monkeypatch.setattr(host.system_deps, "get_model_manager", lambda: None)
    with pytest.raises(LabError, match="catalog_unavailable"):
        await host_local_catalog()


def install(runner):
    catalog, _, _ = fixture_catalog()
    catalog._apply(catalog.loader.return_value, catalog.metadata())
    spec = next(s for s in catalog.specs() if s.model_id.startswith("ollama-"))
    runner.catalog_service = catalog
    runner.model_catalog = catalog.specs
    adapters = []

    def factory(model, lease):
        assert model == spec.model_id
        adapter = FakeAdapter(lease)
        adapters.append(adapter)
        return adapter

    runner.adapter_factory = factory
    return catalog, spec, adapters


@pytest.mark.asyncio
async def test_qualification_contexts_cleanup_receipt_and_idempotency(
    rig,
):
    runner, _ = rig
    catalog, spec, adapters = install(runner)
    request = RunRequest(model_id=spec.model_id, scenario_id="split_facts")
    direct, _ = await runner.start(request, "direct-experiment")
    await runner.jobs[direct["id"]].task
    assert runner.snapshot(direct["id"])["run"]["status"] == "completed"
    assert (
        runner.store.get_document("qualifications", spec.model_id, owner=OWNER) is None
    )
    adapters.clear()
    row, _ = await runner.start(request, "qualify", qualification=True)
    duplicate, created = await runner.start(request, "qualify", qualification=True)
    assert duplicate["id"] == row["id"] and not created
    assert (
        runner.store.get_document("qualifications", spec.model_id, owner=OWNER) is None
    )
    await runner.jobs[row["id"]].task
    assert runner.snapshot(row["id"])["run"]["status"] == "completed"
    assert [p for p, _, _ in adapters[0].recorded] == ["A", "B"]
    assert all(len(history) == 2 for _, history, _ in adapters[0].recorded)
    assert adapters[0].closed and runner.admission.snapshot()["status"] == "available"
    assert runner._qualified_model(spec.model_id)["qualified"]
    catalog._available.clear()
    with pytest.raises(LabError, match="model_unavailable"):
        runner._qualified_model(spec.model_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["cancel", "load", "empty", "receipt"])
async def test_failed_qualification_never_grants_ready(rig, kind):
    runner, _ = rig
    _, spec, adapters = install(runner)
    original = runner.adapter_factory

    def factory(model, lease):
        adapter = original(model, lease)
        if kind == "load":
            adapter.load = lambda deadline: (_ for _ in ()).throw(
                LabError("artifact_missing")
            )
        if kind == "empty":
            adapter.responses = [""]
        return adapter

    runner.adapter_factory = factory
    if kind == "receipt":
        runner._record_qualification = lambda job: (_ for _ in ()).throw(
            LabError("storage_unavailable")
        )
    request = RunRequest(model_id=spec.model_id, scenario_id="split_facts")
    row, _ = await runner.start(request, "failure-" + kind, qualification=True)
    if kind == "cancel":
        await runner.cancel(row["id"])
    await runner.jobs[row["id"]].task
    assert runner.snapshot(row["id"])["run"]["status"] in {"failed", "cancelled"}
    assert (
        runner.store.get_document("qualifications", spec.model_id, owner=OWNER) is None
    )


def test_metadata_is_bounded_local_and_no_generation(monkeypatch):
    import io
    import json
    import urllib.request

    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, request.data))
        if request.full_url.endswith("/api/version"):
            return io.BytesIO(b'{"version":"0.40.6"}')
        if request.full_url.endswith("/api/tags"):
            return io.BytesIO(
                json.dumps({"models": [{"name": "small"}, {"name": None}]}).encode()
            )
        return io.BytesIO(b"{}")

    monkeypatch.setattr(
        urllib.request, "build_opener", lambda *a: SimpleNamespace(open=open_request)
    )
    assert len(ollama_metadata()["models"]) == 1
    assert all(url.startswith("http://127.0.0.1:11434/api/") for url, _ in calls)
    assert all("chat" not in url and "generate" not in url for url, _ in calls)
    monkeypatch.setattr(
        urllib.request,
        "build_opener",
        lambda *a: SimpleNamespace(open=lambda *a, **k: io.BytesIO(b"x" * 262145)),
    )
    with pytest.raises(LabError, match="runtime_response_too_large"):
        ollama_metadata()


@pytest.mark.asyncio
@pytest.mark.parametrize("qualification", [False, True])
async def test_start_retry_survives_unavailable_or_changed_model(rig, qualification):
    runner, _ = rig
    catalog, spec, _ = install(runner)
    request = RunRequest(model_id=spec.model_id, scenario_id="split_facts", max_turns=1)
    row, _ = await runner.start(request, "durable-start", qualification=qualification)
    await runner.jobs[row["id"]].task
    runner.jobs.clear()
    runner.store.close()
    runner.store.open()
    catalog._available.clear()
    catalog.loader.side_effect = RuntimeError("unavailable")
    catalog._updated = 0
    same, created = await runner.start(
        request, "durable-start", qualification=qualification
    )
    assert same["id"] == row["id"] and not created
    with pytest.raises(LabError, match="idempotency_conflict"):
        await runner.start(
            request.model_copy(update={"model_id": "changed"}),
            "durable-start",
            qualification=qualification,
        )
    if not qualification:
        with pytest.raises(LabError, match="idempotency_conflict"):
            await runner.start(
                request.model_copy(update={"max_new_tokens": 32}), "durable-start"
            )


def test_second_rwkv_survives_catalog_refresh_and_can_qualify():
    from venom_module_cooperation_lab.adapters.registry import RWKV_29_SPEC

    c = ModelCatalog()
    c._apply([], {"models": [], "version": ""})
    assert c.candidate(RWKV_29_SPEC.model_id) == RWKV_29_SPEC
    rows = c.public_models([asdict(RWKV_29_SPEC)])
    assert rows[0]["can_qualify"]
    assert not rows[0]["can_run"]
    assert c.adapter(RWKV_29_SPEC.model_id, Lease()).spec == RWKV_29_SPEC
