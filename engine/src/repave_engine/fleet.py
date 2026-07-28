"""Append-only JSONL registry of repositories repave manages.

The log records `register` and `unregister` events; current fleet state is the fold of
those events with last write winning per repo URL. Same shape as the audit sink so the
storage backend can move to a database later without changing callers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from repave_engine.jsonl_lock import append_jsonl_line

logger = logging.getLogger(__name__)

EVENT_REGISTER = "register"
EVENT_UNREGISTER = "unregister"

_MAX_FILE_BYTES = 8_000_000


class FleetError(ValueError):
    """Raised for invalid registry input."""


@dataclass(frozen=True)
class FleetEntry:
    """A repository under repave governance."""

    repo_url: str
    blueprint_name: str
    blueprint_version: str
    standard_source: str = ""
    standard_version: str = ""
    owner: str = ""
    registered_by: str = "unknown"
    registered_at: str = ""

    def to_event(self, event: str) -> dict[str, Any]:
        return {
            "event": event,
            "repo_url": self.repo_url,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "standard_source": self.standard_source,
            "standard_version": self.standard_version,
            "owner": self.owner,
            "registered_by": self.registered_by,
            "timestamp": self.registered_at or _now(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "standard_source": self.standard_source,
            "standard_version": self.standard_version,
            "owner": self.owner,
            "registered_by": self.registered_by,
            "registered_at": self.registered_at,
        }

    @classmethod
    def from_event(cls, payload: dict[str, Any]) -> FleetEntry | None:
        repo_url = str(payload.get("repo_url", "")).strip()
        blueprint = str(payload.get("blueprint_name", "")).strip()
        if not repo_url or not blueprint:
            return None
        return cls(
            repo_url=repo_url,
            blueprint_name=blueprint,
            blueprint_version=str(payload.get("blueprint_version", "")).strip(),
            standard_source=str(payload.get("standard_source", "")).strip(),
            standard_version=str(payload.get("standard_version", "")).strip(),
            owner=str(payload.get("owner", "")).strip(),
            registered_by=str(payload.get("registered_by", "unknown")).strip() or "unknown",
            registered_at=str(payload.get("timestamp", "")).strip(),
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_repo_url(raw: str) -> str:
    """Collapse the spellings of one repo so register/unregister agree.

    `https://github.com/acme/mod.git`, the same URL with a trailing slash, and the SSH
    form all identify one repository.
    """
    value = str(raw).strip()
    if not value:
        raise FleetError("repository URL is required")
    value = value.rstrip("/")
    if value.endswith(".git"):
        value = value[: -len(".git")]
    return value


def pins_from_repave_file(repo_path: Path) -> dict[str, str]:
    """Read blueprint and standard pins from a repo's repave.yaml provenance."""
    provenance_file = repo_path / "repave.yaml"
    if not provenance_file.is_file():
        raise FleetError(f"no repave.yaml under {repo_path}")
    try:
        data = yaml.safe_load(provenance_file.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FleetError(f"invalid repave.yaml in {repo_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FleetError(f"expected mapping in {provenance_file}")

    spec = data.get("spec")
    if not isinstance(spec, dict):
        raise FleetError(f"{provenance_file} has no spec block")
    blueprint_raw = spec.get("blueprint")
    blueprint: dict[str, Any] = blueprint_raw if isinstance(blueprint_raw, dict) else {}
    standard_raw = spec.get("standard")
    standard: dict[str, Any] = standard_raw if isinstance(standard_raw, dict) else {}

    name = str(blueprint.get("name", "")).strip()
    if not name:
        raise FleetError(f"{provenance_file} has no spec.blueprint.name")

    return {
        "blueprint_name": name,
        "blueprint_version": str(blueprint.get("version", "")).strip(),
        "standard_source": str(standard.get("source", "")).strip(),
        "standard_version": str(standard.get("version", "")).strip(),
    }


def append_fleet_event(path: Path, entry: FleetEntry, event: str) -> None:
    """Append one register/unregister event. Raises on write failure.

    Unlike the audit sink, registry writes are user-initiated commands, so a failure must
    surface rather than be logged and swallowed.
    """
    if event not in (EVENT_REGISTER, EVENT_UNREGISTER):
        raise FleetError(f"unknown fleet event {event!r}")
    payload = entry.to_event(event)
    try:
        append_jsonl_line(path, json.dumps(payload, separators=(",", ":")))
    except OSError as exc:
        raise FleetError(f"fleet registry write failed ({path}): {exc}") from exc


def read_fleet(path: Path) -> tuple[FleetEntry, ...]:
    """Return currently registered repos, sorted by URL. Never raises."""
    if not path.is_file():
        return ()
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            logger.warning("Fleet registry %s is unusually large; reading anyway", path)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        logger.warning("Fleet registry unreadable (%s): %s", path, exc)
        return ()

    current: dict[str, FleetEntry] = {}
    for line in lines:
        text = line.strip()
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        event = str(payload.get("event", "")).strip()
        repo_url = str(payload.get("repo_url", "")).strip()
        if not repo_url:
            continue
        if event == EVENT_UNREGISTER:
            current.pop(repo_url, None)
            continue
        if event != EVENT_REGISTER:
            continue
        entry = FleetEntry.from_event(payload)
        if entry is not None:
            current[repo_url] = entry

    return tuple(sorted(current.values(), key=lambda item: item.repo_url))


def register_repo(path: Path, entry: FleetEntry) -> FleetEntry:
    """Register (or re-register with new pins) a repository."""
    normalized = replace(
        entry,
        repo_url=normalize_repo_url(entry.repo_url),
        registered_at=entry.registered_at or _now(),
    )
    if not normalized.blueprint_name:
        raise FleetError("blueprint name is required to register a repository")
    append_fleet_event(path, normalized, EVENT_REGISTER)
    return normalized


def unregister_repo(path: Path, repo_url: str) -> bool:
    """Remove a repository. Returns False when it was not registered."""
    normalized = normalize_repo_url(repo_url)
    if not any(item.repo_url == normalized for item in read_fleet(path)):
        return False
    append_fleet_event(
        path,
        FleetEntry(repo_url=normalized, blueprint_name="-", blueprint_version=""),
        EVENT_UNREGISTER,
    )
    return True
