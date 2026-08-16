"""Environment vending — render governed stack and open a GitOps PR (ADR 003 Phase 3)."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import blueprint_dir, load_blueprint, validate_inputs
from repave_engine.gates import GateResult, RunEventCallback, all_gates_passed, gate_outcome
from repave_engine.git_clone import FULL_DEPTH, CloneError, shallow_clone
from repave_engine.github import (
    add_pull_request_labels,
    create_github_pull_request,
)
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.pr_conventions import (
    append_evidence_section,
    branch_name,
    load_pull_request_conventions,
)
from repave_engine.repo_import import preflight_import, push_import_branch
from repave_engine.settings import (
    EnvironmentVendingConfig,
    OutputConfig,
    load_gate_overrides,
)
from repave_engine.target_repo import (
    _copy_tree_contents,
    _run_git,
    resolve_module_repository_from_git,
)

logger = logging.getLogger(__name__)

ENVIRONMENT_VEND_BLUEPRINT_SENTINEL = "environment-vend"
DEFAULT_VEND_BLUEPRINT = "terraform-environment-stack"


class EnvironmentVendError(RuntimeError):
    """Expected failure while vending an environment (message names the fix)."""


@dataclass(frozen=True)
class EnvironmentVendResult:
    kind: str
    blueprint: str
    blueprint_version: str
    gates_outcome: str
    gates_passed: bool
    gitops_repo: str
    gitops_path: str
    git_branch: str
    owner: str
    env_class: str
    pull_request_url: str
    pull_request_number: int
    draft: bool
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind,
            "blueprint": self.blueprint,
            "blueprint_version": self.blueprint_version,
            "gates_outcome": self.gates_outcome,
            "gates_passed": self.gates_passed,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "owner": self.owner,
            "class": self.env_class,
            "detail": self.detail,
        }
        if self.pull_request_url:
            payload["pull_request_url"] = self.pull_request_url
            payload["pull_request_number"] = self.pull_request_number
            payload["draft"] = self.draft
        return payload


def is_environment_vend_run(payload: dict[str, Any]) -> bool:
    return str(payload.get("kind", "")).strip() == "environment_vend"


def build_environment_vend_pull_request_title(
    *,
    stack_name: str,
    environment: str,
    cloud_provider: str,
) -> str:
    return f"feat(repave): vend {environment} environment `{stack_name}` on {cloud_provider}"


def build_environment_vend_pull_request_body(
    *,
    stack_name: str,
    environment: str,
    cloud_provider: str,
    gitops_path: str,
    owner: str,
    env_class: str,
    blueprint_name: str,
    blueprint_version: str,
    gates: Sequence[GateResult],
    repo_root: Path,
) -> str:
    lines = [
        "## Summary",
        (
            f"Governed environment stack `{stack_name}` ({environment} on {cloud_provider}) "
            f"vended by repave blueprint `{blueprint_name}` v{blueprint_version}."
        ),
        "",
        "### Request",
        f"- **Owner:** `{owner or 'unknown'}`",
        f"- **Class:** `{env_class or 'sandbox'}`",
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


def _ensure_git_identity(repo_dir: Path) -> None:
    _run_git(["config", "user.email", "repave@local.dev"], cwd=repo_dir)
    _run_git(["config", "user.name", "repave"], cwd=repo_dir)


def _commit_gitops_tree(repo_dir: Path, *, git_branch: str, message: str) -> bool:
    _ensure_git_identity(repo_dir)
    _run_git(["checkout", "-B", git_branch], cwd=repo_dir)
    _run_git(["add", "-A"], cwd=repo_dir)
    try:
        _run_git(["diff", "--cached", "--quiet"], cwd=repo_dir)
        return False
    except subprocess.CalledProcessError:
        _run_git(["commit", "-m", message], cwd=repo_dir)
        return True


def _copy_rendered_stack(render_dir: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    _copy_tree_contents(render_dir, dest_dir, artifact_type="terraform-environment-stack")


def run_environment_vend(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    blueprint_name: str,
    inputs: dict[str, Any],
    gitops_repo: str,
    gitops_path: str,
    owner: str,
    env_class: str,
    base_branch: str,
    git_branch: str,
    dry_run: bool,
    github_token: str | None,
    on_event: RunEventCallback | None = None,
    pr_title: str = "",
    pr_body: str = "",
) -> EnvironmentVendResult:
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    gate_overrides = load_gate_overrides(repo_root)
    normalized = validate_inputs(
        blueprint,
        {str(k): str(v) for k, v in inputs.items()},
        repo_root=repo_root,
        gate_overrides=gate_overrides,
    )
    stack_name = str(normalized.get("stack_name", "")).strip() or "stack"
    environment = str(normalized.get("environment", "dev")).strip()
    cloud_provider = str(normalized.get("cloud_provider", "aws")).strip()

    conventions = load_pull_request_conventions(repo_root)
    branch = git_branch.strip() or branch_name(
        conventions.branch_prefix_vend,
        stack_name,
        environment,
    )
    path = gitops_path.strip().strip("/")
    if not path:
        raise EnvironmentVendError("gitops_path is required; set it on the request or in config")

    with tempfile.TemporaryDirectory(prefix="repave-env-vend-") as tmp:
        staging = Path(tmp) / "render"
        gen = generate_from_blueprint(
            blueprint,
            normalized,
            output_config=output_config,
            dry_run=True,
            require_run=True,
            github_token=None,
            staging_root=staging,
            repo_root=repo_root,
            on_event=on_event,
            send_notification=False,
            record_operability=False,
        )
        gates = list(gen.gates)
        outcome = gate_outcome(gates)
        passed = all_gates_passed(gates)

        if dry_run:
            detail = "Dry-run: gates evaluated; GitOps PR not opened."
            return EnvironmentVendResult(
                kind="environment_vend",
                blueprint=blueprint.name,
                blueprint_version=blueprint.version,
                gates_outcome=outcome,
                gates_passed=passed,
                gitops_repo=gitops_repo,
                gitops_path=path,
                git_branch=branch,
                owner=owner,
                env_class=env_class,
                pull_request_url="",
                pull_request_number=0,
                draft=False,
                detail=detail,
            )

        if not github_token:
            raise EnvironmentVendError(
                "GITHUB_TOKEN is not configured; set it to open a GitOps pull request"
            )
        if not gitops_repo.strip():
            raise EnvironmentVendError(
                "gitops_repo is required; set environment_vending.gitops_repo in "
                "repave.config.yaml or pass gitops_repo on the request"
            )

        clone_root = Path(tmp) / "gitops"
        try:
            shallow_clone(
                gitops_repo.strip(),
                clone_root,
                token=github_token,
                depth=FULL_DEPTH,
                ref=base_branch.strip() or None,
            )
        except CloneError as exc:
            raise EnvironmentVendError(f"gitops clone failed: {exc}") from exc

        preflight = preflight_import(clone_root, github_token=github_token, git_branch=branch)
        if preflight.has_existing_pull_request:
            raise EnvironmentVendError(
                f"a pull request is already open for branch `{branch}`: "
                f"{preflight.existing_pull_request_url}"
            )

        dest = clone_root / path
        if dest.exists():
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        _copy_rendered_stack(gen.render.output_dir, dest)

        commit_message = (
            f"feat(repave): vend {environment} environment {stack_name}\n\n"
            f"Blueprint: {blueprint.name}@{blueprint.version}\n"
            f"Owner: {owner or 'unknown'}; class: {env_class or 'sandbox'}"
        )
        if not _commit_gitops_tree(clone_root, git_branch=branch, message=commit_message):
            raise EnvironmentVendError(
                f"no changes under `{path}` relative to {base_branch or preflight.base_branch}; "
                "stack may already be vendored"
            )

        repository = resolve_module_repository_from_git(clone_root)
        push_import_branch(
            clone_root,
            repository,
            token=github_token,
            branch=branch,
        )

        title = pr_title.strip() or build_environment_vend_pull_request_title(
            stack_name=stack_name,
            environment=environment,
            cloud_provider=cloud_provider,
        )
        body = pr_body.strip() or build_environment_vend_pull_request_body(
            stack_name=stack_name,
            environment=environment,
            cloud_provider=cloud_provider,
            gitops_path=path,
            owner=owner,
            env_class=env_class,
            blueprint_name=blueprint.name,
            blueprint_version=blueprint.version,
            gates=gates,
            repo_root=repo_root,
        )
        resolved_base = base_branch.strip() or preflight.base_branch
        pr_payload = create_github_pull_request(
            repository.owner,
            repository.name,
            title=title,
            body=body,
            head=branch,
            base=resolved_base,
            token=github_token,
            draft=not passed,
        )
        pr_number = int(pr_payload.get("number", 0))
        if pr_number and conventions.labels:
            add_pull_request_labels(
                repository.owner,
                repository.name,
                pr_number,
                conventions.labels,
                github_token,
            )

        pr_url = str(pr_payload.get("html_url", ""))
        detail = (
            f"Opened {'draft ' if not passed else ''}pull request for `{path}` "
            f"on {repository.web_url}"
        )
        return EnvironmentVendResult(
            kind="environment_vend",
            blueprint=blueprint.name,
            blueprint_version=blueprint.version,
            gates_outcome=outcome,
            gates_passed=passed,
            gitops_repo=gitops_repo.strip(),
            gitops_path=path,
            git_branch=branch,
            owner=owner,
            env_class=env_class,
            pull_request_url=pr_url,
            pull_request_number=pr_number,
            draft=not passed,
            detail=detail,
        )


def resolve_vend_request_fields(
    payload: dict[str, Any],
    config: EnvironmentVendingConfig,
) -> tuple[str, str, str, str, str, str, bool]:
    """Return blueprint, gitops_repo, gitops_path, owner, env_class, base_branch, dry_run."""
    blueprint = (
        str(payload.get("blueprint", DEFAULT_VEND_BLUEPRINT)).strip() or DEFAULT_VEND_BLUEPRINT
    )
    gitops_repo = str(payload.get("gitops_repo", "")).strip() or config.gitops_repo
    base_branch = str(payload.get("base_branch", "")).strip() or config.base_branch
    owner = str(payload.get("owner", "")).strip()
    env_class = str(payload.get("class", "")).strip() or "sandbox"
    dry_run = bool(payload.get("dry_run", False))

    inputs_raw = payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise ValueError("inputs must be an object")
    stack_name = str(inputs_raw.get("stack_name", "")).strip()
    if not stack_name:
        raise ValueError("inputs.stack_name is required for kind=environment_vend")

    gitops_path = str(payload.get("gitops_path", "")).strip()
    if not gitops_path:
        prefix = config.path_prefix.strip().strip("/")
        gitops_path = f"{prefix}/{stack_name}" if prefix else stack_name

    if not gitops_repo and not dry_run:
        raise ValueError(
            "gitops_repo is required when dry_run is false; set environment_vending.gitops_repo "
            "in repave.config.yaml or pass gitops_repo on the request"
        )
    return blueprint, gitops_repo, gitops_path, owner, env_class, base_branch, dry_run
