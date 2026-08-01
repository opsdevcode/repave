"""SQLite-backed generation run records for async queue (Phase 1 durability)."""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from repave_engine.sql_store import (
    DatabaseConfig,
    SqlConnection,
    connect,
    database_config_for_runs_db,
    ensure_schema,
    is_unique_constraint_error,
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
    attempt_count: int = 0
    next_attempt_at: str | None = None

    def to_public_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "run_id": self.run_id,
            "status": self.status.value,
            "dry_run": self.dry_run,
            "acting_user": self.acting_user,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "attempt_count": self.attempt_count,
        }
        kind = str(self.payload.get("kind", "")).strip()
        if kind:
            body["kind"] = kind
        if self.payload.get("bundle"):
            body["bundle"] = str(self.payload["bundle"])
        elif kind == "environment_vend":
            vend_blueprint = str(self.payload.get("blueprint", "")).strip()
            if vend_blueprint:
                body["blueprint"] = vend_blueprint
        elif kind != "live_plan":
            body["blueprint"] = self.blueprint_name
        inputs = self.payload.get("inputs")
        if isinstance(inputs, dict):
            entity_id = str(inputs.get("entity_id", "")).strip()
            if entity_id:
                body["entity_id"] = entity_id
            stack_name = str(inputs.get("stack_name", "")).strip()
            if stack_name:
                body["stack_name"] = stack_name
        if self.client_request_id:
            body["client_request_id"] = self.client_request_id
        if self.next_attempt_at:
            body["next_attempt_at"] = self.next_attempt_at
        if self.result is not None:
            body["result"] = self.result
        if self.error:
            body["error"] = self.error
        return body


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


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
                            payload_json, result_json, error, attempt_count,
                            next_attempt_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, 0, NULL)
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
            except Exception as exc:
                if client_request_id and is_unique_constraint_error(exc):
                    existing = self.get_by_client_request_id(client_request_id)
                    if existing is not None:
                        return existing
                raise
        row = self.get(run_id)
        if row is None:
            raise RuntimeError(
                f"run row missing immediately after insert: {run_id}; "
                "check database connectivity and schema"
            )
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

    def list_runs(
        self,
        *,
        status: RunStatus | None = None,
        limit: int = 50,
    ) -> list[RunRecord]:
        limit = max(1, min(limit, 200))
        with self._lock, self._connect() as conn:
            if status is None:
                cur = conn.execute(
                    """
                    SELECT * FROM runs
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                )
            else:
                cur = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE status = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (status.value, limit),
                )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
        return [_row_to_record(row) for row in rows]

    def update_status(
        self,
        run_id: str,
        status: RunStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        next_attempt_at: str | None = None,
        clear_next_attempt: bool = False,
    ) -> None:
        now = _now_iso()
        result_json = json.dumps(result, separators=(",", ":")) if result is not None else None
        next_raw = None if clear_next_attempt else next_attempt_at
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    UPDATE runs
                    SET status = ?, updated_at = ?, result_json = ?, error = ?,
                        next_attempt_at = ?
                    WHERE run_id = ?
                    """,
                (status.value, now, result_json, error, next_raw, run_id),
            )
            conn.commit()

    def reset_for_replay(self, run_id: str) -> None:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    UPDATE runs
                    SET status = ?, updated_at = ?, result_json = NULL, error = NULL,
                        attempt_count = 0, next_attempt_at = NULL
                    WHERE run_id = ?
                    """,
                (RunStatus.QUEUED.value, now, run_id),
            )
            conn.commit()

    def schedule_retry(
        self,
        run_id: str,
        *,
        attempt_count: int,
        error: str,
        next_attempt_at: str,
    ) -> None:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                    UPDATE runs
                    SET status = ?, updated_at = ?, error = ?,
                        attempt_count = ?, next_attempt_at = ?,
                        result_json = NULL
                    WHERE run_id = ?
                    """,
                (
                    RunStatus.QUEUED.value,
                    now,
                    error,
                    attempt_count,
                    next_attempt_at,
                    run_id,
                ),
            )
            conn.commit()

    def reclaim_stale_runs(
        self,
        *,
        stale_after_seconds: int,
        max_attempts: int,
    ) -> int:
        """Requeue or dead-letter runs stuck in running after worker loss."""
        if stale_after_seconds <= 0:
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
        cutoff_iso = cutoff.isoformat()
        reclaimed = 0
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                SELECT run_id, attempt_count FROM runs
                WHERE status = ? AND updated_at < ?
                """,
                (RunStatus.RUNNING.value, cutoff_iso),
            )
            rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
            for row in rows:
                run_id = row["run_id"] if isinstance(row, dict) else row[0]
                attempts = int(row["attempt_count"] if isinstance(row, dict) else row[1])
                next_attempt = attempts + 1
                now = _now_iso()
                if next_attempt >= max_attempts:
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = ?, updated_at = ?, error = ?,
                            attempt_count = ?, next_attempt_at = NULL
                        WHERE run_id = ?
                        """,
                        (
                            RunStatus.DEAD_LETTER.value,
                            now,
                            "stale running run exceeded retry budget",
                            next_attempt,
                            run_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = ?, updated_at = ?, error = ?,
                            attempt_count = ?, next_attempt_at = ?
                        WHERE run_id = ?
                        """,
                        (
                            RunStatus.QUEUED.value,
                            now,
                            "reclaimed stale running run",
                            next_attempt,
                            now,
                            run_id,
                        ),
                    )
                reclaimed += 1
            if reclaimed:
                conn.commit()
        return reclaimed

    def claim_next_queued(self) -> RunRecord | None:
        """Atomically move one queued run to running (external worker / Job mode)."""
        now = _now_iso()
        with self._lock, self._connect() as conn:
            if conn.dialect == "postgresql":
                cur = conn.execute(
                    """
                    UPDATE runs
                    SET status = ?, updated_at = ?, next_attempt_at = NULL
                    WHERE run_id = (
                        SELECT run_id FROM runs
                        WHERE status = ?
                          AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                        ORDER BY created_at ASC
                        FOR UPDATE SKIP LOCKED
                        LIMIT 1
                    )
                    RETURNING run_id
                    """,
                    (RunStatus.RUNNING.value, now, RunStatus.QUEUED.value, now),
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
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (RunStatus.QUEUED.value, now),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            run_id = row["run_id"] if isinstance(row, dict) else row[0]
            conn.execute(
                """
                UPDATE runs
                SET status = ?, updated_at = ?, next_attempt_at = NULL
                WHERE run_id = ?
                """,
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
    attempt_raw = _row_field(row, "attempt_count", 0)
    next_attempt = _row_field(row, "next_attempt_at")
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
        attempt_count=int(attempt_raw or 0),
        next_attempt_at=str(next_attempt) if next_attempt else None,
    )


def _row_field(row: Any, key: str, default: Any = None) -> Any:
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default
