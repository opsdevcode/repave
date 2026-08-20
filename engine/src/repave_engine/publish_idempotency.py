"""Publish idempotency for retried async runs (target repo + content hash)."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.gates import is_gate_artifact_path
from repave_engine.sql_store import (
    DatabaseConfig,
    SqlConnection,
    connect,
    database_config_for_runs_db,
    ensure_schema,
    is_unique_constraint_error,
)
from repave_engine.target_repo import ModuleRepository


@dataclass(frozen=True)
class PublishReceipt:
    publish_key: str
    pr_message: str
    repository_web_url: str
    content_hash: str
    run_id: str | None
    client_request_id: str | None
    created_at: str


@dataclass(frozen=True)
class PublishIdempotencyContext:
    store: PublishIdempotencyStore | None
    run_id: str | None = None
    client_request_id: str | None = None


def build_publish_key(repository: ModuleRepository, content_hash: str) -> str:
    return f"github:{repository.owner}/{repository.name}:{content_hash}"


def compute_publish_content_hash(staging_dir: Path, *, artifact_type: str) -> str:
    hasher = hashlib.sha256()
    for path in _iter_publish_files(staging_dir, artifact_type=artifact_type):
        rel = path.relative_to(staging_dir).as_posix()
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def publish_message_succeeded(pr_message: str) -> bool:
    lowered = pr_message.lower()
    if "gates failed" in lowered:
        return False
    if "github publish failed" in lowered:
        return False
    return "github repository provisioning failed" not in lowered


def _iter_publish_files(staging_dir: Path, *, artifact_type: str) -> list[Path]:
    if not staging_dir.is_dir():
        return []
    paths: list[Path] = []
    for item in staging_dir.rglob("*"):
        if not item.is_file():
            continue
        rel = item.relative_to(staging_dir)
        if rel.parts and rel.parts[0] == ".repave":
            if rel.name != "policy-selection.json":
                continue
        elif is_gate_artifact_path(item.name, artifact_type=artifact_type):
            continue
        paths.append(item)
    return sorted(paths, key=lambda path: path.relative_to(staging_dir).as_posix())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PublishIdempotencyStore:
    """Durable publish receipts keyed by target repository plus content hash."""

    def __init__(self, db: Path | DatabaseConfig) -> None:
        self._config = db if isinstance(db, DatabaseConfig) else database_config_for_runs_db(db)
        self._lock = threading.RLock()
        with self._lock, connect(self._config) as conn:
            ensure_schema(conn)

    def _connect(self) -> SqlConnection:
        return connect(self._config)

    def get(self, publish_key: str) -> PublishReceipt | None:
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                """
                SELECT publish_key, pr_message, repository_web_url, content_hash,
                       run_id, client_request_id, created_at
                FROM publish_receipts
                WHERE publish_key = ?
                """,
                (publish_key,),
            )
            row = cur.fetchone()
        return _row_to_receipt(row) if row else None

    def record(
        self,
        *,
        publish_key: str,
        pr_message: str,
        repository_web_url: str,
        content_hash: str,
        run_id: str | None = None,
        client_request_id: str | None = None,
    ) -> PublishReceipt:
        now = _now_iso()
        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO publish_receipts (
                        publish_key, pr_message, repository_web_url, content_hash,
                        run_id, client_request_id, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        publish_key,
                        pr_message,
                        repository_web_url,
                        content_hash,
                        run_id,
                        client_request_id,
                        now,
                    ),
                )
                conn.commit()
            except Exception as exc:
                conn.rollback()
                if not is_unique_constraint_error(exc):
                    raise
        existing = self.get(publish_key)
        if existing is None:
            raise RuntimeError(
                f"publish receipt missing after insert for key {publish_key!r}; "
                "retry the publish or inspect the runs database publish_receipts table"
            )
        return existing


def _row_to_receipt(row: Any) -> PublishReceipt:
    if isinstance(row, dict):
        publish_key = row["publish_key"]
        pr_message = row["pr_message"]
        repository_web_url = row["repository_web_url"]
        content_hash = row["content_hash"]
        run_id = row["run_id"]
        client_request_id = row["client_request_id"]
        created_at = row["created_at"]
    else:
        publish_key = row[0]
        pr_message = row[1]
        repository_web_url = row[2]
        content_hash = row[3]
        run_id = row[4]
        client_request_id = row[5]
        created_at = row[6]
    return PublishReceipt(
        publish_key=str(publish_key),
        pr_message=str(pr_message),
        repository_web_url=str(repository_web_url),
        content_hash=str(content_hash),
        run_id=str(run_id) if run_id else None,
        client_request_id=str(client_request_id) if client_request_id else None,
        created_at=str(created_at),
    )
