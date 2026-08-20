"""Read-only assistant tools — fleet, pin drift, and gate history.

Same viewer/generator/admin bar as GET /api/v2/fleet and /audit. No register,
unregister, or confirm-drift from this path.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from repave_engine.assistant_corpus import tokenize_intent
from repave_engine.auth import ROLE_ADMIN, ROLE_GENERATOR, ROLE_VIEWER
from repave_engine.blueprint import Blueprint
from repave_engine.fleet import FleetEntry

_VIEW_ROLES = frozenset({ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN})
_MAX_HITS = 5
_AUDIT_SCAN = _MAX_HITS * 20
_FLEET_HINTS = frozenset({"fleet", "registry"})
_DRIFT_HINTS = frozenset({"drift", "behind", "pins"})
_AUDIT_HINTS = frozenset({"audit", "gates"})

TOOL_FLEET = "fleet.reads"
TOOL_DRIFT = "fleet.drift"
TOOL_AUDIT = "audit.history"


@dataclass(frozen=True)
class AssistantReadHit:
    tool_id: str
    source: str
    title: str
    excerpt: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "tool_id": self.tool_id,
            "source": self.source,
            "title": self.title,
            "excerpt": self.excerpt,
        }


def reads_allowed(*, role: str | None, auth_enabled: bool) -> bool:
    """True when the caller may see the same fleet/audit the portal already shows."""
    if not auth_enabled:
        return True
    return (role or "") in _VIEW_ROLES


def collect_assistant_reads(
    repo_root: Path,
    *,
    intent: str,
    blueprints: Sequence[Blueprint],
    role: str | None,
    auth_enabled: bool,
) -> tuple[tuple[AssistantReadHit, ...], tuple[str, ...]]:
    """Return hits plus tool ids that actually ran. Denied callers get empty tuples."""
    if not reads_allowed(role=role, auth_enabled=auth_enabled):
        return (), ()
    tokens = tokenize_intent(intent)
    hits: list[AssistantReadHit] = []
    tools: list[str] = []
    want_fleet = bool(tokens & _FLEET_HINTS)
    want_drift = bool(tokens & _DRIFT_HINTS)
    entries: tuple[FleetEntry, ...] | None = None
    if want_fleet or want_drift:
        entries = _load_fleet_entries(repo_root)
    if want_fleet:
        tools.append(TOOL_FLEET)
        hits.extend(_fleet_hits(entries or (), tokens=tokens))
    if want_drift:
        tools.append(TOOL_DRIFT)
        hits.extend(_drift_hits(entries or (), blueprints=blueprints))
    if tokens & _AUDIT_HINTS:
        tools.append(TOOL_AUDIT)
        hits.extend(_audit_hits(repo_root, blueprints=blueprints))
    return tuple(hits[: _MAX_HITS * 3]), tuple(tools)


def _load_fleet_entries(repo_root: Path) -> tuple[FleetEntry, ...]:
    from repave_engine.fleet import read_fleet
    from repave_engine.settings import load_fleet_config

    try:
        config = load_fleet_config(repo_root)
    except ValueError:
        return ()
    if config is None or not config.enabled:
        return ()
    return read_fleet(config.file, repo_root=repo_root)


def _fleet_hits(
    entries: Sequence[FleetEntry],
    *,
    tokens: frozenset[str],
) -> tuple[AssistantReadHit, ...]:
    ranked = sorted(entries, key=lambda entry: (-_fleet_score(entry, tokens), entry.repo_url))
    hits: list[AssistantReadHit] = []
    for entry in ranked[:_MAX_HITS]:
        hits.append(
            AssistantReadHit(
                tool_id=TOOL_FLEET,
                source=f"fleet:{entry.repo_url}",
                title=entry.blueprint_name,
                excerpt=(
                    f"{entry.repo_url} pin {entry.blueprint_version} owner={entry.owner or 'unset'}"
                ),
            )
        )
    return tuple(hits)


def _fleet_score(entry: FleetEntry, tokens: frozenset[str]) -> int:
    hay = f"{entry.repo_url} {entry.blueprint_name} {entry.owner} {entry.blueprint_version}".lower()
    return sum(1 for token in tokens if token in hay)


def _drift_hits(
    entries: Sequence[FleetEntry],
    *,
    blueprints: Sequence[Blueprint],
) -> tuple[AssistantReadHit, ...]:
    from repave_engine.fleet_drift import estimate_fleet_drift

    summaries = estimate_fleet_drift(tuple(entries), list(blueprints))
    hits: list[AssistantReadHit] = []
    for summary in summaries:
        if summary.behind_count == 0:
            continue
        sample = summary.behind_repos[0].repo_url if summary.behind_repos else ""
        hits.append(
            AssistantReadHit(
                tool_id=TOOL_DRIFT,
                source=f"fleet-drift:{summary.blueprint_name}",
                title=summary.blueprint_name,
                excerpt=(
                    f"{summary.behind_count} of {summary.governed_count} behind "
                    f"catalog {summary.catalog_version}" + (f"; e.g. {sample}" if sample else "")
                ),
            )
        )
        if len(hits) >= _MAX_HITS:
            break
    return tuple(hits)


def _audit_hits(
    repo_root: Path,
    *,
    blueprints: Sequence[Blueprint],
) -> tuple[AssistantReadHit, ...]:
    from repave_engine.audit_history import AuditQueryFilters, query_audit_entries
    from repave_engine.settings import load_audit_config

    try:
        audit = load_audit_config(repo_root)
    except ValueError:
        return ()
    if audit is None or not audit.enabled:
        return ()
    names = {item.name for item in blueprints}
    result = query_audit_entries(
        audit.file,
        AuditQueryFilters(limit=_AUDIT_SCAN),
        repo_root=repo_root,
    )
    hits: list[AssistantReadHit] = []
    for entry in result.entries:
        if names and entry.blueprint_name not in names:
            continue
        hits.append(
            AssistantReadHit(
                tool_id=TOOL_AUDIT,
                source=f"audit:{entry.blueprint_name}",
                title=entry.blueprint_name,
                excerpt=(
                    f"{entry.gates_outcome or 'unknown'} "
                    f"{entry.module_name or entry.blueprint_name} "
                    f"{entry.timestamp}".strip()
                ),
            )
        )
        if len(hits) >= _MAX_HITS:
            break
    return tuple(hits)
