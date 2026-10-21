from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient


def test_absent_off_and_invalid_manifest_do_not_block_host(tmp_path, monkeypatch):
    from venom_core.services import module_registry

    monkeypatch.setattr(
        module_registry, "_install_conversation_provider_lifespan", lambda *_: None
    )
    actual = str(Path("module.json").resolve())
    invalid = tmp_path / "bad.json"
    invalid.write_text("{invalid")
    for source in ["", actual, str(invalid), str(tmp_path / "absent.json")]:
        app = FastAPI()
        app.get("/host-health")(lambda: {"ok": True})
        included = module_registry.include_optional_api_routers(
            app,
            SimpleNamespace(
                API_OPTIONAL_MODULES=source,
                FEATURE_COOPERATION_LAB=False,
                CORE_MODULE_API_VERSION="1.0.0",
                CORE_RUNTIME_VERSION="1.6.0",
            ),
        )
        assert included == []
        with TestClient(app) as client:
            assert client.get("/host-health").json() == {"ok": True}
            assert client.get("/api/v1/cooperation-lab/health").status_code == 404


def test_abi_mismatch_is_quarantined(tmp_path, monkeypatch):
    from venom_core.services import module_registry

    monkeypatch.setattr(
        module_registry, "_install_conversation_provider_lifespan", lambda *_: None
    )
    data = json.loads(Path("module.json").read_text())
    data["backend"]["module_api_version"] = "999.0.0"
    manifest = tmp_path / "module.json"
    manifest.write_text(json.dumps(data))
    app = FastAPI()
    included = module_registry.include_optional_api_routers(
        app,
        SimpleNamespace(
            API_OPTIONAL_MODULES=str(manifest),
            FEATURE_COOPERATION_LAB=True,
            CORE_MODULE_API_VERSION="1.0.0",
            CORE_RUNTIME_VERSION="1.6.0",
        ),
    )
    assert included == []
    assert app.state.optional_module_diagnostics[0]["state"] != "loaded"


def test_optional_lifecycle_failure_keeps_host_healthy():
    from venom_core.services.module_runtime import include_isolated_router

    @asynccontextmanager
    async def broken(_app):
        raise RuntimeError("private model directory")
        yield  # pragma: no cover - async context protocol

    app = FastAPI()
    app.get("/host-health")(lambda: {"ok": True})
    optional = APIRouter(lifespan=broken)
    optional.get("/lab")(lambda: {"ready": False})
    record = {"state": "loaded", "reason_code": "router_loaded"}
    include_isolated_router(app, optional, record)
    with TestClient(app) as client:
        assert client.get("/host-health").status_code == 200
        assert client.get("/lab").status_code == 503
    assert record["reason_code"] == "module_initialization_failed"


def test_optional_lifecycle_timeout_is_bounded(monkeypatch):
    from venom_core.services import module_runtime

    original = asyncio.wait_for

    async def short_timeout(awaitable, timeout):
        return await original(awaitable, timeout=0.01)

    monkeypatch.setattr(module_runtime.asyncio, "wait_for", short_timeout)

    @asynccontextmanager
    async def slow(_app):
        await asyncio.sleep(10)
        yield

    optional = APIRouter(lifespan=slow)
    optional.get("/lab")(lambda: {"ready": False})
    app = FastAPI()
    record = {"state": "loaded", "reason_code": "router_loaded"}
    module_runtime.include_isolated_router(app, optional, record)
    with TestClient(app) as client:
        assert client.get("/lab").status_code == 503
    assert record["reason_code"] == "module_initialization_failed"
