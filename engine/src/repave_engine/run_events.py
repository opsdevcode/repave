"""Append-only run event log for portal SSE (async generation progress)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
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
                CREATE TABLE IF NOT EXISTS run_events (
                    run_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (run_id, seq)
                )
                """
            )
            conn.commit()

    def append(self, run_id: str, kind: str, payload: dict[str, Any] | None = None) -> RunEvent:
        body = payload if payload is not None else {}
        with self._cond:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS mx FROM run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                next_seq = int(row["mx"]) + 1 if row else 1
                count_row = conn.execute(
                    "SELECT COUNT(*) AS c FROM run_events WHERE run_id = ?",
                    (run_id,),
                ).fetchone()
                if count_row and int(count_row["c"]) >= MAX_EVENTS_PER_RUN:
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
            rows = conn.execute(
                """
                SELECT seq, kind, payload_json FROM run_events
                WHERE run_id = ? AND seq > ?
                ORDER BY seq ASC
                """,
                (run_id, after_seq),
            ).fetchall()
        events: list[RunEvent] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            if not isinstance(payload, dict):
                payload = {}
            events.append(RunEvent(seq=int(row["seq"]), kind=str(row["kind"]), payload=payload))
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


def build_run_event_store(db_path: Path) -> RunEventStore:
    return RunEventStore(db_path)
