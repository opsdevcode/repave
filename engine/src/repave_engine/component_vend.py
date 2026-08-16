"""Component vending — render a governed stack and open a GitOps PR (ADR 013)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.component_kinds import (
    COMPONENT_NAME_RE,
    DEFAULT_COMPONENT_BLUEPRINT,
    ComponentKind,
    ComponentVendError,
    find_component_kind,
)
from repave_engine.environment_vend import run_environment_vend
from repave_engine.gates import GateResult, RunEventCallback
from repave_engine.pr_conventions import append_evidence_section, load_pull_request_conventions
from repave_engine.settings import ComponentVendingConfig

COMPONENT_VEND_BLUEPRINT_SENTINEL = "component-vend"


@dataclass(frozen=True)
class ComponentVendResult:
    kind: str
    name: str
    blueprint: str
    blueprint_version: str
    gates_outcome: str
    gates_passed: bool
    gitops_repo: str
    gitops_path: str
    git_branch: str
    owner: str
    pull_request_url: str
    pull_request_number: int
    draft: bool
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": "component_vend",
            "component_kind": self.kind,
            "name": self.name,
            "blueprint": self.blueprint,
            "blueprint_version": self.blueprint_version,
            "gates_outcome": self.gates_outcome,
            "gates_passed": self.gates_passed,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "owner": self.owner,
            "detail": self.detail,
        }
        if self.pull_request_url:
            payload["pull_request_url"] = self.pull_request_url
            payload["pull_request_number"] = self.pull_request_number
            payload["draft"] = self.draft
        return payload


def is_component_vend_run(payload: dict[str, Any]) -> bool:
    return str(payload.get("kind", "")).strip() == "component_vend"


def build_component_vend_pull_request_title(*, kind: str, name: str, environment: str) -> str:
    return f"feat(repave): vend {kind} component `{name}` in {environment}"


def build_component_vend_pull_request_body(
    *,
    kind: str,
    name: str,
    environment: str,
    cloud_provider: str,
    gitops_path: str,
    owner: str,
    blueprint_name: str,
    blueprint_version: str,
    gates: Sequence[GateResult],
    repo_root: Path,
) -> str:
    lines = [
        "## Summary",
        (
            f"Governed `{kind}` component `{name}` ({environment} on {cloud_provider}) "
            f"vended by repave blueprint `{blueprint_name}` v{blueprint_version}."
        ),
        "",
        "### Request",
        f"- **Owner:** `{owner or 'unknown'}`",
        f"- **Kind:** `{kind}`",
        f"- **GitOps path:** `{gitops_path}`",
        "",
        "Review the diff before merging; CD applies desired state after merge.",
        "repave does not run `terraform apply`.",
    ]
    conventions = load_pull_request_conventions(repo_root)
    return append_evidence_section(
        "\n".join(lines) + "\n",
        gates,
        enabled=conventions.evidence_checklist,
    )


def resolve_component_vend_fields(
    payload: dict[str, Any],
    config: ComponentVendingConfig,
    kinds: tuple[ComponentKind, ...],
) -> tuple[ComponentKind, str, str, str, str, str, bool, dict[str, Any]]:
    """Return kind, name, gitops_repo, gitops_path, owner, base_branch, dry_run, inputs."""
    kind_id = str(payload.get("component_kind", payload.get("kind", ""))).strip()
    if kind_id == "component_vend":
        kind_id = str(payload.get("component_kind", "")).strip()
    inputs_raw = payload.get("inputs", {})
    if inputs_raw is None:
        inputs_raw = {}
    if not isinstance(inputs_raw, dict):
        raise ComponentVendError("inputs must be an object")
    if not kind_id:
        kind_id = str(inputs_raw.get("component_kind", "")).strip()
    name = str(payload.get("name", "")).strip() or str(inputs_raw.get("stack_name", "")).strip()
    if not kind_id:
        raise ComponentVendError("kind is required (database, bucket, or queue)")
    if not name:
        raise ComponentVendError("name is required")
    if COMPONENT_NAME_RE.fullmatch(name) is None:
        raise ComponentVendError("name must be 3-63 lowercase letters, numbers, and hyphens")
    kind = find_component_kind(kinds, kind_id)
    if kind is None:
        known = ", ".join(item.id for item in kinds) or "database, bucket, queue"
        raise ComponentVendError(f"unknown component kind {kind_id!r}; known: {known}")
    owner = str(payload.get("owner", "")).strip() or str(inputs_raw.get("owner", "")).strip()
    dry_run = bool(payload.get("dry_run", True))
    gitops_repo = str(payload.get("gitops_repo", "")).strip() or config.gitops_repo
    base_branch = str(payload.get("base_branch", "")).strip() or config.base_branch
    gitops_path = str(payload.get("gitops_path", "")).strip()
    if not gitops_path:
        prefix = config.path_prefix.strip().strip("/")
        gitops_path = f"{prefix}/{kind.id}/{name}" if prefix else f"{kind.id}/{name}"
    if not gitops_repo and not dry_run:
        raise ComponentVendError(
            "gitops_repo is required when dry_run is false; set component_vending.gitops_repo "
            "in repave.config.yaml or pass gitops_repo on the request"
        )
    inputs: dict[str, Any] = dict(kind.default_inputs)
    inputs.update({str(key): value for key, value in inputs_raw.items()})
    inputs["stack_name"] = name
    inputs.setdefault("description", kind.default_inputs.get("description") or f"{kind.label}")
    inputs.setdefault("cloud_provider", str(payload.get("cloud_provider", "aws")).strip() or "aws")
    inputs.setdefault("environment", str(payload.get("environment", "dev")).strip() or "dev")
    if owner:
        inputs.setdefault("owner", owner)
    inputs["component_kind"] = kind.id
    return kind, name, gitops_repo, gitops_path, owner, base_branch, dry_run, inputs


def run_component_vend(
    *,
    repo_root: Path,
    output_config: Any,
    blueprint_name: str,
    inputs: dict[str, Any],
    gitops_repo: str,
    gitops_path: str,
    owner: str,
    component_kind: str,
    name: str,
    base_branch: str,
    git_branch: str,
    dry_run: bool,
    github_token: str | None,
    on_event: RunEventCallback | None = None,
) -> ComponentVendResult:
    environment = str(inputs.get("environment", "dev")).strip() or "dev"
    env_result = run_environment_vend(
        repo_root=repo_root,
        output_config=output_config,
        blueprint_name=blueprint_name or DEFAULT_COMPONENT_BLUEPRINT,
        inputs=inputs,
        gitops_repo=gitops_repo,
        gitops_path=gitops_path,
        owner=owner,
        env_class=component_kind,
        base_branch=base_branch,
        git_branch=git_branch,
        dry_run=dry_run,
        github_token=github_token,
        on_event=on_event,
        pr_title=build_component_vend_pull_request_title(
            kind=component_kind, name=name, environment=environment
        ),
    )
    return ComponentVendResult(
        kind=component_kind,
        name=name,
        blueprint=env_result.blueprint,
        blueprint_version=env_result.blueprint_version,
        gates_outcome=env_result.gates_outcome,
        gates_passed=env_result.gates_passed,
        gitops_repo=env_result.gitops_repo,
        gitops_path=env_result.gitops_path,
        git_branch=env_result.git_branch,
        owner=env_result.owner,
        pull_request_url=env_result.pull_request_url,
        pull_request_number=env_result.pull_request_number,
        draft=env_result.draft,
        detail=env_result.detail,
    )
