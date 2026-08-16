"""Component record model for vended GitOps managed resources (ADR 013)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
        )
