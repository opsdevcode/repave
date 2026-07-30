"""Append-only JSONL audit log for generation events."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.jsonl_lock import append_jsonl_line_best_effort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditRecord:
    event: str
    blueprint_name: str
    blueprint_version: str
    module_name: str
    dry_run: bool
    gates_outcome: str
    repository_url: str | None
    acting_user: str
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["timestamp"] = datetime.now(timezone.utc).isoformat()
        return payload


def acting_user_from_env() -> str:
    for key in ("REPAVE_ACTING_USER", "USER", "USERNAME"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return "unknown"


def append_audit_record(path: Path, record: AuditRecord, *, repo_root: Path | None = None) -> None:
    """Write one JSON line; never raises. Uses SQL store when Phase 2 durability is configured."""
    payload = record.to_dict()
    line = json.dumps(payload, separators=(",", ":"))
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import append_audit_event, connect, ensure_schema

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    ensure_schema(conn)
                    append_audit_event(conn, payload, created_at=str(payload["timestamp"]))
                    conn.commit()
            except OSError as exc:
                logger.error("audit SQL append failed: %s", exc)
            else:
                if settings.export_jsonl:
                    append_jsonl_line_best_effort(path, line, store="audit")
                return
    append_jsonl_line_best_effort(path, line, store="audit")
