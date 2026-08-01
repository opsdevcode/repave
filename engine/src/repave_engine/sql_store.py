"""Unified SQL durability store (Phase 2): runs, events, audit, fleet."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

Dialect = Literal["sqlite", "postgresql"]


def is_unique_constraint_error(exc: Exception) -> bool:
    """True for SQLite IntegrityError or psycopg UniqueViolation (when installed)."""
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    try:
        from psycopg.errors import UniqueViolation
    except ImportError:
        return False
    return isinstance(exc, UniqueViolation)


@dataclass(frozen=True)
class DatabaseConfig:
    dialect: Dialect
    """SQLite file path or PostgreSQL DSN for psycopg."""

    sqlite_path: Path | None = None
    postgres_dsn: str | None = None

    @property
    def runs_db_path(self) -> Path | None:
        return self.sqlite_path


def parse_database_url(raw: str, *, repo_root: Path) -> DatabaseConfig:
    value = raw.strip()
    if not value:
        raise ValueError("database_url must not be empty")
    if value.startswith("sqlite:"):
        parsed = urlparse(value)
        if parsed.path in ("", "/") and parsed.netloc:
            path = Path(unquote(parsed.netloc))
        else:
            path = Path(unquote(parsed.path.lstrip("/")))
        if not path.is_absolute():
            path = (repo_root / path).resolve()
        return DatabaseConfig(dialect="sqlite", sqlite_path=path)
    if re.match(r"^postgres(ql)?://", value, re.I):
        return DatabaseConfig(dialect="postgresql", postgres_dsn=value)
    raise ValueError(
        f"database_url must be sqlite:///path or postgresql://user:pass@host/db (got {raw!r})"
    )


def load_database_config(repo_root: Path) -> DatabaseConfig | None:
    env_url = os.environ.get("REPAVE_DATABASE_URL", "").strip()
    if env_url:
        return parse_database_url(env_url, repo_root=repo_root)

    from repave_engine.settings import _load_config_file

    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("durability")
    if not isinstance(block, dict):
        return None
    url_raw = block.get("database_url")
    if not url_raw:
        return None
    return parse_database_url(str(url_raw).strip(), repo_root=repo_root)


class SqlConnection:
    """Thin wrapper so RunStore can use SQLite or PostgreSQL with the same SQL shape."""

    def __init__(self, raw: sqlite3.Connection | Any) -> None:
        self._conn = raw
        self.dialect: Dialect = (
            "postgresql" if raw.__class__.__module__.startswith("psycopg") else "sqlite"
        )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        adapted = _adapt_sql(sql, self.dialect)
        return self._conn.execute(adapted, params)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqlConnection:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _adapt_sql(sql: str, dialect: Dialect) -> str:
    if dialect == "sqlite":
        return sql
    return sql.replace("?", "%s")


def connect(config: DatabaseConfig) -> SqlConnection:
    if config.dialect == "sqlite":
        if config.sqlite_path is None:
            raise ValueError("sqlite database config requires sqlite_path")
        config.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(config.sqlite_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return SqlConnection(conn)
    if config.postgres_dsn is None:
        raise ValueError("postgresql database config requires postgres_dsn")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL database_url requires psycopg; install repave-engine[postgres]"
        ) from exc
    raw = psycopg.connect(config.postgres_dsn, row_factory=dict_row)
    return SqlConnection(raw)


def ensure_schema(conn: SqlConnection) -> None:
    if conn.dialect == "sqlite":
        _ensure_schema_sqlite(conn)
    else:
        _ensure_schema_postgres(conn)
    _migrate_runs_columns(conn)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_runs_next_attempt ON runs(status, next_attempt_at)"
    )
    conn.commit()


def _is_duplicate_column_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "duplicate column" in message or "already exists" in message


def _migrate_runs_columns(conn: SqlConnection) -> None:
    """Add retry/reclaim columns to existing run stores."""
    for name, decl in (
        ("attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ("next_attempt_at", "TEXT"),
    ):
        try:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {decl}")
        except Exception as exc:
            if not _is_duplicate_column_error(exc):
                raise


def _ensure_schema_sqlite(conn: SqlConnection) -> None:
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
            error TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fleet_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publish_receipts (
            publish_key TEXT PRIMARY KEY,
            pr_message TEXT NOT NULL,
            repository_web_url TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            run_id TEXT,
            client_request_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publish_receipts_client_request "
        "ON publish_receipts(client_request_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")


def _ensure_schema_postgres(conn: SqlConnection) -> None:
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
            error TEXT,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            next_attempt_at TEXT
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status)")
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
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id BIGSERIAL PRIMARY KEY,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_events_created ON audit_events(created_at)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fleet_events (
            id BIGSERIAL PRIMARY KEY,
            record_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publish_receipts (
            publish_key TEXT PRIMARY KEY,
            pr_message TEXT NOT NULL,
            repository_web_url TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            run_id TEXT,
            client_request_id TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publish_receipts_client_request "
        "ON publish_receipts(client_request_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            data_json TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)")


def save_session(
    conn: SqlConnection,
    session_id: str,
    data: dict[str, Any],
    *,
    expires_at: str,
    updated_at: str,
) -> None:
    line = json.dumps(data, separators=(",", ":"))
    conn.execute(
        """
        INSERT INTO sessions (session_id, data_json, expires_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            data_json=excluded.data_json,
            expires_at=excluded.expires_at,
            updated_at=excluded.updated_at
        """,
        (session_id, line, expires_at, updated_at),
    )


def load_session(conn: SqlConnection, session_id: str, *, now: str) -> dict[str, Any] | None:
    cur = conn.execute(
        "SELECT data_json, expires_at FROM sessions WHERE session_id = ?",
        (session_id,),
    )
    rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
    if not rows:
        return None
    row = rows[0]
    expires_at = row["expires_at"] if isinstance(row, dict) else row[1]
    if expires_at < now:
        delete_session(conn, session_id)
        return None
    raw = row["data_json"] if isinstance(row, dict) else row[0]
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        delete_session(conn, session_id)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def delete_session(conn: SqlConnection, session_id: str) -> None:
    conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def append_audit_event(conn: SqlConnection, record: dict[str, Any], *, created_at: str) -> None:
    line = json.dumps(record, separators=(",", ":"))
    conn.execute(
        "INSERT INTO audit_events (record_json, created_at) VALUES (?, ?)",
        (line, created_at),
    )


def read_audit_events(conn: SqlConnection, *, limit: int) -> list[dict[str, Any]]:
    return scan_audit_events(conn, max_rows=limit * 3)


def scan_audit_events(conn: SqlConnection, *, max_rows: int) -> list[dict[str, Any]]:
    if max_rows <= 0:
        return []
    cur = conn.execute(
        """
        SELECT record_json FROM audit_events
        ORDER BY id DESC
        LIMIT ?
        """,
        (max_rows,),
    )
    rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = row["record_json"] if isinstance(row, dict) else row[0]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def append_fleet_event_line(
    conn: SqlConnection, payload: dict[str, Any], *, created_at: str
) -> None:
    line = json.dumps(payload, separators=(",", ":"))
    conn.execute(
        "INSERT INTO fleet_events (record_json, created_at) VALUES (?, ?)",
        (line, created_at),
    )


def read_fleet_event_lines(conn: SqlConnection) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT record_json FROM fleet_events ORDER BY id ASC",
    )
    rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = row["record_json"] if isinstance(row, dict) else row[0]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


_store_lock = threading.Lock()
_store_by_key: dict[str, DatabaseConfig] = {}


def register_database_config(config: DatabaseConfig) -> None:
    key = str(config.sqlite_path or config.postgres_dsn)
    with _store_lock:
        _store_by_key[key] = config


def database_config_for_runs_db(db_path: Path) -> DatabaseConfig:
    return DatabaseConfig(dialect="sqlite", sqlite_path=db_path)
