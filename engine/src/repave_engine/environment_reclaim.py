"""TTL reclaim and decommission review for expired environments (ADR 003 Phase 3)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from repave_engine.environment_record import (
    EnvironmentRecord,
    has_open_decommission_review,
    is_environment_expired,
    is_reclaim_eligible_class,
    resolve_decommission_review_classes,
)
from repave_engine.environment_registry import (
    decommission_environment,
    mark_environment_expired,
    read_environments,
)
from repave_engine.environment_vend import _commit_gitops_tree
from repave_engine.git_clone import FULL_DEPTH, CloneError, shallow_clone
from repave_engine.github import (
    GitHubError,
    add_pull_request_labels,
    create_github_pull_request,
    get_pull_request,
)
from repave_engine.github_inventory import GitHubInventoryError, parse_github_repository
from repave_engine.pr_conventions import branch_name, load_pull_request_conventions
from repave_engine.repo_import import preflight_import, push_import_branch
from repave_engine.settings import EnvironmentVendingConfig
from repave_engine.target_repo import resolve_module_repository_from_git

logger = logging.getLogger(__name__)

MODE_AUTO_RECLAIM = "auto_reclaim"
MODE_DECOMMISSION_REVIEW = "decommission_review"
MODE_REGISTRY_FINALIZE = "registry_finalize"

PullRequestMergeState = Literal["merged", "open", "closed", "unknown"]


class EnvironmentReclaimError(RuntimeError):
    """Expected failure while reclaiming an environment (message names the fix)."""


@dataclass(frozen=True)
class EnvironmentReclaimResult:
    stack_name: str
    entity_id: str
    mode: str
    reclaimed: bool
    skipped: bool
    skip_reason: str
    gitops_repo: str
    gitops_path: str
    git_branch: str
    pull_request_url: str
    pull_request_number: int
    draft: bool
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stack_name": self.stack_name,
            "entity_id": self.entity_id,
            "mode": self.mode,
            "reclaimed": self.reclaimed,
            "skipped": self.skipped,
            "gitops_repo": self.gitops_repo,
            "gitops_path": self.gitops_path,
            "git_branch": self.git_branch,
            "draft": self.draft,
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
            "decommission_review": sum(
                1
                for item in self.results
                if item.mode == MODE_DECOMMISSION_REVIEW and not item.skipped
            ),
            "finalized": sum(
                1 for item in self.results if item.mode == MODE_REGISTRY_FINALIZE and item.reclaimed
            ),
            "skipped": sum(1 for item in self.results if item.skipped),
            "results": [item.to_public_dict() for item in self.results],
        }


@dataclass(frozen=True)
class _DecommissionPrOutcome:
    pull_request_url: str
    pull_request_number: int
    git_branch: str
    path_already_absent: bool
    repository_web_url: str


def build_environment_reclaim_pull_request_title(*, stack_name: str, env_class: str) -> str:
    return f"chore(repave): reclaim expired {env_class} environment `{stack_name}`"


def build_environment_decommission_review_pull_request_title(
    *,
    stack_name: str,
    env_class: str,
) -> str:
    return f"chore(repave): decommission expired {env_class} environment `{stack_name}`"


def build_environment_reclaim_pull_request_body(
    *,
    record: EnvironmentRecord,
    repo_root: Path,
    requires_review: bool = False,
) -> str:
    action = (
        "is proposed for decommission by removing its GitOps path."
        if requires_review
        else "is reclaimed by removing its GitOps path."
    )
    lines = [
        "## Summary",
        (
            f"Expired governed environment `{record.stack_name}` "
            f"({record.environment_tier} on {record.cloud_provider}) {action}"
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
    if requires_review:
        lines.extend(
            [
                "",
                "This is a **draft** decommission pull request for human review.",
            ]
        )
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


def list_expired_environments_for_decommission_review(
    records: Sequence[EnvironmentRecord],
    *,
    auto_reclaim_classes: frozenset[str],
    review_classes: frozenset[str],
    now: datetime | None = None,
    stack_name: str | None = None,
) -> tuple[EnvironmentRecord, ...]:
    current = now or datetime.now(timezone.utc)
    eligible: list[EnvironmentRecord] = []
    for record in records:
        if stack_name and record.stack_name != stack_name.strip():
            continue
        if is_reclaim_eligible_class(record.env_class, auto_reclaim_classes):
            continue
        if not is_reclaim_eligible_class(record.env_class, review_classes):
            continue
        if not is_environment_expired(record, now=current):
            continue
        if has_open_decommission_review(record):
            continue
        eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.stack_name))


def list_pending_decommission_reviews(
    records: Sequence[EnvironmentRecord],
    *,
    stack_name: str | None = None,
) -> tuple[EnvironmentRecord, ...]:
    eligible: list[EnvironmentRecord] = []
    for record in records:
        if stack_name and record.stack_name != stack_name.strip():
            continue
        if has_open_decommission_review(record):
            eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.stack_name))


def resolve_decommission_pull_request_state(
    record: EnvironmentRecord,
    *,
    github_token: str,
) -> PullRequestMergeState:
    if record.pull_request_number <= 0:
        return "unknown"
    gitops_repo = record.gitops_repo.strip()
    if not gitops_repo:
        return "unknown"
    try:
        owner, repo = parse_github_repository(gitops_repo)
    except GitHubInventoryError:
        return "unknown"
    try:
        payload = get_pull_request(owner, repo, record.pull_request_number, github_token)
    except GitHubError:
        return "unknown"
    if payload.get("merged_at"):
        return "merged"
    state = str(payload.get("state", "")).strip().lower()
    if state == "open":
        return "open"
    if state == "closed":
        return "closed"
    return "unknown"


def finalize_merged_decommission(
    record: EnvironmentRecord,
    *,
    registry_path: Path,
    github_token: str,
    dry_run: bool = False,
) -> EnvironmentReclaimResult:
    stack_name = record.stack_name
    entity_id = record.entity_id
    gitops_repo, path = _validate_record_fields(record)
    merge_state = resolve_decommission_pull_request_state(record, github_token=github_token)

    if merge_state == "open":
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_REGISTRY_FINALIZE,
            reclaimed=False,
            skipped=True,
            skip_reason="decommission pull request is still open",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=record.git_branch,
            pull_request_url=record.pull_request_url,
            pull_request_number=record.pull_request_number,
            draft=True,
            detail=(
                f"Decommission pull request #{record.pull_request_number} is still open; "
                f"`{stack_name}` remains in the registry with status expired."
            ),
        )

    if merge_state == "closed":
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_REGISTRY_FINALIZE,
            reclaimed=False,
            skipped=True,
            skip_reason="decommission pull request closed without merge",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=record.git_branch,
            pull_request_url=record.pull_request_url,
            pull_request_number=record.pull_request_number,
            draft=True,
            detail=(
                f"Decommission pull request #{record.pull_request_number} was closed without "
                f"merge; `{stack_name}` remains expired in the registry for operator review."
            ),
        )

    if merge_state != "merged":
        raise EnvironmentReclaimError(
            f"could not resolve merge state for decommission pull request "
            f"#{record.pull_request_number} on `{gitops_repo}`; "
            "check GITHUB_TOKEN access to the GitOps repository"
        )

    if dry_run:
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_REGISTRY_FINALIZE,
            reclaimed=False,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=record.git_branch,
            pull_request_url=record.pull_request_url,
            pull_request_number=record.pull_request_number,
            draft=True,
            detail=(
                f"Dry-run: would remove `{stack_name}` from the registry after merged "
                f"decommission pull request #{record.pull_request_number}."
            ),
        )

    decommission_environment(registry_path, record)
    return EnvironmentReclaimResult(
        stack_name=stack_name,
        entity_id=entity_id,
        mode=MODE_REGISTRY_FINALIZE,
        reclaimed=True,
        skipped=False,
        skip_reason="",
        gitops_repo=gitops_repo,
        gitops_path=path,
        git_branch=record.git_branch,
        pull_request_url=record.pull_request_url,
        pull_request_number=record.pull_request_number,
        draft=True,
        detail=(
            f"Removed `{stack_name}` from the registry after merged decommission pull request "
            f"#{record.pull_request_number}."
        ),
    )


def _execute_decommission_pr(
    record: EnvironmentRecord,
    *,
    repo_root: Path,
    base_branch: str,
    github_token: str,
    draft: bool,
) -> _DecommissionPrOutcome:
    stack_name = record.stack_name
    gitops_repo = record.gitops_repo.strip()
    path = record.gitops_path.strip().strip("/")
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, stack_name, "reclaim")
    resolved_base = base_branch.strip() or "main"

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
            return _DecommissionPrOutcome(
                pull_request_url="",
                pull_request_number=0,
                git_branch=branch,
                path_already_absent=True,
                repository_web_url=gitops_repo,
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

        title_builder = (
            build_environment_decommission_review_pull_request_title
            if draft
            else build_environment_reclaim_pull_request_title
        )
        title = title_builder(stack_name=stack_name, env_class=record.env_class)
        body = build_environment_reclaim_pull_request_body(
            record=record,
            repo_root=repo_root,
            requires_review=draft,
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
            draft=draft,
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

        return _DecommissionPrOutcome(
            pull_request_url=str(pr_payload.get("html_url", "")),
            pull_request_number=pr_number,
            git_branch=branch,
            path_already_absent=False,
            repository_web_url=repository.web_url,
        )


def _validate_record_fields(record: EnvironmentRecord) -> tuple[str, str]:
    stack_name = record.stack_name
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
    return gitops_repo, path


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
    gitops_repo, path = _validate_record_fields(record)
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, stack_name, "reclaim")

    if dry_run:
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_AUTO_RECLAIM,
            reclaimed=False,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=branch,
            pull_request_url="",
            pull_request_number=0,
            draft=False,
            detail=(
                f"Dry-run: would open decommission PR removing `{path}` "
                f"from {gitops_repo} (expired {record.expires_at})."
            ),
        )

    if not github_token:
        raise EnvironmentReclaimError(
            "GITHUB_TOKEN is not configured; set it to open a GitOps decommission pull request"
        )

    outcome = _execute_decommission_pr(
        record,
        repo_root=repo_root,
        base_branch=base_branch,
        github_token=github_token,
        draft=False,
    )
    if outcome.path_already_absent:
        decommission_environment(registry_path, record)
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_AUTO_RECLAIM,
            reclaimed=True,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=outcome.git_branch,
            pull_request_url="",
            pull_request_number=0,
            draft=False,
            detail=(
                f"GitOps path `{path}` already absent; removed `{stack_name}` "
                "from the environment registry."
            ),
        )

    decommission_environment(registry_path, record)
    detail = (
        f"Opened decommission pull request for `{path}` on {outcome.repository_web_url}; "
        f"removed `{stack_name}` from the environment registry."
    )
    return EnvironmentReclaimResult(
        stack_name=stack_name,
        entity_id=entity_id,
        mode=MODE_AUTO_RECLAIM,
        reclaimed=True,
        skipped=False,
        skip_reason="",
        gitops_repo=gitops_repo,
        gitops_path=path,
        git_branch=outcome.git_branch,
        pull_request_url=outcome.pull_request_url,
        pull_request_number=outcome.pull_request_number,
        draft=False,
        detail=detail,
    )


def request_decommission_review(
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
    gitops_repo, path = _validate_record_fields(record)
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, stack_name, "reclaim")

    if dry_run:
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_DECOMMISSION_REVIEW,
            reclaimed=False,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=branch,
            pull_request_url="",
            pull_request_number=0,
            draft=True,
            detail=(
                f"Dry-run: would open draft decommission PR removing `{path}` "
                f"from {gitops_repo} (expired {record.expires_at})."
            ),
        )

    if not github_token:
        raise EnvironmentReclaimError(
            "GITHUB_TOKEN is not configured; set it to open a GitOps decommission pull request"
        )

    outcome = _execute_decommission_pr(
        record,
        repo_root=repo_root,
        base_branch=base_branch,
        github_token=github_token,
        draft=True,
    )
    if outcome.path_already_absent:
        decommission_environment(registry_path, record)
        return EnvironmentReclaimResult(
            stack_name=stack_name,
            entity_id=entity_id,
            mode=MODE_DECOMMISSION_REVIEW,
            reclaimed=True,
            skipped=False,
            skip_reason="",
            gitops_repo=gitops_repo,
            gitops_path=path,
            git_branch=outcome.git_branch,
            pull_request_url="",
            pull_request_number=0,
            draft=False,
            detail=(
                f"GitOps path `{path}` already absent; removed `{stack_name}` "
                "from the environment registry."
            ),
        )

    mark_environment_expired(
        registry_path,
        record,
        pull_request_url=outcome.pull_request_url,
        pull_request_number=outcome.pull_request_number,
        git_branch=outcome.git_branch,
    )
    detail = (
        f"Opened draft decommission pull request for `{path}` on "
        f"{outcome.repository_web_url}; marked `{stack_name}` expired in the registry."
    )
    return EnvironmentReclaimResult(
        stack_name=stack_name,
        entity_id=entity_id,
        mode=MODE_DECOMMISSION_REVIEW,
        reclaimed=False,
        skipped=False,
        skip_reason="",
        gitops_repo=gitops_repo,
        gitops_path=path,
        git_branch=outcome.git_branch,
        pull_request_url=outcome.pull_request_url,
        pull_request_number=outcome.pull_request_number,
        draft=True,
        detail=detail,
    )


def _append_result_on_error(
    results: list[EnvironmentReclaimResult],
    record: EnvironmentRecord,
    *,
    mode: str,
    exc: EnvironmentReclaimError,
) -> None:
    logger.warning("Environment reclaim failed for %s: %s", record.stack_name, exc)
    results.append(
        EnvironmentReclaimResult(
            stack_name=record.stack_name,
            entity_id=record.entity_id,
            mode=mode,
            reclaimed=False,
            skipped=True,
            skip_reason=str(exc),
            gitops_repo=record.gitops_repo,
            gitops_path=record.gitops_path,
            git_branch="",
            pull_request_url="",
            pull_request_number=0,
            draft=mode == MODE_DECOMMISSION_REVIEW,
            detail=str(exc),
        )
    )


def _validate_stack_filter(
    *,
    stack_name: str | None,
    records: tuple[EnvironmentRecord, ...],
    auto_reclaim_classes: frozenset[str],
    review_classes: frozenset[str],
    now: datetime | None,
) -> None:
    if not stack_name:
        return
    needle = stack_name.strip()
    match = next((item for item in records if item.stack_name == needle), None)
    if match is None:
        raise EnvironmentReclaimError(
            f"environment `{needle}` is not registered; "
            "check the registry file or omit --stack to scan all expired environments"
        )
    if not is_environment_expired(match, now=now):
        raise EnvironmentReclaimError(
            f"environment `{needle}` is not expired (expires_at={match.expires_at or 'none'})"
        )
    if has_open_decommission_review(match):
        raise EnvironmentReclaimError(
            f"environment `{needle}` already has decommission review pull request "
            f"#{match.pull_request_number}"
        )
    auto = is_reclaim_eligible_class(match.env_class, auto_reclaim_classes)
    review = is_reclaim_eligible_class(match.env_class, review_classes)
    if not auto and not review:
        raise EnvironmentReclaimError(
            f"environment `{needle}` class `{match.env_class}` is not eligible for reclaim "
            f"(auto_reclaim_classes={tuple(auto_reclaim_classes)}, "
            f"decommission_review_classes={tuple(review_classes)})"
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
    auto_reclaim_classes = frozenset(config.auto_reclaim_classes)
    records = read_environments(config.file)
    observed_classes = frozenset(
        item.env_class.strip().lower() for item in records if item.env_class.strip()
    )
    review_classes = resolve_decommission_review_classes(
        auto_reclaim_classes=config.auto_reclaim_classes,
        configured_review_classes=config.decommission_review_classes,
        observed_classes=observed_classes,
    )

    results: list[EnvironmentReclaimResult] = []
    pending_reviews = list_pending_decommission_reviews(records, stack_name=stack_name)
    if pending_reviews:
        if not github_token:
            for record in pending_reviews:
                results.append(
                    EnvironmentReclaimResult(
                        stack_name=record.stack_name,
                        entity_id=record.entity_id,
                        mode=MODE_REGISTRY_FINALIZE,
                        reclaimed=False,
                        skipped=True,
                        skip_reason="GITHUB_TOKEN is required to check decommission PR merge state",
                        gitops_repo=record.gitops_repo,
                        gitops_path=record.gitops_path,
                        git_branch=record.git_branch,
                        pull_request_url=record.pull_request_url,
                        pull_request_number=record.pull_request_number,
                        draft=True,
                        detail=(
                            f"Skipped registry finalize for `{record.stack_name}`; "
                            "set GITHUB_TOKEN to detect merged decommission pull requests."
                        ),
                    )
                )
        else:
            for record in pending_reviews:
                try:
                    results.append(
                        finalize_merged_decommission(
                            record,
                            registry_path=config.file,
                            github_token=github_token,
                            dry_run=dry_run,
                        )
                    )
                except EnvironmentReclaimError as exc:
                    _append_result_on_error(
                        results,
                        record,
                        mode=MODE_REGISTRY_FINALIZE,
                        exc=exc,
                    )

    auto_expired = list_expired_environments(
        records,
        reclaim_classes=auto_reclaim_classes,
        now=now,
        stack_name=stack_name,
    )
    review_expired = list_expired_environments_for_decommission_review(
        records,
        auto_reclaim_classes=auto_reclaim_classes,
        review_classes=review_classes,
        now=now,
        stack_name=stack_name,
    )

    for record in auto_expired:
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
            _append_result_on_error(
                results,
                record,
                mode=MODE_AUTO_RECLAIM,
                exc=exc,
            )

    for record in review_expired:
        try:
            results.append(
                request_decommission_review(
                    record,
                    repo_root=repo_root,
                    registry_path=config.file,
                    base_branch=config.base_branch,
                    github_token=github_token,
                    dry_run=dry_run,
                )
            )
        except EnvironmentReclaimError as exc:
            _append_result_on_error(
                results,
                record,
                mode=MODE_DECOMMISSION_REVIEW,
                exc=exc,
            )

    if stack_name and not auto_expired and not review_expired:
        _validate_stack_filter(
            stack_name=stack_name,
            records=records,
            auto_reclaim_classes=auto_reclaim_classes,
            review_classes=review_classes,
            now=now,
        )
    return EnvironmentReclaimSummary(results=tuple(results))
