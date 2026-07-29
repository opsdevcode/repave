"""Append-only run event log for portal SSE (async generation progress)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.sql_store import (
    DatabaseConfig,
    SqlConnection,
    connect,
    database_config_for_runs_db,
    ensure_schema,
)

MAX_EVENTS_PER_RUN = 500

TERMINAL_EVENT_KINDS = frozenset({"run_finished", "run_failed"})


@dataclass(frozen=True)
class RunEvent:
    seq: int
    kind: str
    payload: dict[str, Any]

    def to_sse_data(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.payload}


class RunEventStore:
    """Thread-safe persisted event log with in-process wait/notify for SSE."""

    def __init__(self, db: Path | DatabaseConfig) -> None:
        self._config = db if isinstance(db, DatabaseConfig) else database_config_for_runs_db(db)
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        with self._lock, connect(self._config) as conn:
            ensure_schema(conn)

    def _connect(self) -> SqlConnection:
        return connect(self._config)

    def append(self, run_id: str, kind: str, payload: dict[str, Any] | None = None) -> RunEvent:
        body = payload if payload is not None else {}
        with self._cond:
            with self._connect() as conn:
                cur = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS mx FROM run_events WHERE run_id = ?",
                    (run_id,),
                )
                row = cur.fetchone()
                next_seq = int(row["mx"] if isinstance(row, dict) else row[0]) + 1 if row else 1
                cur = conn.execute(
                    "SELECT COUNT(*) AS c FROM run_events WHERE run_id = ?",
                    (run_id,),
                )
                count_row = cur.fetchone()
                count = int(count_row["c"] if isinstance(count_row, dict) else count_row[0])
                if count >= MAX_EVENTS_PER_RUN:
                    raise RuntimeError(f"run event log full for {run_id}")
                conn.execute(
                    """
                    INSERT INTO run_events (run_id, seq, kind, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (run_id, next_seq, kind, json.dumps(body, separators=(",", ":"))),
                )
                conn.commit()
            event = RunEvent(seq=next_seq, kind=kind, payload=body)
            self._cond.notify_all()
            return event

    def list_from(self, run_id: str, *, after_seq: int = 0) -> list[RunEvent]:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                SELECT seq, kind, payload_json FROM run_events
                WHERE run_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (run_id, after_seq),
            )
            rows = cur.fetchall()
        events: list[RunEvent] = []
        for row in rows:
            seq = int(row["seq"] if isinstance(row, dict) else row[0])
            kind = str(row["kind"] if isinstance(row, dict) else row[1])
            raw = row["payload_json"] if isinstance(row, dict) else row[2]
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                payload = {}
            events.append(RunEvent(seq=seq, kind=kind, payload=payload))
        return events

    def wait_for_events(
        self,
        run_id: str,
        *,
        after_seq: int,
        timeout_seconds: float,
    ) -> list[RunEvent]:
        with self._cond:
            events = self.list_from(run_id, after_seq=after_seq)
            if events:
                return events
            self._cond.wait(timeout=timeout_seconds)
            return self.list_from(run_id, after_seq=after_seq)


def build_run_event_store(db: Path | DatabaseConfig) -> RunEventStore:
    return RunEventStore(db)
