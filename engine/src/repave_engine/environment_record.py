"""Environment record model for vended GitOps stacks (ADR 003 Phase 3)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class EnvironmentRecord:
    """A governed environment vended into GitOps."""

    stack_name: str
    entity_id: str
    cloud_provider: str
    environment_tier: str
    owner: str
    env_class: str
    blueprint_name: str
    blueprint_version: str
    gitops_repo: str
    gitops_path: str
    git_branch: str
    pull_request_url: str
    pull_request_number: int
    gates_outcome: str
    source_entity_id: str
    run_id: str
    vended_by: str
    vended_at: str
    expires_at: str
    status: str

    def to_event(self, event: str) -> dict[str, Any]:
        return {
            "event": event,
            "stack_name": self.stack_name,
            "entity_id": self.entity_id,
            "cloud_provider": self.cloud_provider,
            "environment_tier": self.environment_tier,
            "owner": self.owner,
            "class": self.env_class,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "pull_request_url": self.pull_request_url,
            "pull_request_number": self.pull_request_number,
            "gates_outcome": self.gates_outcome,
            "source_entity_id": self.source_entity_id,
            "run_id": self.run_id,
            "vended_by": self.vended_by,
            "timestamp": self.vended_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "stack_name": self.stack_name,
            "entity_id": self.entity_id,
            "cloud_provider": self.cloud_provider,
            "environment_tier": self.environment_tier,
            "owner": self.owner,
            "class": self.env_class,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "pull_request_url": self.pull_request_url,
            "pull_request_number": self.pull_request_number,
            "gates_outcome": self.gates_outcome,
            "source_entity_id": self.source_entity_id,
            "run_id": self.run_id,
            "vended_by": self.vended_by,
            "vended_at": self.vended_at,
            "expires_at": self.expires_at,
            "status": self.status,
        }

    @classmethod
    def from_event(cls, payload: dict[str, Any]) -> EnvironmentRecord | None:
        stack_name = str(payload.get("stack_name", "")).strip()
        entity_id = str(payload.get("entity_id", "")).strip()
        if not stack_name or not entity_id:
            return None
        return cls(
            stack_name=stack_name,
            entity_id=entity_id,
            cloud_provider=str(payload.get("cloud_provider", "")).strip(),
            environment_tier=str(payload.get("environment_tier", "")).strip(),
            owner=str(payload.get("owner", "")).strip(),
            env_class=str(payload.get("class", "sandbox")).strip() or "sandbox",
            blueprint_name=str(payload.get("blueprint_name", "")).strip(),
            blueprint_version=str(payload.get("blueprint_version", "")).strip(),
            gitops_repo=str(payload.get("gitops_repo", "")).strip(),
            gitops_path=str(payload.get("gitops_path", "")).strip(),
            git_branch=str(payload.get("git_branch", "")).strip(),
            pull_request_url=str(payload.get("pull_request_url", "")).strip(),
            pull_request_number=int(payload.get("pull_request_number", 0) or 0),
            gates_outcome=str(payload.get("gates_outcome", "")).strip(),
            source_entity_id=str(payload.get("source_entity_id", "")).strip(),
            run_id=str(payload.get("run_id", "")).strip(),
            vended_by=str(payload.get("vended_by", "unknown")).strip() or "unknown",
            vended_at=str(payload.get("timestamp", "")).strip(),
            expires_at=str(payload.get("expires_at", "")).strip(),
            status=str(payload.get("status", "active")).strip() or "active",
        )


def entity_id_for_environment(*, cloud_provider: str, stack_name: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", f"{cloud_provider}-{stack_name}".lower()).strip("-")
    if not slug:
        slug = "stack"
    return f"env-{slug}"[:120]


def resolve_ttl_hours(
    env_class: str,
    *,
    default_ttl_hours: int,
    ttl_hours_by_class: tuple[tuple[str, int], ...],
) -> int | None:
    needle = env_class.strip().lower()
    for class_name, hours in ttl_hours_by_class:
        if class_name.strip().lower() == needle and hours > 0:
            return hours
    if default_ttl_hours > 0:
        return default_ttl_hours
    return None


def expires_at_from_ttl(*, ttl_hours: int | None, vended_at: str) -> str:
    if ttl_hours is None or ttl_hours <= 0:
        return ""
    try:
        start = datetime.fromisoformat(vended_at.replace("Z", "+00:00"))
    except ValueError:
        start = datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return (start + timedelta(hours=ttl_hours)).isoformat()
