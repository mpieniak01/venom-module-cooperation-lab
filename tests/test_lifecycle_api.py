from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_module_cooperation_lab.api.routes import router, state
from venom_module_cooperation_lab.lifecycle import LabLifecycle, lifespan
from venom_module_cooperation_lab.storage import LabStore


@pytest.fixture(autouse=True)
def configured_host_settings(monkeypatch):
    from venom_core import config

    settings = SimpleNamespace(
        FEATURE_COOPERATION_LAB=False, RUNTIME_ADMISSION_ENABLED=False
    )
    monkeypatch.setattr(config, "SETTINGS", settings)
    return settings


@pytest.mark.asyncio
async def test_disabled_has_no_factory_io():
    factory = Mock()
    lifecycle = LabLifecycle(factory)
    await lifecycle.start(False)
    await lifecycle.close()
    factory.assert_not_called()
    assert lifecycle.state == "disabled"


@pytest.mark.asyncio
async def test_start_error_is_not_ready():
    factory = Mock(side_effect=RuntimeError("private internal path"))
    lifecycle = LabLifecycle(factory)
    await lifecycle.start(True)
    assert lifecycle.state == "not_ready"
    assert lifecycle.reason == "storage_unavailable"


@pytest.mark.asyncio
async def test_start_closes_failed_store():
    store = Mock()
    store.open.side_effect = PermissionError("preprod")
    lifecycle = LabLifecycle(lambda: store)
    await lifecycle.start(True)
    store.close.assert_called_once()
    assert lifecycle.store is None


@pytest.mark.asyncio
async def test_lifespan_enabled_owns_schema_not_model(
    tmp_path, monkeypatch, configured_host_settings
):
    configured_host_settings.FEATURE_COOPERATION_LAB = True
    stores = []

    def factory(access):
        store = LabStore(tmp_path / "lab", Mock(), access)
        stores.append(store)
        return store

    monkeypatch.setattr(LabStore, "from_host", factory)
    app = FastAPI()
    async with lifespan(app):
        assert stores[0].opened
        assert app.state.cooperation_lab.state == "not_ready"
        with pytest.raises(PermissionError, match="host_access_policy_required"):
            stores[0].list_runs(owner="operator")
    assert not stores[0].opened


def test_public_discovery_true_not_ready_no_generation(
    monkeypatch, configured_host_settings
):
    monkeypatch.delenv("FEATURE_COOPERATION_LAB", raising=False)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=("127.0.0.1", 4000)) as client:
        response = client.get("/api/v1/cooperation-lab/health")
        assert response.json()["state"] == "disabled"
        caps = client.get("/api/v1/cooperation-lab/capabilities").json()
        assert caps["ready"] is False and caps["generation"] is False
        assert caps["limits"]["database_bytes"] == 512 * 1024 * 1024
        denied = client.post(
            "/api/v1/cooperation-lab/runs",
            json={"model_id": "unqualified", "scenario_id": "split_facts"},
            headers={"Idempotency-Key": "unqualified"},
        )
        assert denied.status_code == 503
        assert denied.json()["detail"]["reason_code"] == "model_not_qualified"
    configured_host_settings.FEATURE_COOPERATION_LAB = True
    req = SimpleNamespace(app=app)
    assert state(req)["reason_code"] == "runtime_admission_disabled"
    configured_host_settings.RUNTIME_ADMISSION_ENABLED = True
    del app.state.cooperation_lab
    assert state(req)["reason_code"] == "lifecycle_not_started"
    app.state.cooperation_lab = LabLifecycle(Mock())
    assert state(req)["state"] == "disabled"


def test_access_policy_rejects_remote_reads(monkeypatch):
    monkeypatch.delenv("FEATURE_COOPERATION_LAB", raising=False)
    app = FastAPI()
    app.include_router(router)
    with TestClient(app, client=("198.51.100.1", 4000)) as client:
        assert client.get("/api/v1/cooperation-lab/health").status_code == 403


def test_manifest_host_namespace_and_guard(tmp_path, monkeypatch):
    from pathlib import Path

    from venom_core.core import module_data_policy
    from venom_core.services.module_registry import (
        _is_compatible,
        _is_enabled,
        _parse_manifest_file,
    )

    manifest = _parse_manifest_file(str(Path("module.json").resolve()))
    assert manifest and manifest.module_id == "cooperation_lab"
    assert not _is_enabled(manifest, SimpleNamespace())
    assert _is_enabled(manifest, SimpleNamespace(FEATURE_COOPERATION_LAB=True))
    assert _is_compatible(
        manifest,
        SimpleNamespace(CORE_MODULE_API_VERSION="1.0.0", CORE_RUNTIME_VERSION="1.6.0"),
    )
    assert not _is_compatible(
        manifest, SimpleNamespace(CORE_MODULE_API_VERSION="2.0.0")
    )
    assert not _is_compatible(
        manifest,
        SimpleNamespace(CORE_MODULE_API_VERSION="1.0.0", CORE_RUNTIME_VERSION="1.5.0"),
    )
    mutation = Mock()
    monkeypatch.setattr(module_data_policy, "ensure_module_mutation_allowed", mutation)
    monkeypatch.setattr(
        module_data_policy,
        "resolve_module_data_root",
        lambda **_: tmp_path / "dev" / "cooperation_lab",
    )
    store = LabStore.from_host(Mock())
    assert store.root == tmp_path / "dev" / "cooperation_lab"
    store.open()
    store.close()
    assert mutation.call_args_list[0].kwargs["module_id"] == "cooperation_lab"
    data = json.loads(Path("module.json").read_text())
    assert data["enabled_by_default"] is False


def test_host_settings_are_the_only_feature_flag_truth(
    monkeypatch, configured_host_settings
):
    from venom_module_cooperation_lab.lifecycle import enabled

    monkeypatch.setenv("FEATURE_COOPERATION_LAB", "true")
    assert not enabled()
    monkeypatch.delenv("FEATURE_COOPERATION_LAB")
    configured_host_settings.FEATURE_COOPERATION_LAB = True
    assert enabled()
