"""Real bounded SQLite rotation: oldest terminal trial, shared by both histories."""

import time
from dataclasses import replace

import pytest

from venom_module_cooperation_lab.errors import LabError
from venom_module_cooperation_lab.evaluation.store import EvaluationStore
from venom_module_cooperation_lab.storage import LabStore


@pytest.fixture
def store(tmp_path):
    value = LabStore(tmp_path / "lab", lambda _op: None, lambda *_args: None)
    value.open()
    yield value
    value.close()


def legacy(store, identifier, *, owner="local_operator", terminal=True, created=None):
    store.create_run(
        identifier, {}, owner=owner, idempotency_key=identifier, now=created
    )
    if terminal:
        store.set_run_status(identifier, "completed", owner=owner)


def evaluation(store, identifier, *, status="completed", created=None):
    EvaluationStore(store).create(
        {
            "id": identifier,
            "key": identifier,
            "created": created or time.time(),
            "status": status,
            "config": {},
            "episodes": [],
        }
    )


def test_101st_trial_rotates_oldest_across_both_histories_and_cascades_events(store):
    base = time.time() - 1000
    for index in range(50):
        legacy(store, f"run-{index}", created=base + index)
    store.append_event(
        "run-0", "message", {"content": "bounded"}, owner="local_operator"
    )
    for index in range(50):
        evaluation(store, f"eval-{index}", created=base + 50 + index)
    assert store.history_count() == 100
    evaluation(store, "eval-new")
    assert store.history_count() == 100
    with pytest.raises(LabError):
        store.get_run("run-0", owner="local_operator")
    assert (
        store._connection()
        .execute("SELECT count(*) FROM events WHERE run_id='run-0'")
        .fetchone()[0]
        == 0
    )
    assert EvaluationStore(store).get("eval-0")["status"] == "completed"


def test_legacy_insertion_also_rotates_old_evaluation_and_active_is_protected(store):
    store.limits = replace(store.limits, max_runs=2)
    evaluation(store, "old", created=time.time() - 50)
    evaluation(store, "active", status="cleanup_pending")
    legacy(store, "new")
    assert store.history_count() == 2
    with pytest.raises(LabError, match="evaluation_not_found"):
        EvaluationStore(store).get("old")
    assert EvaluationStore(store).get("active")["status"] == "cleanup_pending"
    store.limits = replace(store.limits, max_runs=1)
    with pytest.raises(LabError, match="run_limit_reached"):
        legacy(store, "blocked")
    assert store.history_count() == 2  # Failed reservation deletes nothing.


def test_active_and_foreign_owners_cannot_be_evicted(store):
    store.limits = replace(store.limits, max_runs=1)
    legacy(store, "foreign", owner="someone_else")
    with pytest.raises(LabError, match="run_limit_reached"):
        legacy(store, "mine")
    assert store.get_run("foreign", owner="someone_else")["status"] == "completed"


def test_failed_new_insert_rolls_back_rotation_and_keeps_idempotent_trial(store):
    store.limits = replace(store.limits, max_runs=1)
    legacy(store, "retained")
    store._connection().executescript(
        "CREATE TRIGGER reject_new BEFORE INSERT ON runs WHEN NEW.id='fail' "
        "BEGIN SELECT RAISE(ABORT, 'fixture'); END;"
    )
    with pytest.raises(LabError, match="runtime_busy"):
        legacy(store, "fail")
    assert store.history_count() == 1
    assert store.get_run("retained", owner="local_operator")["status"] == "completed"
    previous = store.create_run(
        "different-id", {}, owner="local_operator", idempotency_key="retained"
    )
    assert previous["id"] == "retained" and store.history_count() == 1
