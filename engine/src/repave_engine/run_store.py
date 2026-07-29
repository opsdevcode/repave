"""SQLite-backed generation run records for async queue (Phase 1 durability)."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class RunStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: RunStatus
    blueprint_name: str
    dry_run: bool
    client_request_id: str | None
    acting_user: str
    created_at: str
    updated_at: str
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status.value,
            "blueprint": self.blueprint_name,
            "dry_run": self.dry_run,
            "acting_user": self.acting_user,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.client_request_id:
            body["client_request_id"] = self.client_request_id
        if self.result is not None:
            body["result"] = self.result
        if self.error:
            body["error"] = self.error
        return body


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunStore:
    """Thread-safe SQLite store for async generation runs."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    CREATE TABLE IF NOT EXISTS runs (
                        run_id TEXT PRIMARY KEY,
                        client_request_id TEXT UNIQUE,
                        status TEXT NOT NULL,
                        blueprint_name TEXT NOT NULL,
                        dry_run INTEGER NOT NULL,
                        acting_user TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        result_json TEXT,
                        error TEXT
                    )
                    """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
            conn.commit()

    def create_run(
        self,
        *,
        blueprint_name: str,
        dry_run: bool,
        payload: dict[str, Any],
        acting_user: str,
        client_request_id: str | None = None,
    ) -> RunRecord:
        run_id = str(uuid.uuid4())
        now = _now_iso()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                        INSERT INTO runs (
                            run_id, client_request_id, status, blueprint_name,
                            dry_run, acting_user, created_at, updated_at,
                            payload_json, result_json, error
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                        """,
                    (
                        run_id,
                        client_request_id,
                        RunStatus.QUEUED.value,
                        blueprint_name,
                        1 if dry_run else 0,
                        acting_user,
                        now,
                        now,
                        json.dumps(payload, separators=(",", ":")),
                    ),
                )
                conn.commit()
            except sqlite3.IntegrityError as exc:
                if client_request_id:
                    existing = self.get_by_client_request_id(client_request_id)
                    if existing is not None:
                        return existing
                raise exc
        row = self.get(run_id)
        if row is None:
            raise RuntimeError(f"run row missing immediately after insert: {run_id}")
        return row

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return _row_to_record(row) if row else None

    def get_by_client_request_id(self, client_request_id: str) -> RunRecord | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM runs WHERE client_request_id = ?",
                (client_request_id,),
            ).fetchone()
        return _row_to_record(row) if row else None

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        now = _now_iso()
        result_json = json.dumps(result, separators=(",", ":")) if result is not None else None
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    UPDATE runs
                    SET status = ?, updated_at = ?, result_json = ?, error = ?
                    WHERE run_id = ?
                    """,
                (status.value, now, result_json, error, run_id),
            )
            conn.commit()

    def count_by_status(self, *statuses: RunStatus) -> int:
        return sum(self._count_one_status(status) for status in statuses)

    def _count_one_status(self, status: RunStatus) -> int:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM runs WHERE status = ?",
                (status.value,),
            ).fetchone()
        return int(row["c"]) if row else 0


def _row_to_record(row: sqlite3.Row) -> RunRecord:
    payload = json.loads(row["payload_json"])
    result_raw = row["result_json"]
    result = json.loads(result_raw) if result_raw else None
    client_id = row["client_request_id"]
    return RunRecord(
        run_id=row["run_id"],
        status=RunStatus(row["status"]),
        blueprint_name=row["blueprint_name"],
        dry_run=bool(row["dry_run"]),
        client_request_id=str(client_id) if client_id else None,
        acting_user=row["acting_user"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        payload=payload,
        result=result,
        error=row["error"],
    )
