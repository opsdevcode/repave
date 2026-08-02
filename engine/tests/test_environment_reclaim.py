from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.environment_reclaim import (
    MODE_AUTO_RECLAIM,
    MODE_DECOMMISSION_REVIEW,
    EnvironmentReclaimError,
    build_environment_reclaim_pull_request_title,
    list_expired_environments,
    list_expired_environments_for_decommission_review,
    reclaim_environment,
    reclaim_expired_environments,
    request_decommission_review,
)
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
    register_environment,
)
from repave_engine.settings import EnvironmentVendingConfig, load_environment_vending_config


def _record(**overrides: object) -> EnvironmentRecord:
    base = EnvironmentRecord(
        stack_name="sandbox-alice",
        entity_id="env-aws-sandbox-alice",
        cloud_provider="aws",
        environment_tier="dev",
        owner="platform",
        env_class="sandbox",
        blueprint_name="terraform-environment-stack",
        blueprint_version="0.4.0",
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        pull_request_url="https://github.com/acme/gitops/pull/7",
        pull_request_number=7,
        gates_outcome="passed",
        source_entity_id="acme-tf-live",
        run_id="run-1",
        vended_by="tester",
        vended_at="2026-08-01T12:00:00+00:00",
        expires_at="2026-08-02T11:00:00+00:00",
        status="active",
    )
    return EnvironmentRecord(**{**base.__dict__, **overrides})


def test_is_environment_expired_requires_expires_at() -> None:
    record = _record(expires_at="")
    assert is_environment_expired(record) is False


def test_is_environment_expired_past_ttl() -> None:
    record = _record(expires_at="2020-01-01T00:00:00+00:00")
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    assert is_environment_expired(record, now=now) is True


def test_is_reclaim_eligible_class() -> None:
    classes = frozenset({"sandbox"})
    assert is_reclaim_eligible_class("sandbox", classes) is True
    assert is_reclaim_eligible_class("prod", classes) is False


def test_list_expired_environments_filters_class_and_ttl() -> None:
    expired_sandbox = _record(
        stack_name="sandbox-old",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    fresh_sandbox = _record(
        stack_name="sandbox-new",
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    expired_prod = _record(
        stack_name="prod-old",
        env_class="prod",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    expired = list_expired_environments(
        (expired_sandbox, fresh_sandbox, expired_prod),
        reclaim_classes=frozenset({"sandbox"}),
        now=now,
    )
    assert [item.stack_name for item in expired] == ["sandbox-old"]


def test_decommission_removes_environment_from_registry(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_environment(registry, record)
    assert len(read_environments(registry)) == 1
    decommission_environment(registry, record)
    assert read_environments(registry) == ()


def test_build_environment_reclaim_pull_request_title() -> None:
    title = build_environment_reclaim_pull_request_title(
        stack_name="sandbox-alice",
        env_class="sandbox",
    )
    assert "sandbox-alice" in title
    assert "reclaim" in title


def test_reclaim_environment_dry_run(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_environment(registry, record)
    result = reclaim_environment(
        record,
        repo_root=repo_root,
        registry_path=registry,
        base_branch="main",
        github_token=None,
        dry_run=True,
    )
    assert result.reclaimed is False
    assert "Dry-run" in result.detail
    assert len(read_environments(registry)) == 1


def test_reclaim_expired_environments_dry_run(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_environment(registry, _record())
    config = EnvironmentVendingConfig(
        enabled=True,
        gitops_repo="https://github.com/acme/gitops",
        file=registry,
        auto_reclaim_classes=("sandbox",),
    )
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    summary = reclaim_expired_environments(
        repo_root=repo_root,
        config=config,
        github_token=None,
        dry_run=True,
        now=now,
    )
    assert len(summary.results) == 1
    assert "Dry-run" in summary.results[0].detail
    assert len(read_environments(registry)) == 1


def test_reclaim_environment_opens_pr_and_decommissions(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_environment(registry, record)

    work = tmp_path / "work"
    gitops_root = work / "gitops"
    (gitops_root / "environments" / "sandbox-alice").mkdir(parents=True)

    class _Repo:
        owner = "acme"
        name = "gitops"
        web_url = "https://github.com/acme/gitops"

    with (
        patch(
            "repave_engine.environment_reclaim.tempfile.TemporaryDirectory",
            return_value=_FakeTempDir(work),
        ),
        patch("repave_engine.environment_reclaim.shallow_clone"),
        patch("repave_engine.environment_reclaim.preflight_import") as preflight,
        patch("repave_engine.environment_reclaim._commit_gitops_tree", return_value=True),
        patch(
            "repave_engine.environment_reclaim.resolve_module_repository_from_git",
            return_value=_Repo(),
        ),
        patch("repave_engine.environment_reclaim.push_import_branch"),
        patch(
            "repave_engine.environment_reclaim.create_github_pull_request",
            return_value={"number": 42, "html_url": "https://github.com/acme/gitops/pull/42"},
        ),
        patch("repave_engine.environment_reclaim.add_pull_request_labels"),
        patch("repave_engine.environment_reclaim.shutil.rmtree"),
    ):
        preflight.return_value = type(
            "Preflight",
            (),
            {"has_existing_pull_request": False, "base_branch": "main"},
        )()
        result = reclaim_environment(
            record,
            repo_root=repo_root,
            registry_path=registry,
            base_branch="main",
            github_token="gh-test",
            dry_run=False,
        )

    assert result.reclaimed is True
    assert result.mode == MODE_AUTO_RECLAIM
    assert result.pull_request_number == 42
    assert read_environments(registry) == ()


class _FakeTempDir:
    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, *args: object) -> None:
        return None


def test_reclaim_missing_gitops_path_decommissions_without_pr(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_environment(registry, record)

    work = tmp_path / "work"
    (work / "gitops").mkdir(parents=True)

    with (
        patch(
            "repave_engine.environment_reclaim.tempfile.TemporaryDirectory",
            return_value=_FakeTempDir(work),
        ),
        patch("repave_engine.environment_reclaim.shallow_clone"),
        patch("repave_engine.environment_reclaim.preflight_import") as preflight,
    ):
        preflight.return_value = type(
            "Preflight",
            (),
            {"has_existing_pull_request": False, "base_branch": "main"},
        )()
        result = reclaim_environment(
            record,
            repo_root=repo_root,
            registry_path=registry,
            base_branch="main",
            github_token="gh-test",
            dry_run=False,
        )

    assert result.reclaimed is True
    assert result.pull_request_number == 0
    assert "already absent" in result.detail
    assert read_environments(registry) == ()


def test_reclaim_single_stack_not_registered_raises(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    config = EnvironmentVendingConfig(enabled=True, file=registry)
    with pytest.raises(EnvironmentReclaimError, match="not registered"):
        reclaim_expired_environments(
            repo_root=repo_root,
            config=config,
            github_token=None,
            dry_run=True,
            stack_name="missing-stack",
        )


def test_load_environment_vending_config_auto_reclaim_classes(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  auto_reclaim_classes:
    - sandbox
    - dev
""",
        encoding="utf-8",
    )
    config = load_environment_vending_config(tmp_path)
    assert config is not None
    assert config.auto_reclaim_classes == ("sandbox", "dev")


def test_resolve_decommission_review_classes_defaults_to_non_auto() -> None:
    classes = resolve_decommission_review_classes(
        auto_reclaim_classes=("sandbox",),
        configured_review_classes=(),
        observed_classes=frozenset({"sandbox", "prod", "staging"}),
    )
    assert classes == frozenset({"prod", "staging"})


def test_has_open_decommission_review() -> None:
    assert has_open_decommission_review(_record(status="expired", pull_request_number=9))
    assert not has_open_decommission_review(_record(status="active", pull_request_number=9))


def test_list_expired_environments_for_decommission_review_skips_open_pr() -> None:
    expired_prod = _record(
        stack_name="prod-old",
        env_class="prod",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    expired_with_pr = _record(
        stack_name="prod-reviewed",
        env_class="prod",
        expires_at="2020-01-01T00:00:00+00:00",
        status="expired",
        pull_request_number=55,
    )
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    eligible = list_expired_environments_for_decommission_review(
        (expired_prod, expired_with_pr),
        auto_reclaim_classes=frozenset({"sandbox"}),
        review_classes=frozenset({"prod"}),
        now=now,
    )
    assert [item.stack_name for item in eligible] == ["prod-old"]


def test_request_decommission_review_opens_draft_and_keeps_registry(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record(
        stack_name="prod-app",
        entity_id="env-aws-prod-app",
        env_class="prod",
        gitops_path="environments/prod-app",
    )
    register_environment(registry, record)

    work = tmp_path / "work"
    (work / "gitops" / "environments" / "prod-app").mkdir(parents=True)

    class _Repo:
        owner = "acme"
        name = "gitops"
        web_url = "https://github.com/acme/gitops"

    with (
        patch(
            "repave_engine.environment_reclaim.tempfile.TemporaryDirectory",
            return_value=_FakeTempDir(work),
        ),
        patch("repave_engine.environment_reclaim.shallow_clone"),
        patch("repave_engine.environment_reclaim.preflight_import") as preflight,
        patch("repave_engine.environment_reclaim._commit_gitops_tree", return_value=True),
        patch(
            "repave_engine.environment_reclaim.resolve_module_repository_from_git",
            return_value=_Repo(),
        ),
        patch("repave_engine.environment_reclaim.push_import_branch"),
        patch(
            "repave_engine.environment_reclaim.create_github_pull_request",
            return_value={"number": 99, "html_url": "https://github.com/acme/gitops/pull/99"},
        ) as create_pr,
        patch("repave_engine.environment_reclaim.add_pull_request_labels"),
        patch("repave_engine.environment_reclaim.shutil.rmtree"),
    ):
        preflight.return_value = type(
            "Preflight",
            (),
            {"has_existing_pull_request": False, "base_branch": "main"},
        )()
        result = request_decommission_review(
            record,
            repo_root=repo_root,
            registry_path=registry,
            base_branch="main",
            github_token="gh-test",
            dry_run=False,
        )

    assert result.mode == MODE_DECOMMISSION_REVIEW
    assert result.reclaimed is False
    assert result.draft is True
    assert result.pull_request_number == 99
    create_pr.assert_called_once()
    assert create_pr.call_args.kwargs["draft"] is True
    entries = read_environments(registry)
    assert len(entries) == 1
    assert entries[0].status == "expired"
    assert entries[0].pull_request_number == 99


def test_reclaim_expired_environments_processes_prod_review_dry_run(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    register_environment(
        registry,
        _record(
            stack_name="prod-app",
            entity_id="env-aws-prod-app",
            env_class="prod",
            gitops_path="environments/prod-app",
        ),
    )
    config = EnvironmentVendingConfig(
        enabled=True,
        gitops_repo="https://github.com/acme/gitops",
        file=registry,
        auto_reclaim_classes=("sandbox",),
        decommission_review_classes=("prod",),
    )
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    summary = reclaim_expired_environments(
        repo_root=repo_root,
        config=config,
        github_token=None,
        dry_run=True,
        now=now,
    )
    assert len(summary.results) == 1
    assert summary.results[0].mode == MODE_DECOMMISSION_REVIEW
    assert summary.results[0].draft is True
    assert read_environments(registry)[0].status == "active"


def test_mark_environment_expired_updates_registry(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record(env_class="prod")
    register_environment(registry, record)
    mark_environment_expired(
        registry,
        record,
        pull_request_url="https://github.com/acme/gitops/pull/99",
        pull_request_number=99,
        git_branch="repave/environment-reclaim/prod-app-reclaim",
    )
    entry = read_environments(registry)[0]
    assert entry.status == "expired"
    assert entry.pull_request_number == 99
