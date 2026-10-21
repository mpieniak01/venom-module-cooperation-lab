from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from venom_core.services import runtime_admission

from venom_module_cooperation_lab.lifecycle import LabLifecycle
from venom_module_cooperation_lab.storage import LabStore


@pytest.mark.asyncio
async def test_off_does_not_acquire_namespace_or_open_storage(monkeypatch):
    monkeypatch.setenv("RUNTIME_ADMISSION_ENABLED", "true")
    admission = Mock(side_effect=AssertionError("OFF must not touch admission"))
    monkeypatch.setattr(runtime_admission, "get_runtime_admission", admission)
    factory = Mock()
    lifecycle = LabLifecycle(factory)
    await lifecycle.start(False)
    assert lifecycle.state == "disabled"
    admission.assert_not_called()
    factory.assert_not_called()


@pytest.mark.asyncio
async def test_c0_disabled_preserves_storage_only_startup(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_ADMISSION_ENABLED", "false")
    admission = Mock(side_effect=AssertionError("disabled C0 must not be acquired"))
    monkeypatch.setattr(runtime_admission, "get_runtime_admission", admission)
    store = LabStore(tmp_path / "lab", Mock(), Mock())
    lifecycle = LabLifecycle(lambda: store)
    await lifecycle.start(True)
    assert store.opened
    await lifecycle.close()
    admission.assert_not_called()


def test_second_worker_cannot_recover_or_interrupt_first_workers_run(tmp_path):
    ledger = tmp_path / "admission.sqlite3"
    root = tmp_path / "module"
    store = LabStore(root, Mock(), Mock())
    store.open()
    store.create_run(
        "owned-run", {}, owner="local_operator", idempotency_key="owned-run"
    )
    store.set_run_status("owned-run", "running", owner="local_operator")
    store.close()
    first = runtime_admission.RuntimeAdmission(ledger, enabled=True)
    with first.operation(kind="module_startup_check"):
        pass
    child = """
import asyncio, json, sys
from pathlib import Path
from venom_core.services import runtime_admission
from venom_module_cooperation_lab.lifecycle import LabLifecycle
from venom_module_cooperation_lab.storage import LabStore
runtime_admission._ADMISSION = runtime_admission.RuntimeAdmission(
    Path(sys.argv[1]),enabled=True)
store=LabStore(Path(sys.argv[2]),lambda _op:None,lambda _owner,_op:None)
lifecycle=LabLifecycle(lambda:store)
asyncio.run(lifecycle.start(True))
print(json.dumps({'opened':store.opened,'state':lifecycle.state,'reason':lifecycle.reason}))
"""
    env = dict(os.environ, RUNTIME_ADMISSION_ENABLED="true", ENV_FILE="/dev/null")
    # Keep the module source location explicit because the child uses a safe cwd.
    env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + os.environ.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", child, str(ledger), str(root)],
        capture_output=True,
        text=True,
        timeout=10,
        env=env,
        cwd=tmp_path,
        check=True,
    )
    assert json.loads(result.stdout) == {
        "opened": False,
        "state": "not_ready",
        "reason": "runtime_topology_unsupported",
    }
    db = sqlite3.connect(f"file:{root / 'lab.sqlite3'}?mode=ro", uri=True)
    try:
        assert (
            db.execute("SELECT status FROM runs WHERE id='owned-run'").fetchone()[0]
            == "running"
        )
    finally:
        db.close()


@pytest.mark.asyncio
async def test_enabled_startup_holds_namespace_before_every_storage_mutation(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("RUNTIME_ADMISSION_ENABLED", "true")
    admission = runtime_admission.RuntimeAdmission(
        tmp_path / "first.sqlite3", enabled=True
    )
    monkeypatch.setattr(runtime_admission, "get_runtime_admission", lambda: admission)
    observed = []

    def guard(operation):
        observed.append((operation, admission.snapshot()["active_operations"]))

    store = LabStore(tmp_path / "lab", guard, Mock())
    lifecycle = LabLifecycle(lambda: store)
    await lifecycle.start(True)
    assert store.opened
    assert observed and all(count == 1 for _operation, count in observed)
    assert admission.snapshot()["status"] == "available"
    await lifecycle.close()


@pytest.mark.asyncio
async def test_startup_rejects_stale_disabled_admission_before_open(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("RUNTIME_ADMISSION_ENABLED", "true")
    admission = runtime_admission.RuntimeAdmission(
        tmp_path / "disabled.sqlite3", enabled=False
    )
    monkeypatch.setattr(runtime_admission, "get_runtime_admission", lambda: admission)
    store = LabStore(tmp_path / "never-created", Mock(), Mock())
    lifecycle = LabLifecycle(lambda: store)
    await lifecycle.start(True)
    assert lifecycle.reason == "runtime_admission_disabled"
    assert not store.opened
    assert not store.root.exists()
    assert not admission.database.exists()
