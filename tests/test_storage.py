from __future__ import annotations

import sqlite3
from dataclasses import replace
from unittest.mock import Mock

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.limits import Limits
from venom_module_cooperation_lab.storage import STATE_FILES, LabStore


@pytest.fixture
def store(tmp_path):
    result = LabStore(tmp_path / "lab", lambda _op: None, lambda _owner, _op: None)
    result.open()
    yield result
    result.close()


def create(store, run_id="r1", **kwargs):
    return store.create_run(
        run_id,
        {"scenario": "split"},
        owner="operator",
        idempotency_key=run_id,
        **kwargs,
    )


def test_explicit_creation_guarded(tmp_path):
    guard = Mock(side_effect=PermissionError("denied"))
    result = LabStore(tmp_path / "lab", guard, Mock())
    assert not result.root.exists()
    with pytest.raises(PermissionError):
        result.open()
    assert not result.root.exists()
    guard.assert_called_once_with("storage.open")
    with pytest.raises(LabError, match="storage_not_ready"):
        result.get_run("r1", owner="operator")


def test_migrate_resume_and_no_auto_run(store):
    create(store)
    assert store.get_run("r1", owner="operator")["status"] == "created"
    store.close()
    store.open()
    store.open()
    assert store.get_run("r1", owner="operator")["status"] == "interrupted"
    assert store._connection().execute("PRAGMA user_version").fetchone()[0] == 1
    assert (store.root / "lab.sqlite3").stat().st_mode & 0o777 == 0o600


def test_unknown_future_schema_rejected(tmp_path):
    root = tmp_path / "lab"
    root.mkdir()
    with sqlite3.connect(root / "lab.sqlite3") as db:
        db.execute("PRAGMA user_version=99")
    db.close()
    result = LabStore(root, Mock(), Mock())
    with pytest.raises(LabError, match="storage_schema_unsupported"):
        result.open()
    assert not result.opened


def test_symbolic_state_rejected(tmp_path):
    root = tmp_path / "lab"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("private")
    (root / "lab.sqlite3").symlink_to(outside)
    with pytest.raises(LabError, match="unsafe_storage"):
        LabStore(root, Mock(), Mock()).open()
    assert outside.read_text() == "private"


def test_idempotency_active_limit_and_owner_isolation(store):
    first = create(store)
    assert create(store) == first
    with pytest.raises(LabError, match="idempotency_conflict"):
        store.create_run("new", {}, owner="operator", idempotency_key="r1")
    with pytest.raises(LabError, match="runtime_busy"):
        create(store, "r2")
    with pytest.raises(LabError, match="run_not_found"):
        store.get_run("r1", owner="other")
    assert store.list_runs(owner="other") == []
    with pytest.raises(LabError, match="run_active"):
        store.delete_run("r1", owner="operator")


def test_sequence_export_and_pagination(store):
    create(store)
    a = store.append_event("r1", "message", {"text": "żółć"}, owner="operator")
    b = store.append_event("r1", "message", {"text": "answer"}, owner="operator")
    assert (a["seq"], b["seq"]) == (1, 2)
    assert store.events("r1", owner="operator", after=1) == [b]
    assert store.events("r1", owner="operator", limit=1) == [a]
    exported = store.export_run("r1", owner="operator")
    assert b"answer" in exported
    assert set(item.name for item in store.root.iterdir()) <= set(STATE_FILES)
    assert store.get_run("r1", owner="operator")["last_seq"] == 2
    store.set_run_status("r1", "completed", owner="operator")
    create(store, "r2")
    assert [r["id"] for r in store.list_runs(owner="operator", after="r1")] == ["r2"]
    store.delete_run("r1", owner="operator")
    assert store._connection().execute("SELECT count(*) FROM events").fetchone()[0] == 0


def test_event_and_run_payload_limits(store):
    create(store)
    store.limits = replace(store.limits, event_bytes=10)
    with pytest.raises(LabError, match="payload_too_large"):
        store.append_event("r1", "message", {"text": "abc"}, owner="operator")
    store.limits = replace(store.limits, event_bytes=1024, run_bytes=32)
    with pytest.raises(LabError, match="run_storage_full"):
        store.append_event("r1", "message", {}, owner="operator")
    with pytest.raises(LabError, match="invalid_payload"):
        store.append_event("r1", "message", {"bad": object()}, owner="operator")
    with pytest.raises(LabError, match="invalid_payload"):
        store.append_event("r1", "message", {"bad": float("nan")}, owner="operator")


def test_disk_and_wal_included(store, monkeypatch):
    store.limits = replace(store.limits, database_bytes=1)
    with pytest.raises(LabError, match="storage_full"):
        create(store)
    store.limits = Limits()
    monkeypatch.setattr("shutil.disk_usage", lambda _root: Mock(free=0))
    with pytest.raises(LabError, match="disk_space_low"):
        create(store)


def test_transaction_rollback_keeps_prior_data(store):
    create(store)
    with pytest.raises(RuntimeError):
        with store._transaction("test.rollback"):
            store._connection().execute("UPDATE runs SET status='completed'")
            raise RuntimeError("crash")
    assert store.get_run("r1", owner="operator")["status"] == "created"
    with pytest.raises(LabError, match="storage_unavailable"):
        with store._transaction("test.rollback"):
            store._connection().execute("SELECT * FROM nonexistent")


def test_retention_never_removes_active_runs(store):
    create(store, now=0)
    assert store.cleanup(now=2000000) == 0
    store.set_run_status("r1", "completed", owner="operator")
    assert store.cleanup(now=2000000) == 1
    assert store.list_runs(owner="operator") == []
    store.limits = replace(store.limits, max_runs=1)
    create(store, now=2000000)
    store.set_run_status("r1", "completed", owner="operator")
    create(store, "r2", now=2000000)
    assert [r["id"] for r in store.list_runs(owner="operator")] == ["r2"]


def test_all_access_and_mutations_are_guarded(store):
    create(store)
    store._access = Mock(side_effect=PermissionError("no access"))
    with pytest.raises(PermissionError):
        store.export_run("r1", owner="operator")
    with pytest.raises(PermissionError):
        store.delete_run("r1", owner="operator")
    store._access = Mock()
    store._guard = Mock(side_effect=PermissionError("read only"))
    assert store.get_run("r1", owner="operator")["status"] == "created"
    with pytest.raises(PermissionError):
        store.set_run_status("r1", "completed", owner="operator")


@pytest.mark.parametrize("value", ["../private", "a/b", "", "a" * 129])
def test_safe_identifiers(store, value):
    with pytest.raises(LabError, match="invalid_id"):
        create(store, value)


def test_invalid_limits_page_status_and_document(store):
    with pytest.raises(ValueError, match="limits_must_be_positive"):
        Limits(max_runs=0)
    with pytest.raises(LabError, match="invalid_page"):
        store.list_runs(owner="operator", limit=0)
    with pytest.raises(LabError, match="invalid_page"):
        store.events("r1", owner="operator", after=-1)
    with pytest.raises(LabError, match="invalid_status"):
        store.set_run_status("r1", "unknown", owner="operator")
    with pytest.raises(LabError, match="invalid_document"):
        store.put_document("runs", "key", {}, owner="operator")
    with pytest.raises(LabError, match="invalid_document"):
        store.get_document("runs", "key", owner="operator")


def test_documents_quota_and_upsert(store):
    assert store.get_document("settings", "a", owner="operator") is None
    for index in range(100):
        store.put_document("qualifications", str(index), {"x": index}, owner="operator")
    with pytest.raises(LabError, match="document_limit_reached"):
        store.put_document("qualifications", "extra", {}, owner="operator")
    store.put_document("qualifications", "0", {"x": "changed"}, owner="operator")
    assert store.get_document("qualifications", "0", owner="operator") == {
        "x": "changed"
    }
    store.put_document("settings", "a", {}, owner="operator")
    assert store.get_document("settings", "a", owner="operator") == {}


def test_reclaim_overlimit_and_low_space_without_new_writes(store, monkeypatch):
    create(store)
    store.set_run_status("r1", "completed", owner="operator")
    store.limits = replace(store.limits, database_bytes=1)
    monkeypatch.setattr("shutil.disk_usage", lambda _root: Mock(free=2 * 1024 * 1024))
    store.close()
    store.open()
    assert store.get_run("r1", owner="operator")["status"] == "completed"
    with pytest.raises(LabError, match="storage_full"):
        store.append_event("r1", "message", {}, owner="operator")
    store.delete_run("r1", owner="operator")
    assert store.list_runs(owner="operator") == []
    assert (store.root / "lab.sqlite3-wal").stat().st_size == 0


def test_namespace_parent_symlink_is_rejected_before_writes(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "scope"
    link.symlink_to(outside, target_is_directory=True)
    store = LabStore(link / "cooperation_lab", Mock(), Mock())
    with pytest.raises(LabError, match="unsafe_storage"):
        store.open()
    assert list(outside.iterdir()) == []


def test_export_has_explicit_limit(store):
    create(store)
    store.limits = replace(store.limits, run_bytes=1)
    with pytest.raises(LabError, match="export_too_large"):
        store.export_run("r1", owner="operator")


def test_checkpoint_failure_is_sanitized(store):
    class FailingDatabase:
        def execute(self, _sql):
            raise sqlite3.OperationalError("private path")

    original = store._db
    store._db = FailingDatabase()
    try:
        with pytest.raises(LabError, match="storage_unavailable"):
            store._checkpoint()
    finally:
        store._db = original
