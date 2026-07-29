"""Read recent generation events from the JSONL audit sink."""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 8
_MAX_LINE_BYTES = 256_000


@dataclass(frozen=True)
class AuditHistoryEntry:
    timestamp: str
    blueprint_name: str
    blueprint_version: str
    module_name: str
    dry_run: bool
    gates_outcome: str
    acting_user: str
    repository_url: str | None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuditHistoryEntry | None:
        if payload.get("event") != "generation":
            return None
        name = str(payload.get("blueprint_name", "")).strip()
        if not name:
            return None
        return cls(
            timestamp=str(payload.get("timestamp", "")),
            blueprint_name=name,
            blueprint_version=str(payload.get("blueprint_version", "")),
            module_name=str(payload.get("module_name", "")),
            dry_run=bool(payload.get("dry_run")),
            gates_outcome=str(payload.get("gates_outcome", "")),
            acting_user=str(payload.get("acting_user", "unknown")),
            repository_url=(
                str(payload["repository_url"]).strip() if payload.get("repository_url") else None
            ),
        )


def read_recent_audit_entries(
    path: Path,
    *,
    limit: int = _DEFAULT_LIMIT,
    repo_root: Path | None = None,
) -> tuple[AuditHistoryEntry, ...]:
    """Return the most recent generation records, newest first."""
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, read_audit_events

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = read_audit_events(conn, limit=limit)
            except OSError as exc:
                logger.warning("Audit SQL read failed: %s", exc)
            else:
                entries: list[AuditHistoryEntry] = []
                for payload in payloads:
                    entry = AuditHistoryEntry.from_dict(payload)
                    if entry is not None:
                        entries.append(entry)
                    if len(entries) >= limit:
                        break
                return tuple(entries)

    if limit <= 0 or not path.is_file():
        return ()
    try:
        size = path.stat().st_size
        if size == 0:
            return ()
    except OSError as exc:
        logger.warning("Audit history unreadable (%s): %s", path, exc)
        return ()

    lines: deque[str] = deque(maxlen=limit * 3)
    try:
        with path.open("rb") as handle:
            if size > _MAX_LINE_BYTES * limit:
                handle.seek(max(0, size - _MAX_LINE_BYTES * limit))
                handle.readline()
            for raw in handle:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
    except OSError as exc:
        logger.warning("Audit history read failed (%s): %s", path, exc)
        return ()

    file_entries: list[AuditHistoryEntry] = []
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        entry = AuditHistoryEntry.from_dict(payload)
        if entry is None:
            continue
        file_entries.append(entry)
        if len(file_entries) >= limit:
            break
    return tuple(file_entries)
