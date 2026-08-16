"""TTL reclaim and decommission review for expired components (ADR 013)."""

from __future__ import annotations

import logging
import shutil
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from repave_engine.component_record import (
    ComponentRecord,
    has_open_decommission_review,
    is_component_expired,
    is_reclaim_eligible_kind,
    resolve_decommission_review_kinds,
)
from repave_engine.component_registry import (
    decommission_component,
    mark_component_expired,
    read_components,
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
from repave_engine.settings import ComponentVendingConfig
from repave_engine.target_repo import resolve_module_repository_from_git

logger = logging.getLogger(__name__)

MODE_AUTO_RECLAIM = "auto_reclaim"
MODE_DECOMMISSION_REVIEW = "decommission_review"
MODE_REGISTRY_FINALIZE = "registry_finalize"

PullRequestMergeState = Literal["merged", "open", "closed", "unknown"]


class ComponentReclaimError(RuntimeError):
    """Expected failure while reclaiming a component (message names the fix)."""


@dataclass(frozen=True)
class ComponentReclaimResult:
    name: str
    kind: str
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
            "name": self.name,
            "kind": self.kind,
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
class ComponentReclaimSummary:
    results: tuple[ComponentReclaimResult, ...]

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


def build_component_reclaim_pull_request_title(*, kind: str, name: str) -> str:
    return f"chore(repave): reclaim expired {kind} component `{name}`"


def build_component_decommission_review_pull_request_title(*, kind: str, name: str) -> str:
    return f"chore(repave): decommission expired {kind} component `{name}`"


def build_component_reclaim_pull_request_body(
    *,
    record: ComponentRecord,
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
            f"Expired governed component `{record.name}` "
            f"({record.kind} on {record.cloud_provider}) {action}"
        ),
        "",
        "### Component",
        f"- **Owner:** `{record.owner or 'unknown'}`",
        f"- **Kind:** `{record.kind}`",
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


def _matches_filter(
    record: ComponentRecord,
    *,
    name: str | None,
    kind: str | None,
) -> bool:
    return (not name or record.name == name.strip()) and (not kind or record.kind == kind.strip())


def list_expired_components(
    records: Sequence[ComponentRecord],
    *,
    reclaim_kinds: frozenset[str],
    now: datetime | None = None,
    name: str | None = None,
    kind: str | None = None,
) -> tuple[ComponentRecord, ...]:
    current = now or datetime.now(timezone.utc)
    eligible: list[ComponentRecord] = []
    for record in records:
        if not _matches_filter(record, name=name, kind=kind):
            continue
        if not is_reclaim_eligible_kind(record.kind, reclaim_kinds):
            continue
        if not is_component_expired(record, now=current):
            continue
        eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.entity_id))


def list_expired_components_for_decommission_review(
    records: Sequence[ComponentRecord],
    *,
    auto_reclaim_kinds: frozenset[str],
    review_kinds: frozenset[str],
    now: datetime | None = None,
    name: str | None = None,
    kind: str | None = None,
) -> tuple[ComponentRecord, ...]:
    current = now or datetime.now(timezone.utc)
    eligible: list[ComponentRecord] = []
    for record in records:
        if not _matches_filter(record, name=name, kind=kind):
            continue
        if is_reclaim_eligible_kind(record.kind, auto_reclaim_kinds):
            continue
        if not is_reclaim_eligible_kind(record.kind, review_kinds):
            continue
        if not is_component_expired(record, now=current):
            continue
        if has_open_decommission_review(record):
            continue
        eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.entity_id))


def list_pending_decommission_reviews(
    records: Sequence[ComponentRecord],
    *,
    name: str | None = None,
    kind: str | None = None,
) -> tuple[ComponentRecord, ...]:
    eligible: list[ComponentRecord] = []
    for record in records:
        if not _matches_filter(record, name=name, kind=kind):
            continue
        if has_open_decommission_review(record):
            eligible.append(record)
    return tuple(sorted(eligible, key=lambda item: item.entity_id))


def resolve_decommission_pull_request_state(
    record: ComponentRecord,
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


def _validate_record_fields(record: ComponentRecord) -> tuple[str, str]:
    name = record.name
    gitops_repo = record.gitops_repo.strip()
    path = record.gitops_path.strip().strip("/")
    if not gitops_repo:
        raise ComponentReclaimError(
            f"gitops_repo is missing on component `{name}`; "
            "re-register after vending with gitops_repo set"
        )
    if not path:
        raise ComponentReclaimError(
            f"gitops_path is missing on component `{name}`; "
            "re-register after vending with gitops_path set"
        )
    return gitops_repo, path


def finalize_merged_decommission(
    record: ComponentRecord,
    *,
    registry_path: Path,
    github_token: str,
    dry_run: bool = False,
) -> ComponentReclaimResult:
    name = record.name
    gitops_repo, path = _validate_record_fields(record)
    merge_state = resolve_decommission_pull_request_state(record, github_token=github_token)

    if merge_state == "open":
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
                f"`{name}` remains in the registry with status expired."
            ),
        )

    if merge_state == "closed":
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
                f"merge; `{name}` remains expired in the registry for operator review."
            ),
        )

    if merge_state != "merged":
        raise ComponentReclaimError(
            f"could not resolve merge state for decommission pull request "
            f"#{record.pull_request_number} on `{gitops_repo}`; "
            "check GITHUB_TOKEN access to the GitOps repository"
        )

    if dry_run:
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
                f"Dry-run: would remove `{name}` from the registry after merged "
                f"decommission pull request #{record.pull_request_number}."
            ),
        )

    decommission_component(registry_path, record)
    return ComponentReclaimResult(
        name=name,
        kind=record.kind,
        entity_id=record.entity_id,
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
            f"Removed `{name}` from the registry after merged decommission pull request "
            f"#{record.pull_request_number}."
        ),
    )


def _execute_decommission_pr(
    record: ComponentRecord,
    *,
    repo_root: Path,
    base_branch: str,
    github_token: str,
    draft: bool,
) -> _DecommissionPrOutcome:
    name = record.name
    gitops_repo = record.gitops_repo.strip()
    path = record.gitops_path.strip().strip("/")
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, name, "reclaim")
    resolved_base = base_branch.strip() or "main"

    with tempfile.TemporaryDirectory(prefix="repave-cmp-reclaim-") as tmp:
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
            raise ComponentReclaimError(f"gitops clone failed: {exc}") from exc

        preflight = preflight_import(clone_root, github_token=github_token, git_branch=branch)
        if preflight.has_existing_pull_request:
            raise ComponentReclaimError(
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
            f"chore(repave): reclaim expired component {name}\n\n"
            f"Owner: {record.owner or 'unknown'}; kind: {record.kind}\n"
            f"Expired: {record.expires_at or 'unknown'}"
        )
        if not _commit_gitops_tree(clone_root, git_branch=branch, message=commit_message):
            raise ComponentReclaimError(
                f"no changes under `{path}` relative to {resolved_base or preflight.base_branch}; "
                "component may already be reclaimed"
            )

        repository = resolve_module_repository_from_git(clone_root)
        push_import_branch(
            clone_root,
            repository,
            token=github_token,
            branch=branch,
        )

        title_builder = (
            build_component_decommission_review_pull_request_title
            if draft
            else build_component_reclaim_pull_request_title
        )
        title = title_builder(kind=record.kind, name=name)
        body = build_component_reclaim_pull_request_body(
            record=record,
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


def reclaim_component(
    record: ComponentRecord,
    *,
    repo_root: Path,
    registry_path: Path,
    base_branch: str,
    github_token: str | None,
    dry_run: bool = False,
) -> ComponentReclaimResult:
    name = record.name
    gitops_repo, path = _validate_record_fields(record)
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, name, "reclaim")

    if dry_run:
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
        raise ComponentReclaimError(
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
        decommission_component(registry_path, record)
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
                f"GitOps path `{path}` already absent; removed `{name}` "
                "from the component registry."
            ),
        )

    decommission_component(registry_path, record)
    detail = (
        f"Opened decommission pull request for `{path}` on {outcome.repository_web_url}; "
        f"removed `{name}` from the component registry."
    )
    return ComponentReclaimResult(
        name=name,
        kind=record.kind,
        entity_id=record.entity_id,
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
    record: ComponentRecord,
    *,
    repo_root: Path,
    registry_path: Path,
    base_branch: str,
    github_token: str | None,
    dry_run: bool = False,
) -> ComponentReclaimResult:
    name = record.name
    gitops_repo, path = _validate_record_fields(record)
    conventions = load_pull_request_conventions(repo_root)
    branch = branch_name(conventions.branch_prefix_reclaim, name, "reclaim")

    if dry_run:
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
        raise ComponentReclaimError(
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
        decommission_component(registry_path, record)
        return ComponentReclaimResult(
            name=name,
            kind=record.kind,
            entity_id=record.entity_id,
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
                f"GitOps path `{path}` already absent; removed `{name}` "
                "from the component registry."
            ),
        )

    mark_component_expired(
        registry_path,
        record,
        pull_request_url=outcome.pull_request_url,
        pull_request_number=outcome.pull_request_number,
        git_branch=outcome.git_branch,
    )
    detail = (
        f"Opened draft decommission pull request for `{path}` on "
        f"{outcome.repository_web_url}; marked `{name}` expired in the registry."
    )
    return ComponentReclaimResult(
        name=name,
        kind=record.kind,
        entity_id=record.entity_id,
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
    results: list[ComponentReclaimResult],
    record: ComponentRecord,
    *,
    mode: str,
    exc: ComponentReclaimError,
) -> None:
    logger.warning("Component reclaim failed for %s: %s", record.name, exc)
    results.append(
        ComponentReclaimResult(
            name=record.name,
            kind=record.kind,
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


def _validate_name_filter(
    *,
    name: str | None,
    kind: str | None,
    records: tuple[ComponentRecord, ...],
    auto_reclaim_kinds: frozenset[str],
    review_kinds: frozenset[str],
    now: datetime | None,
) -> None:
    if not name:
        return
    needle = name.strip()
    matches = [item for item in records if item.name == needle]
    if kind:
        matches = [item for item in matches if item.kind == kind.strip()]
    if not matches:
        hint = f" `{kind}`" if kind else ""
        raise ComponentReclaimError(
            f"component{hint} `{needle}` is not registered; "
            "check the registry file or omit name to scan all expired components"
        )
    match = matches[0]
    if not is_component_expired(match, now=now):
        raise ComponentReclaimError(
            f"component `{needle}` is not expired (expires_at={match.expires_at or 'none'})"
        )
    if has_open_decommission_review(match):
        raise ComponentReclaimError(
            f"component `{needle}` already has decommission review pull request "
            f"#{match.pull_request_number}"
        )
    auto = is_reclaim_eligible_kind(match.kind, auto_reclaim_kinds)
    review = is_reclaim_eligible_kind(match.kind, review_kinds)
    if not auto and not review:
        raise ComponentReclaimError(
            f"component `{needle}` kind `{match.kind}` is not eligible for reclaim "
            f"(auto_reclaim_kinds={tuple(auto_reclaim_kinds)}, "
            f"decommission_review_kinds={tuple(review_kinds)})"
        )


def reclaim_expired_components(
    *,
    repo_root: Path,
    config: ComponentVendingConfig,
    github_token: str | None,
    dry_run: bool = False,
    name: str | None = None,
    kind: str | None = None,
    now: datetime | None = None,
) -> ComponentReclaimSummary:
    auto_reclaim_kinds = frozenset(config.auto_reclaim_kinds)
    records = read_components(config.file)
    observed_kinds = frozenset(item.kind.strip().lower() for item in records if item.kind.strip())
    review_kinds = resolve_decommission_review_kinds(
        auto_reclaim_kinds=config.auto_reclaim_kinds,
        configured_review_kinds=config.decommission_review_kinds,
        observed_kinds=observed_kinds,
    )

    results: list[ComponentReclaimResult] = []
    pending_reviews = list_pending_decommission_reviews(records, name=name, kind=kind)
    if pending_reviews:
        if not github_token:
            for record in pending_reviews:
                results.append(
                    ComponentReclaimResult(
                        name=record.name,
                        kind=record.kind,
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
                            f"Skipped registry finalize for `{record.name}`; "
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
                except ComponentReclaimError as exc:
                    _append_result_on_error(
                        results,
                        record,
                        mode=MODE_REGISTRY_FINALIZE,
                        exc=exc,
                    )

    auto_expired = list_expired_components(
        records,
        reclaim_kinds=auto_reclaim_kinds,
        now=now,
        name=name,
        kind=kind,
    )
    review_expired = list_expired_components_for_decommission_review(
        records,
        auto_reclaim_kinds=auto_reclaim_kinds,
        review_kinds=review_kinds,
        now=now,
        name=name,
        kind=kind,
    )

    for record in auto_expired:
        try:
            results.append(
                reclaim_component(
                    record,
                    repo_root=repo_root,
                    registry_path=config.file,
                    base_branch=config.base_branch,
                    github_token=github_token,
                    dry_run=dry_run,
                )
            )
        except ComponentReclaimError as exc:
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
        except ComponentReclaimError as exc:
            _append_result_on_error(
                results,
                record,
                mode=MODE_DECOMMISSION_REVIEW,
                exc=exc,
            )

    if name and not auto_expired and not review_expired:
        _validate_name_filter(
            name=name,
            kind=kind,
            records=records,
            auto_reclaim_kinds=auto_reclaim_kinds,
            review_kinds=review_kinds,
            now=now,
        )
    return ComponentReclaimSummary(results=tuple(results))
