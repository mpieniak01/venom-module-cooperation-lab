"""Namespaced SQLite storage with explicit guards and bounded retained payloads.

Creation is explicit. The trusted host supplies actor/access policy; a model never
chooses its owner. Every read/export/delete checks it again. No background jobs.
"""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .errors import LabError
from .limits import Limits

STATE_FILES = ("lab.sqlite3", "lab.sqlite3-wal", "lab.sqlite3-shm")
ACTIVE = ("created", "queued", "preparing", "running", "cancelling")
TERMINAL = ("completed", "failed", "cancelled", "interrupted")
_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise LabError("invalid_id", 400)
    return value


def _json(value: Any, limit: int) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise LabError("invalid_payload", 400) from exc
    if len(encoded.encode("utf-8")) > limit:
        raise LabError("payload_too_large", 413)
    return encoded


class LabStore:
    def __init__(
        self,
        root: Path,
        mutation_guard: Callable[[str], None],
        access_guard: Callable[[str, str], None],
        limits: Limits | None = None,
    ) -> None:
        self.root = root
        self.limits = limits or Limits()
        self._guard = mutation_guard
        self._access = access_guard
        self._db: sqlite3.Connection | None = None
        self._lock = threading.RLock()

    @classmethod
    def from_host(cls, access_guard: Callable[[str, str], None]) -> LabStore:
        from venom_core.core.module_data_policy import (
            ensure_module_mutation_allowed,
            resolve_module_data_root,
        )

        return cls(
            resolve_module_data_root(module_id="cooperation_lab"),
            lambda operation: ensure_module_mutation_allowed(
                module_id="cooperation_lab", operation_name=operation
            ),
            access_guard,
        )

    @property
    def opened(self) -> bool:
        return self._db is not None

    def _connection(self) -> sqlite3.Connection:
        if self._db is None:
            raise LabError("storage_not_ready", 503)
        return self._db

    def _space(self, reserve: int = 0) -> None:
        probe = self.root
        while not probe.exists():
            probe = probe.parent
        used = sum(
            item.stat().st_size
            for name in STATE_FILES
            if (item := self.root / name).exists()
        )
        if used + reserve > self.limits.database_bytes:
            raise LabError("storage_full", 507)
        if shutil.disk_usage(probe).free < self.limits.minimum_free_bytes + reserve:
            raise LabError("disk_space_low", 507)

    def open(self) -> None:
        with self._lock:
            if self.opened:
                return
            self._guard("storage.open")
            self._space()
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            # Avoid following a replaced namespaced state file outside the scope.
            if self.root.is_symlink() or any(
                (self.root / name).is_symlink() for name in STATE_FILES
            ):
                raise LabError("unsafe_storage", 503)
            db = sqlite3.connect(
                self.root / STATE_FILES[0], timeout=1, check_same_thread=False
            )
            db.row_factory = sqlite3.Row
            self._db = db
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA wal_autocheckpoint=32")
                db.execute("PRAGMA journal_size_limit=1048576")
                self._migrate()
                with self._transaction("restart.recover"):
                    db.execute(
                        "UPDATE runs SET status='interrupted' "
                        "WHERE status IN ('created','queued','preparing',"
                        "'running','cancelling')"
                    )
            except BaseException:
                db.close()
                self._db = None
                raise
            (self.root / STATE_FILES[0]).chmod(0o600)

    def _migrate(self) -> None:
        db = self._connection()
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            raise LabError("storage_schema_unsupported", 503)
        if version == 1:
            return
        # executescript manages its own transaction: an explicit BEGIN/COMMIT
        # keeps the DDL and schema version indivisible even after a crash.
        db.executescript(
            "BEGIN IMMEDIATE;"
            "CREATE TABLE runs (id TEXT PRIMARY KEY, owner TEXT NOT NULL, "
            "idempotency_key TEXT NOT NULL, created REAL NOT NULL, "
            "status TEXT NOT NULL, config TEXT NOT NULL, "
            "bytes INTEGER NOT NULL, next_seq INTEGER NOT NULL DEFAULT 1, "
            "UNIQUE(owner,idempotency_key));"
            "CREATE UNIQUE INDEX one_active ON runs ((1)) WHERE status IN "
            "('created','queued','preparing','running','cancelling');"
            "CREATE TABLE events (run_id TEXT NOT NULL REFERENCES runs(id) "
            "ON DELETE CASCADE, seq INTEGER NOT NULL, kind TEXT NOT NULL, "
            "payload TEXT NOT NULL, timestamp REAL NOT NULL, "
            "PRIMARY KEY(run_id,seq));"
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);"
            "CREATE TABLE qualifications (id TEXT PRIMARY KEY, "
            "value TEXT NOT NULL);"
            "PRAGMA user_version=1;COMMIT;"
        )

    @contextmanager
    def _transaction(self, operation: str, reserve: int = 0) -> Iterator[None]:
        self._guard(operation)
        self._space(reserve)
        db = self._connection()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield
            self._space()
            db.commit()
        except sqlite3.OperationalError as exc:
            db.rollback()
            raise LabError("storage_unavailable", 507) from exc
        except BaseException:
            db.rollback()
            raise

    def close(self) -> None:
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

    def _row(self, run_id: str, owner: str) -> sqlite3.Row:
        self._access(owner, "runs.read")
        row = (
            self._connection()
            .execute(
                "SELECT * FROM runs WHERE id=? AND owner=?",
                (_identifier(run_id), _identifier(owner)),
            )
            .fetchone()
        )
        if row is None:
            raise LabError("run_not_found", 404)
        return row

    @staticmethod
    def _run(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "owner": row["owner"],
            "created": row["created"],
            "status": row["status"],
            "config": json.loads(row["config"]),
            "bytes": row["bytes"],
            "last_seq": row["next_seq"] - 1,
        }

    def create_run(
        self,
        run_id: str,
        config: dict[str, Any],
        *,
        owner: str,
        idempotency_key: str,
        now: float | None = None,
    ) -> dict[str, Any]:
        _identifier(run_id)
        _identifier(owner)
        _identifier(idempotency_key)
        encoded = _json(config, self.limits.run_bytes)
        size = len(encoded.encode("utf-8"))
        with self._lock:
            self._access(owner, "runs.create")
            db = self._connection()
            previous = db.execute(
                "SELECT * FROM runs WHERE owner=? AND idempotency_key=?",
                (owner, idempotency_key),
            ).fetchone()
            if previous is not None:
                if previous["config"] != encoded:
                    raise LabError("idempotency_conflict")
                return self._run(previous)
            self.cleanup(now=now)
            count = db.execute("SELECT count(*) FROM runs").fetchone()[0]
            if count >= self.limits.max_runs:
                raise LabError("run_limit_reached")
            try:
                with self._transaction("runs.create", size + 16384):
                    db.execute(
                        "INSERT INTO runs(id,owner,idempotency_key,created,"
                        "status,config,bytes) VALUES (?,?,?,?,'created',?,?)",
                        (
                            run_id,
                            owner,
                            idempotency_key,
                            time.time() if now is None else now,
                            encoded,
                            size,
                        ),
                    )
            except sqlite3.IntegrityError as exc:
                raise LabError("runtime_busy") from exc
            return self.get_run(run_id, owner=owner)

    def get_run(self, run_id: str, *, owner: str) -> dict[str, Any]:
        with self._lock:
            return self._run(self._row(run_id, owner))

    def list_runs(
        self,
        *,
        owner: str,
        limit: int = 20,
        after: str | None = None,
    ) -> list[dict[str, Any]]:
        _identifier(owner)
        if not 1 <= limit <= 100:
            raise LabError("invalid_page", 400)
        with self._lock:
            self._access(owner, "runs.list")
            rows = self._connection().execute(
                "SELECT * FROM runs WHERE owner=? AND id>? ORDER BY id LIMIT ?",
                (owner, _identifier(after) if after else "", limit),
            )
            return [self._run(row) for row in rows]

    def set_run_status(self, run_id: str, status: str, *, owner: str) -> None:
        if status not in ACTIVE + TERMINAL:
            raise LabError("invalid_status", 400)
        with self._lock:
            self._row(run_id, owner)
            self._access(owner, "runs.update")
            with self._transaction("runs.update"):
                self._connection().execute(
                    "UPDATE runs SET status=? WHERE id=?", (status, run_id)
                )

    def append_event(
        self,
        run_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        owner: str,
    ) -> dict[str, Any]:
        _identifier(kind)
        encoded = _json(payload, self.limits.event_bytes)
        size = len(encoded.encode("utf-8")) + len(kind) + 64
        with self._lock:
            row = self._row(run_id, owner)
            self._access(owner, "events.append")
            if row["bytes"] + size > self.limits.run_bytes:
                raise LabError("run_storage_full", 507)
            seq, timestamp = row["next_seq"], time.time()
            with self._transaction("events.append", size + 8192):
                self._connection().execute(
                    "INSERT INTO events VALUES (?,?,?,?,?)",
                    (run_id, seq, kind, encoded, timestamp),
                )
                self._connection().execute(
                    "UPDATE runs SET bytes=bytes+?,next_seq=next_seq+1 WHERE id=?",
                    (size, run_id),
                )
            return {
                "seq": seq,
                "kind": kind,
                "payload": payload,
                "timestamp": timestamp,
                "run_id": run_id,
            }

    def events(
        self,
        run_id: str,
        *,
        owner: str,
        after: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if after < 0 or not 1 <= limit <= 100:
            raise LabError("invalid_page", 400)
        with self._lock:
            self._row(run_id, owner)
            rows = self._connection().execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
                (run_id, after, limit),
            )
            return [
                {
                    "seq": row["seq"],
                    "kind": row["kind"],
                    "payload": json.loads(row["payload"]),
                    "timestamp": row["timestamp"],
                    "run_id": run_id,
                }
                for row in rows
            ]

    def delete_run(self, run_id: str, *, owner: str) -> None:
        with self._lock:
            row = self._row(run_id, owner)
            self._access(owner, "runs.delete")
            if row["status"] in ACTIVE:
                raise LabError("run_active")
            with self._transaction("runs.delete"):
                self._connection().execute("DELETE FROM runs WHERE id=?", (run_id,))

    def export_run(self, run_id: str, *, owner: str) -> bytes:
        with self._lock:
            row = self._row(run_id, owner)
            self._access(owner, "runs.export")
            # Read bounded pages, no permanent second copy or unbounded SQL export.
            events: list[dict[str, Any]] = []
            cursor = 0
            while page := self.events(run_id, owner=owner, after=cursor):
                events.extend(page)
                cursor = page[-1]["seq"]
            return _json(
                {"schema_version": 1, "run": self._run(row), "events": events},
                self.limits.run_bytes * 2,
            ).encode("utf-8")

    def cleanup(self, *, now: float | None = None) -> int:
        with self._lock:
            db = self._connection()
            cutoff = (time.time() if now is None else now) - (
                self.limits.retention_days * 86400
            )
            with self._transaction("retention.cleanup"):
                count = db.execute(
                    "DELETE FROM runs WHERE created<? AND status IN "
                    "('completed','failed','cancelled','interrupted')",
                    (cutoff,),
                ).rowcount
            return count

    def put_document(
        self, kind: str, key: str, value: dict[str, Any], *, owner: str
    ) -> None:
        _identifier(key)
        if kind not in {"settings", "qualifications"}:
            raise LabError("invalid_document", 400)
        encoded = _json(value, self.limits.event_bytes)
        column = "key" if kind == "settings" else "id"
        with self._lock:
            self._access(owner, "documents.write")
            # Metadata is bounded separately to keep it from bypassing run quotas.
            count = (
                self._connection().execute(f"SELECT count(*) FROM {kind}").fetchone()[0]
            )
            exists = (
                self._connection()
                .execute(f"SELECT 1 FROM {kind} WHERE {column}=?", (key,))
                .fetchone()
            )
            if count >= 100 and exists is None:
                raise LabError("document_limit_reached")
            with self._transaction("documents.write", len(encoded.encode()) + 8192):
                self._connection().execute(
                    f"INSERT OR REPLACE INTO {kind} VALUES (?,?)", (key, encoded)
                )

    def get_document(self, kind: str, key: str, *, owner: str) -> dict[str, Any] | None:
        _identifier(key)
        if kind not in {"settings", "qualifications"}:
            raise LabError("invalid_document", 400)
        column = "key" if kind == "settings" else "id"
        with self._lock:
            self._access(owner, "documents.read")
            row = (
                self._connection()
                .execute(f"SELECT value FROM {kind} WHERE {column}=?", (key,))
                .fetchone()
            )
            return json.loads(row[0]) if row else None
