"""HTTP helpers for /api/v2 upgrade endpoints (remote repo_url + optional push)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from repave_engine.git_clone import CloneError, ephemeral_clone, is_http_remote, resolve_git_token
from repave_engine.github import push_git_branch
from repave_engine.target_repo import resolve_module_repository_from_git
from repave_engine.upgrade_plan import (
    ApplyUpgradeResult,
    UpgradePlanResult,
    apply_upgrade,
    plan_upgrade,
)


class UpgradeTargetError(ValueError):
    """Invalid upgrade target_repo / repo_url input."""


def resolve_upgrade_target(*, target_repo: str, repo_url: str | None = None) -> str:
    """Return the filesystem path or remote URL to use for an upgrade."""
    url = (repo_url or "").strip()
    if url:
        return url
    path = target_repo.strip()
    if not path:
        raise UpgradeTargetError("target_repo or repo_url is required")
    return path


@contextmanager
def materialize_upgrade_target(target: str) -> Iterator[Path]:
    """Yield a local checkout path, cloning remotes into a temp directory."""
    if is_http_remote(target):
        try:
            with ephemeral_clone(target, token=resolve_git_token()) as checkout:
                yield checkout
        except CloneError as exc:
            raise UpgradeTargetError(str(exc)) from exc
        return
    yield Path(target)


def run_plan_upgrade(
    *,
    repo_root: Path,
    target: str,
    blueprint_name: str | None,
    staging_root: Path | None,
) -> UpgradePlanResult:
    with materialize_upgrade_target(target) as checkout:
        return plan_upgrade(
            checkout,
            repo_root,
            blueprint_name=blueprint_name,
            staging_root=staging_root,
        )


def run_apply_upgrade(
    *,
    repo_root: Path,
    target: str,
    blueprint_name: str | None,
    staging_root: Path | None,
    git_branch: str,
    commit_message: str,
    preserve_local: bool,
    push: bool,
) -> tuple[ApplyUpgradeResult, bool]:
    """Apply an upgrade; optionally push when target is a remote URL."""
    pushed = False
    with materialize_upgrade_target(target) as checkout:
        result = apply_upgrade(
            checkout,
            repo_root,
            blueprint_name=blueprint_name,
            staging_root=staging_root,
            git_branch=git_branch,
            commit_message=commit_message,
            preserve_local=preserve_local,
        )
        if push:
            if not is_http_remote(target):
                raise UpgradeTargetError("push requires repo_url or an http(s) target")
            token = resolve_git_token()
            if not token:
                raise UpgradeTargetError("GITHUB_TOKEN is required to push after apply")
            repository = resolve_module_repository_from_git(checkout)
            push_git_branch(
                checkout,
                owner=repository.owner,
                name=repository.name,
                token=token,
                branch=git_branch,
            )
            pushed = True
    return result, pushed
