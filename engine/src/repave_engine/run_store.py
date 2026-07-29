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

from repave_engine.sql_store import (
    DatabaseConfig,
    SqlConnection,
    connect,
    database_config_for_runs_db,
    ensure_schema,
)


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
    """Thread-safe store for async generation runs (SQLite or PostgreSQL)."""

    def __init__(self, db: Path | DatabaseConfig) -> None:
        self._config = db if isinstance(db, DatabaseConfig) else database_config_for_runs_db(db)
        self._lock = threading.RLock()
        with self._lock, connect(self._config) as conn:
            ensure_schema(conn)

    def _connect(self) -> SqlConnection:
        return connect(self._config)

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
            except Exception as exc:
                if client_request_id and "unique" in str(exc).lower():
                    existing = self.get_by_client_request_id(client_request_id)
                    if existing is not None:
                        return existing
                raise
        row = self.get(run_id)
        if row is None:
            raise RuntimeError(f"run row missing immediately after insert: {run_id}")
        return row

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
            row = cur.fetchone()
        return _row_to_record(row) if row else None

    def get_by_client_request_id(self, client_request_id: str) -> RunRecord | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM runs WHERE client_request_id = ?",
                (client_request_id,),
            )
            row = cur.fetchone()
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

    def claim_next_queued(self) -> RunRecord | None:
        """Atomically move one queued run to running (external worker / Job mode)."""
        now = _now_iso()
        with self._lock, self._connect() as conn:
            if conn.dialect == "postgresql":
                cur = conn.execute(
                    """
                    UPDATE runs
                    SET status = ?, updated_at = ?
                    WHERE run_id = (
                        SELECT run_id FROM runs
                        WHERE status = ?
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING run_id
                    """,
                    (RunStatus.RUNNING.value, now, RunStatus.QUEUED.value),
                )
                row = cur.fetchone()
                conn.commit()
                if not row:
                    return None
                run_id = row["run_id"] if isinstance(row, dict) else row[0]
                return self.get(run_id)

            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                SELECT run_id FROM runs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (RunStatus.QUEUED.value,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            run_id = row["run_id"] if isinstance(row, dict) else row[0]
            conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ?",
                (RunStatus.RUNNING.value, now, run_id),
            )
            conn.commit()
        return self.get(run_id)

    def count_by_status(self, *statuses: RunStatus) -> int:
        return sum(self._count_one_status(status) for status in statuses)

    def _count_one_status(self, status: RunStatus) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) AS c FROM runs WHERE status = ?",
                (status.value,),
            )
            row = cur.fetchone()
        if not row:
            return 0
        if isinstance(row, dict):
            return int(row["c"])
        return int(row[0])


def _row_to_record(row: Any) -> RunRecord:
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
