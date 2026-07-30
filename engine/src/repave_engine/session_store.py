"""Server-side OIDC session persistence in the unified SQL durability store."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from repave_engine.sql_store import (
    DatabaseConfig,
    connect,
    delete_session,
    ensure_schema,
    load_database_config,
    load_session,
    save_session,
)

DEFAULT_SESSION_MAX_AGE_SECONDS = 14 * 24 * 60 * 60


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).replace(microsecond=0).isoformat()


class SessionStore:
    """Persist auth session payloads when durability.database_url is configured."""

    def __init__(
        self,
        database: DatabaseConfig,
        *,
        max_age_seconds: int = DEFAULT_SESSION_MAX_AGE_SECONDS,
    ) -> None:
        self._database = database
        self._max_age_seconds = max_age_seconds

    @property
    def database(self) -> DatabaseConfig:
        return self._database

    def create_id(self) -> str:
        return secrets.token_urlsafe(32)

    def load(self, session_id: str) -> dict[str, Any] | None:
        now = _utc_now_iso()
        with connect(self._database) as conn:
            ensure_schema(conn)
            data = load_session(conn, session_id, now=now)
            if data is None:
                conn.commit()
            return data

    def save(self, session_id: str, data: dict[str, Any]) -> None:
        now = _utc_now_iso()
        expires_at = (
            (datetime.now(tz=timezone.utc) + timedelta(seconds=self._max_age_seconds))
            .replace(microsecond=0)
            .isoformat()
        )
        with connect(self._database) as conn:
            ensure_schema(conn)
            save_session(
                conn,
                session_id,
                data,
                expires_at=expires_at,
                updated_at=now,
            )
            conn.commit()

    def delete(self, session_id: str) -> None:
        with connect(self._database) as conn:
            ensure_schema(conn)
            delete_session(conn, session_id)
            conn.commit()

    def ping(self) -> bool:
        """Verify the sessions table is reachable (readiness probe)."""
        try:
            with connect(self._database) as conn:
                ensure_schema(conn)
                conn.execute("SELECT 1 FROM sessions LIMIT 1")
            return True
        except OSError:
            return False


def load_session_store(repo_root: Path) -> SessionStore | None:
    database = load_database_config(repo_root)
    if database is None:
        return None
    return SessionStore(database)
