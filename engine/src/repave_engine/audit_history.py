"""Read and query generation events from the audit sink (JSONL or SQL)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 8
_HOME_ACTIVITY_LIMIT = 5
HOME_ACTIVITY_LIMIT = _HOME_ACTIVITY_LIMIT
_INITIAL_ARTIFACT_VERSION = "0.1.0"
_MAX_LINE_BYTES = 256_000
_MAX_SCAN_ROWS = 10_000
_GENERATION_EVENTS = frozenset({"generation", "bundle_generation", "import"})


def initial_artifact_version_for_audit() -> str:
    """Default semver for a newly generated artifact (matches blueprint template pins)."""
    return _INITIAL_ARTIFACT_VERSION


def _github_repo_slug(repository_url: str) -> str:
    normalized = repository_url.strip().rstrip("/")
    if not normalized:
        return ""
    if "github.com/" in normalized:
        tail = normalized.split("github.com/", 1)[1]
        parts = [part for part in tail.split("/") if part]
        if len(parts) >= 2:
            return parts[1]
        if parts:
            return parts[0]
    return normalized.rsplit("/", 1)[-1]


@dataclass(frozen=True)
class AuditHistoryEntry:
    timestamp: str
    event: str
    blueprint_name: str
    blueprint_version: str
    module_name: str
    dry_run: bool
    gates_outcome: str
    acting_user: str
    repository_url: str | None
    extra: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> AuditHistoryEntry | None:
        event = str(payload.get("event", "")).strip()
        if event not in _GENERATION_EVENTS:
            return None
        name = str(payload.get("blueprint_name", "")).strip()
        if not name:
            return None
        extra_raw = payload.get("extra")
        extra = dict(extra_raw) if isinstance(extra_raw, dict) else {}
        return cls(
            timestamp=str(payload.get("timestamp", "")),
            event=event,
            blueprint_name=name,
            blueprint_version=str(payload.get("blueprint_version", "")),
            module_name=str(payload.get("module_name", "")),
            dry_run=bool(payload.get("dry_run")),
            gates_outcome=str(payload.get("gates_outcome", "")),
            acting_user=str(payload.get("acting_user", "unknown")),
            repository_url=(
                str(payload["repository_url"]).strip() if payload.get("repository_url") else None
            ),
            extra=extra,
        )

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event": self.event,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "module_name": self.module_name,
            "dry_run": self.dry_run,
            "gates_outcome": self.gates_outcome,
            "acting_user": self.acting_user,
            "repository_url": self.repository_url,
            "extra": self.extra,
        }

    def activity_artifact_name(self) -> str:
        """Library-style primary label: produced artifact, not the golden-path blueprint slug."""
        module = self.module_name.strip()
        if module and module != self.blueprint_name:
            return module
        slug = _github_repo_slug(self.repository_url or "")
        if slug:
            return slug
        return module or self.blueprint_name

    def activity_version_label(self) -> str | None:
        """Released or initial artifact semver (not the blueprint pin)."""
        raw = self.extra.get("artifact_version")
        if not isinstance(raw, str):
            return None
        version = raw.strip().lstrip("v")
        if not version:
            return None
        return f"v{version}"

    def activity_blueprint_pin(self) -> str:
        pin = self.blueprint_version.strip()
        if pin:
            return f"{self.blueprint_name}@{pin}"
        return self.blueprint_name

    def activity_href(self) -> str:
        if self.repository_url:
            from repave_engine.entity_catalog import entity_id_for_repo_url

            return f"/services/{entity_id_for_repo_url(self.repository_url)}"
        return f"/blueprints/{self.blueprint_name}"


@dataclass(frozen=True)
class AuditQueryFilters:
    blueprint_name: str | None = None
    module_name: str | None = None
    repository_url: str | None = None
    acting_user: str | None = None
    gates_outcome: str | None = None
    since: str | None = None
    until: str | None = None
    limit: int = 50
    offset: int = 0


def audit_filters_from_mapping(raw: dict[str, str]) -> AuditQueryFilters:
    def _opt(key: str) -> str | None:
        value = raw.get(key, "").strip()
        return value or None

    limit_raw = raw.get("limit", "50").strip() or "50"
    offset_raw = raw.get("offset", "0").strip() or "0"
    try:
        limit = int(limit_raw)
    except ValueError:
        limit = 50
    try:
        offset = int(offset_raw)
    except ValueError:
        offset = 0
    return AuditQueryFilters(
        blueprint_name=_opt("blueprint") or _opt("blueprint_name"),
        module_name=_opt("module_name") or _opt("repo"),
        repository_url=_opt("repository_url"),
        acting_user=_opt("acting_user") or _opt("user"),
        gates_outcome=_opt("gates_outcome") or _opt("outcome"),
        since=_opt("since"),
        until=_opt("until"),
        limit=limit,
        offset=offset,
    )


@dataclass(frozen=True)
class AuditQueryResult:
    entries: tuple[AuditHistoryEntry, ...]
    total: int
    limit: int
    offset: int


def _entry_matches(entry: AuditHistoryEntry, filters: AuditQueryFilters) -> bool:
    if filters.blueprint_name and entry.blueprint_name != filters.blueprint_name.strip():
        return False
    if filters.module_name:
        needle = filters.module_name.strip().lower()
        if needle not in entry.module_name.lower():
            return False
    if filters.repository_url:
        needle = filters.repository_url.strip().lower()
        hay = (entry.repository_url or "").lower()
        if needle not in hay and needle not in entry.module_name.lower():
            return False
    if filters.acting_user and entry.acting_user != filters.acting_user.strip():
        return False
    if filters.gates_outcome and entry.gates_outcome != filters.gates_outcome.strip():
        return False
    if filters.since and entry.timestamp < filters.since.strip():
        return False
    return not (filters.until and entry.timestamp > filters.until.strip())


def _paginate(
    matched: list[AuditHistoryEntry],
    *,
    limit: int,
    offset: int,
) -> tuple[AuditHistoryEntry, ...]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)
    return tuple(matched[safe_offset : safe_offset + safe_limit])


def _collect_payloads_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        size = path.stat().st_size
    except OSError as exc:
        logger.warning("Audit history unreadable (%s): %s", path, exc)
        return []
    if size == 0:
        return []

    lines: list[str] = []
    try:
        with path.open("rb") as handle:
            if size > _MAX_LINE_BYTES * _MAX_SCAN_ROWS:
                handle.seek(max(0, size - _MAX_LINE_BYTES * _MAX_SCAN_ROWS))
                handle.readline()
            for raw in handle:
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
    except OSError as exc:
        logger.warning("Audit history read failed (%s): %s", path, exc)
        return []

    payloads: list[dict[str, Any]] = []
    for line in lines:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _entries_from_payloads(payloads: list[dict[str, Any]]) -> list[AuditHistoryEntry]:
    entries: list[AuditHistoryEntry] = []
    for payload in reversed(payloads):
        entry = AuditHistoryEntry.from_dict(payload)
        if entry is not None:
            entries.append(entry)
        if len(entries) >= _MAX_SCAN_ROWS:
            break
    return entries


def query_audit_entries(
    path: Path,
    filters: AuditQueryFilters,
    *,
    repo_root: Path | None = None,
) -> AuditQueryResult:
    """Filter audit records newest-first with pagination."""
    safe_limit = max(1, min(filters.limit, 500))
    safe_offset = max(0, filters.offset)
    normalized = AuditQueryFilters(
        blueprint_name=filters.blueprint_name,
        module_name=filters.module_name,
        repository_url=filters.repository_url,
        acting_user=filters.acting_user,
        gates_outcome=filters.gates_outcome,
        since=filters.since,
        until=filters.until,
        limit=safe_limit,
        offset=safe_offset,
    )

    entries = _load_entries_newest_first(path, repo_root=repo_root)
    matched = [entry for entry in entries if _entry_matches(entry, normalized)]
    page = _paginate(matched, limit=safe_limit, offset=safe_offset)
    return AuditQueryResult(
        entries=page,
        total=len(matched),
        limit=safe_limit,
        offset=safe_offset,
    )


def _load_entries_newest_first(path: Path, *, repo_root: Path | None) -> list[AuditHistoryEntry]:
    if repo_root is not None:
        from repave_engine.durability_store import load_durability_store_settings
        from repave_engine.sql_store import connect, scan_audit_events

        settings = load_durability_store_settings(repo_root)
        if settings is not None:
            try:
                with connect(settings.database) as conn:
                    payloads = scan_audit_events(conn, max_rows=_MAX_SCAN_ROWS)
            except OSError as exc:
                logger.warning("Audit SQL read failed: %s", exc)
            else:
                return _entries_from_payloads(payloads)

    return _entries_from_payloads(_collect_payloads_jsonl(path))


def read_recent_audit_entries(
    path: Path,
    *,
    limit: int = _DEFAULT_LIMIT,
    repo_root: Path | None = None,
) -> tuple[AuditHistoryEntry, ...]:
    """Return the most recent generation records, newest first."""
    if limit <= 0:
        return ()
    result = query_audit_entries(
        path,
        AuditQueryFilters(limit=limit, offset=0),
        repo_root=repo_root,
    )
    return result.entries
