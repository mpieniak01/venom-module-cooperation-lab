"""Evaluation snapshots in the existing guarded/quota-controlled module SQLite."""

from __future__ import annotations

import json
import time
from typing import Any

from ..errors import LabError
from ..storage import LabStore, _identifier, _json


class EvaluationStore:
    def __init__(self, store: LabStore):
        self.store = store

    def exists(self) -> bool:
        return (
            self.store._connection()
            .execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evaluations'"
            )
            .fetchone()
            is not None
        )

    def prepare(self) -> None:
        with self.store._lock, self.store._transaction("evaluations.schema"):
            self.store._connection().execute(
                "CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY, "
                "owner TEXT NOT NULL, key TEXT NOT NULL, created REAL NOT NULL, "
                "status TEXT NOT NULL, error TEXT, config TEXT NOT NULL, "
                "state TEXT NOT NULL, UNIQUE(owner,key))"
            )

    def list(self) -> list[dict[str, Any]]:
        self.store._access("local_operator", "evaluations.read")
        with self.store._lock:
            if not self.exists():
                return []
            rows = (
                self.store._connection()
                .execute(
                    "SELECT * FROM evaluations WHERE owner='local_operator' "
                    "ORDER BY created DESC LIMIT 100"
                )
                .fetchall()
            )
            return [self._decode(r) for r in rows]

    def count(self) -> int:
        self.store._access("local_operator", "evaluations.read")
        with self.store._lock:
            if not self.exists():
                return 0
            return int(
                self.store._connection()
                .execute(
                    "SELECT count(*) FROM evaluations WHERE owner='local_operator'"
                )
                .fetchone()[0]
            )

    def _find(self, field: str, value: str) -> dict[str, Any] | None:
        _identifier(value)
        self.store._access("local_operator", "evaluations.read")
        with self.store._lock:
            if not self.exists():
                return None
            # Both callers below use a literal column; values remain bound.
            column = "id" if field == "id" else "key"
            row = (
                self.store._connection()
                .execute(
                    "SELECT * FROM evaluations WHERE owner='local_operator' AND "
                    + column
                    + "=?",
                    (value,),
                )
                .fetchone()
            )
            return self._decode(row) if row is not None else None

    def get(self, eid: str) -> dict[str, Any]:
        row = self._find("id", eid)
        if row is None:
            raise LabError("evaluation_not_found", 404)
        return row

    def by_key(self, key: str) -> dict[str, Any] | None:
        return self._find("key", key)

    @staticmethod
    def _decode(row: Any) -> dict[str, Any]:
        result = json.loads(row["state"])
        result.update(status=row["status"], error=row["error"])
        return result

    def create(self, state: dict[str, Any]) -> None:
        self.prepare()
        text = _json(state, self.store.limits.run_bytes - 8192)
        with (
            self.store._lock,
            self.store._transaction("evaluations.create", len(text.encode()) + 16384),
        ):
            db = self.store._connection()
            db.execute(
                "DELETE FROM evaluations WHERE created<? AND status NOT IN "
                "('queued','running','cancelling','cleanup_pending')",
                (time.time() - self.store.limits.retention_days * 86400,),
            )
            self.store._rotate_completed(owner="local_operator")
            db.execute(
                "INSERT INTO evaluations VALUES(?,?,?,?,?,?,?,?)",
                (
                    state["id"],
                    "local_operator",
                    state["key"],
                    state["created"],
                    state["status"],
                    None,
                    json.dumps(state["config"], sort_keys=True),
                    text,
                ),
            )

    def save(self, state: dict[str, Any]) -> None:
        text = _json(state, self.store.limits.run_bytes - 8192)
        with (
            self.store._lock,
            self.store._transaction("evaluations.update", len(text.encode()) + 8192),
        ):
            self.store._connection().execute(
                "UPDATE evaluations SET status=?,error=?,state=? "
                "WHERE id=? AND owner='local_operator'",
                (state["status"], state.get("error"), text, state["id"]),
            )

    def terminal(self, eid: str, status: str, error: str | None = None) -> None:
        with (
            self.store._lock,
            self.store._transaction("evaluations.finish", reclaim=True),
        ):
            self.store._connection().execute(
                "UPDATE evaluations SET status=?,error=? "
                "WHERE id=? AND owner='local_operator'",
                (status, error, eid),
            )

    def delete(self, eid: str) -> None:
        _identifier(eid)
        with (
            self.store._lock,
            self.store._transaction("evaluations.delete", reclaim=True),
        ):
            self.store._connection().execute(
                "DELETE FROM evaluations WHERE id=? AND owner='local_operator'", (eid,)
            )

    def recover(self) -> None:
        if not self.exists():
            return
        for row in self.list():
            if row["status"] in {"queued", "running", "cancelling", "cleanup_pending"}:
                self.terminal(row["id"], "interrupted", "process_restarted")
