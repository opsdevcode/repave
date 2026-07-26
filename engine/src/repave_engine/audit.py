"""Append-only JSONL audit log for generation events."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def append_audit_record(path: Path, record: AuditRecord) -> None:
    """Write one JSON line; never raises."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record.to_dict(), separators=(",", ":"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError as exc:
        logger.warning("Audit log write failed (%s): %s", path, exc)
