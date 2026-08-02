"""TTL reclaim for expired sandbox environments via GitOps decommission PR (ADR 003 Phase 3)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from repave_engine.environment_record import (
    EnvironmentRecord,
    is_environment_expired,
    is_reclaim_eligible_class,
)
from repave_engine.environment_registry import decommission_environment, read_environments
from repave_engine.environment_vend import _commit_gitops_tree
from repave_engine.git_clone import FULL_DEPTH, CloneError, shallow_clone
from repave_engine.github import add_pull_request_labels, create_github_pull_request
from repave_engine.pr_conventions import branch_name, load_pull_request_conventions
from repave_engine.repo_import import preflight_import, push_import_branch
from repave_engine.settings import EnvironmentVendingConfig
from repave_engine.target_repo import resolve_module_repository_from_git

logger = logging.getLogger(__name__)


class EnvironmentReclaimError(RuntimeError):
    """Expected failure while reclaiming an environment (message names the fix)."""


@dataclass(frozen=True)
class EnvironmentReclaimResult:
    stack_name: str
    entity_id: str
    reclaimed: bool
    skipped: bool
    skip_reason: str
    gitops_repo: str
    gitops_path: str
    git_branch: str
    pull_request_url: str
    pull_request_number: int
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stack_name": self.stack_name,
            "entity_id": self.entity_id,
            "reclaimed": self.reclaimed,
            "skipped": self.skipped,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "detail": self.detail,
        }
        if self.skip_reason:
            payload["skip_reason"] = self.skip_reason
        if self.pull_request_url:
            payload["pull_request_url"] = self.pull_request_url
            payload["pull_request_number"] = self.pull_request_number
        return payload


@dataclass(frozen=True)
class EnvironmentReclaimSummary:
    results: tuple[EnvironmentReclaimResult, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "count": len(self.results),
            "reclaimed": sum(1 for item in self.results if item.reclaimed),
            "skipped": sum(1 for item in self.results if item.skipped),
            "results": [item.to_public_dict() for item in self.results],
        }


def build_environment_reclaim_pull_request_title(*, stack_name: str, env_class: str) -> str:
    return f"chore(repave): reclaim expired {env_class} environment `{stack_name}`"


def build_environment_reclaim_pull_request_body(
    *,
    record: EnvironmentRecord,
    repo_root: Path,
) -> str:
    lines = [
        "## Summary",
        (
            f"Expired governed environment `{record.stack_name}` "
            f"({record.environment_tier} on {record.cloud_provider}) is reclaimed by "
            "removing its GitOps path."
        ),
        "",
        "### Environment",
        f"- **Owner:** `{record.owner or 'unknown'}`",
        f"- **Class:** `{record.env_class or 'sandbox'}`",
        f"- **Expires at:** `{record.expires_at or 'unknown'}`",
        f"- **GitOps path:** `{record.gitops_path}`",
        "",
        "Review the diff before merging; CD applies desired state after merge.",
        "repave does not run `terraform apply`.",
    ]
    return "\n".join(lines) + "\n"


def list_expired_environments(
    records: Sequence[EnvironmentRecord],
    *,
    reclaim_classes: frozenset[str],
    now: datetime | None = None,
    stack_name: str | None = None,
) -> tuple[EnvironmentRecord, ...]:
    current = now or datetime.now(timezone.utc)
    eligible: list[EnvironmentRecord] = []
    for record in records:
        if stack_name and record.stack_name != stack_name.strip():
            continue
        if not is_reclaim_eligible_class(record.env_class, reclaim_classes):
            continue
        if not is_environment_expired(record, now=current):
            continue
        eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.stack_name))


def reclaim_environment(
    record: EnvironmentRecord,
    *,
    repo_root: Path,
    registry_path: Path,
    base_branch: str,
    github_token: str | None,
    dry_run: bool = False,
) -> EnvironmentReclaimResult:
    stack_name = record.stack_name
    entity_id = record.entity_id
    gitops_repo = record.gitops_repo.strip()
    path = record.gitops_path.strip().strip("/")
    if not gitops_repo:
        raise EnvironmentReclaimError(
            f"gitops_repo is missing on environment `{stack_name}`; "
            "re-register after vending with gitops_repo set"
        )
    if not path:
        raise EnvironmentReclaimError(
            f"gitops_path is missing on environment `{stack_name}`; "
            "re-register after vending with gitops_path set"
        )

    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, stack_name, "reclaim")
    resolved_base = base_branch.strip() or "main"

    if dry_run:
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            reclaimed=False,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=branch,
            pull_request_url="",
            pull_request_number=0,
            detail=(
                f"Dry-run: would open decommission PR removing `{path}` "
                f"from {gitops_repo} (expired {record.expires_at})."
            ),
        )

    if not github_token:
        raise EnvironmentReclaimError(
            "GITHUB_TOKEN is not configured; set it to open a GitOps decommission pull request"
        )

    with tempfile.TemporaryDirectory(prefix="repave-env-reclaim-") as tmp:
        clone_root = Path(tmp) / "gitops"
        try:
            shallow_clone(
                gitops_repo,
                clone_root,
                token=github_token,
                depth=FULL_DEPTH,
                ref=resolved_base,
            )
        except CloneError as exc:
            raise EnvironmentReclaimError(f"gitops clone failed: {exc}") from exc

        preflight = preflight_import(clone_root, github_token=github_token, git_branch=branch)
        if preflight.has_existing_pull_request:
            raise EnvironmentReclaimError(
                f"a pull request is already open for branch `{branch}`: "
                f"{preflight.existing_pull_request_url}"
            )

        dest = clone_root / path
        if not dest.exists():
            decommission_environment(registry_path, record)
            return EnvironmentReclaimResult(
                stack_name=stack_name,
                entity_id=entity_id,
                reclaimed=True,
                skipped=False,
                skip_reason="",
                gitops_repo=gitops_repo,
                gitops_path=path,
                git_branch=branch,
                pull_request_url="",
                pull_request_number=0,
                detail=(
                    f"GitOps path `{path}` already absent; removed `{stack_name}` "
                    "from the environment registry."
                ),
            )

        if dest.is_dir():
            shutil.rmtree(dest)
        else:
            dest.unlink()

        commit_message = (
            f"chore(repave): reclaim expired environment {stack_name}\n\n"
            f"Owner: {record.owner or 'unknown'}; class: {record.env_class or 'sandbox'}\n"
            f"Expired: {record.expires_at or 'unknown'}"
        )
        if not _commit_gitops_tree(clone_root, git_branch=branch, message=commit_message):
            raise EnvironmentReclaimError(
                f"no changes under `{path}` relative to {resolved_base or preflight.base_branch}; "
                "stack may already be reclaimed"
            )

        repository = resolve_module_repository_from_git(clone_root)
        push_import_branch(
            clone_root,
            repository,
            token=github_token,
            branch=branch,
        )

        title = build_environment_reclaim_pull_request_title(
            stack_name=stack_name,
            env_class=record.env_class,
        )
        body = build_environment_reclaim_pull_request_body(
            record=record,
            repo_root=repo_root,
        )
        resolved_base = resolved_base or preflight.base_branch
        pr_payload = create_github_pull_request(
            repository.owner,
            repository.name,
            title=title,
            body=body,
            head=branch,
            base=resolved_base,
            token=github_token,
            draft=False,
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
        decommission_environment(registry_path, record)
        detail = (
            f"Opened decommission pull request for `{path}` on {repository.web_url}; "
            f"removed `{stack_name}` from the environment registry."
        )
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            reclaimed=True,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=branch,
            pull_request_url=pr_url,
            pull_request_number=pr_number,
            detail=detail,
        )


def reclaim_expired_environments(
    *,
    repo_root: Path,
    config: EnvironmentVendingConfig,
    github_token: str | None,
    dry_run: bool = False,
    stack_name: str | None = None,
    now: datetime | None = None,
) -> EnvironmentReclaimSummary:
    reclaim_classes = frozenset(config.auto_reclaim_classes)
    records = read_environments(config.file)
    expired = list_expired_environments(
        records,
        reclaim_classes=reclaim_classes,
        now=now,
        stack_name=stack_name,
    )
    results: list[EnvironmentReclaimResult] = []
    for record in expired:
        try:
            results.append(
                reclaim_environment(
                    record,
                    repo_root=repo_root,
                    registry_path=config.file,
                    base_branch=config.base_branch,
                    github_token=github_token,
                    dry_run=dry_run,
                )
            )
        except EnvironmentReclaimError as exc:
            logger.warning("Environment reclaim failed for %s: %s", record.stack_name, exc)
            results.append(
                EnvironmentReclaimResult(
                    stack_name=record.stack_name,
                    entity_id=record.entity_id,
                    reclaimed=False,
                    skipped=True,
                    skip_reason=str(exc),
                    gitops_repo=record.gitops_repo,
                    gitops_path=record.gitops_path,
                    git_branch="",
                    pull_request_url="",
                    pull_request_number=0,
                    detail=str(exc),
                )
            )
    if stack_name and not expired:
        needle = stack_name.strip()
        match = next((item for item in records if item.stack_name == needle), None)
        if match is None:
            raise EnvironmentReclaimError(
                f"environment `{needle}` is not registered; "
                f"check {config.file} or omit --stack to scan all expired environments"
            )
        if not is_reclaim_eligible_class(match.env_class, reclaim_classes):
            raise EnvironmentReclaimError(
                f"environment `{needle}` class `{match.env_class}` is not in "
                f"auto_reclaim_classes {tuple(reclaim_classes)}"
            )
        if not is_environment_expired(match, now=now):
            raise EnvironmentReclaimError(
                f"environment `{needle}` is not expired (expires_at={match.expires_at or 'none'})"
            )
    return EnvironmentReclaimSummary(results=tuple(results))
