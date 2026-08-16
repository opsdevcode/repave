"""Component record model for vended GitOps managed resources (ADR 013)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from repave_engine.environment_record import parse_iso_timestamp


def entity_id_for_component(*, kind: str, name: str) -> str:
    return f"cmp-{kind.strip()}-{name.strip()}"


@dataclass(frozen=True)
class ComponentRecord:
    """A governed managed component vended into GitOps."""

    name: str
    kind: str
    entity_id: str
    cloud_provider: str
    environment_tier: str
    owner: str
    blueprint_name: str
    blueprint_version: str
    gitops_repo: str
    gitops_path: str
    git_branch: str
    pull_request_url: str
    pull_request_number: int
    gates_outcome: str
    run_id: str
    vended_by: str
    vended_at: str
    status: str
    expires_at: str = ""

    def to_event(self, event: str) -> dict[str, Any]:
        return {
            "event": event,
            "name": self.name,
            "kind": self.kind,
            "entity_id": self.entity_id,
            "cloud_provider": self.cloud_provider,
            "environment_tier": self.environment_tier,
            "owner": self.owner,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "pull_request_url": self.pull_request_url,
            "pull_request_number": self.pull_request_number,
            "gates_outcome": self.gates_outcome,
            "run_id": self.run_id,
            "vended_by": self.vended_by,
            "timestamp": self.vended_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "entity_id": self.entity_id,
            "cloud_provider": self.cloud_provider,
            "environment_tier": self.environment_tier,
            "owner": self.owner,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "pull_request_url": self.pull_request_url,
            "pull_request_number": self.pull_request_number,
            "gates_outcome": self.gates_outcome,
            "run_id": self.run_id,
            "vended_by": self.vended_by,
            "vended_at": self.vended_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }

    @classmethod
    def from_event(cls, payload: dict[str, Any]) -> ComponentRecord | None:
        name = str(payload.get("name", "")).strip()
        kind = str(payload.get("kind", "")).strip()
        entity_id = str(payload.get("entity_id", "")).strip()
        if not name or not kind or not entity_id:
            return None
        return cls(
            name=name,
            kind=kind,
            entity_id=entity_id,
            cloud_provider=str(payload.get("cloud_provider", "")).strip(),
            environment_tier=str(payload.get("environment_tier", "")).strip(),
            owner=str(payload.get("owner", "")).strip(),
            blueprint_name=str(payload.get("blueprint_name", "")).strip(),
            blueprint_version=str(payload.get("blueprint_version", "")).strip(),
            gitops_repo=str(payload.get("gitops_repo", "")).strip(),
            gitops_path=str(payload.get("gitops_path", "")).strip(),
            git_branch=str(payload.get("git_branch", "")).strip(),
            pull_request_url=str(payload.get("pull_request_url", "")).strip(),
            pull_request_number=int(payload.get("pull_request_number", 0) or 0),
            gates_outcome=str(payload.get("gates_outcome", "")).strip(),
            run_id=str(payload.get("run_id", "")).strip(),
            vended_by=str(payload.get("vended_by", "")).strip(),
            vended_at=str(payload.get("timestamp", payload.get("vended_at", ""))).strip(),
            status=str(payload.get("status", "active")).strip() or "active",
            expires_at=str(payload.get("expires_at", "")).strip(),
        )


def resolve_component_ttl_hours(
    kind: str,
    *,
    default_ttl_hours: int,
    ttl_hours_by_kind: tuple[tuple[str, int], ...],
) -> int | None:
    needle = kind.strip().lower()
    for kind_id, hours in ttl_hours_by_kind:
        if kind_id.strip().lower() == needle and hours > 0:
            return hours
    if default_ttl_hours > 0:
        return default_ttl_hours
    return None


def is_component_expired(
    record: ComponentRecord,
    *,
    now: datetime | None = None,
) -> bool:
    expires = parse_iso_timestamp(record.expires_at)
    if expires is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current >= expires


def is_reclaim_eligible_kind(kind: str, reclaim_kinds: frozenset[str]) -> bool:
    if not reclaim_kinds:
        return False
    needle = kind.strip().lower()
    return needle in {item.strip().lower() for item in reclaim_kinds if item.strip()}


def resolve_decommission_review_kinds(
    *,
    auto_reclaim_kinds: tuple[str, ...],
    configured_review_kinds: tuple[str, ...],
    observed_kinds: frozenset[str],
) -> frozenset[str]:
    auto = frozenset(item.strip().lower() for item in auto_reclaim_kinds if item.strip())
    if configured_review_kinds:
        return frozenset(
            item.strip().lower()
            for item in configured_review_kinds
            if item.strip() and item.strip().lower() not in auto
        )
    return frozenset(
        item.strip().lower() for item in observed_kinds if item.strip() and item not in auto
    )


def has_open_decommission_review(record: ComponentRecord) -> bool:
    return record.status.strip().lower() == "expired" and record.pull_request_number > 0
