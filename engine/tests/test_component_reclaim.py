from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.component_reclaim import (
    MODE_AUTO_RECLAIM,
    MODE_DECOMMISSION_REVIEW,
    ComponentReclaimError,
    build_component_reclaim_pull_request_title,
    list_expired_components,
    list_expired_components_for_decommission_review,
    reclaim_component,
    reclaim_expired_components,
    request_decommission_review,
)
from repave_engine.component_record import (
    ComponentRecord,
    entity_id_for_component,
    has_open_decommission_review,
    is_component_expired,
    is_reclaim_eligible_kind,
    resolve_decommission_review_kinds,
)
from repave_engine.component_registry import (
    decommission_component,
    read_components,
    register_component,
)
from repave_engine.settings import ComponentVendingConfig, load_component_vending_config


def _record(**overrides: object) -> ComponentRecord:
    base = ComponentRecord(
        name="checkout-db",
        kind="database",
        entity_id=entity_id_for_component(kind="database", name="checkout-db"),
        cloud_provider="aws",
        environment_tier="dev",
        owner="platform",
        blueprint_name="terraform-environment-stack",
        blueprint_version="0.4.0",
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="components/database/checkout-db",
        git_branch="repave/component/checkout-db",
        pull_request_url="https://github.com/acme/gitops/pull/9",
        pull_request_number=9,
        gates_outcome="passed",
        run_id="run-1",
        vended_by="tester",
        vended_at="2026-08-01T12:00:00+00:00",
        status="active",
        expires_at="2026-08-02T11:00:00+00:00",
    )
    return ComponentRecord(**{**base.__dict__, **overrides})


def test_is_component_expired_requires_expires_at() -> None:
    assert is_component_expired(_record(expires_at="")) is False


def test_is_component_expired_past_ttl() -> None:
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    assert is_component_expired(_record(expires_at="2020-01-01T00:00:00+00:00"), now=now) is True


def test_is_reclaim_eligible_kind() -> None:
    kinds = frozenset({"database", "bucket"})
    assert is_reclaim_eligible_kind("database", kinds) is True
    assert is_reclaim_eligible_kind("queue", kinds) is False


def test_list_expired_components_filters_kind_and_ttl() -> None:
    expired_db = _record(name="old-db", expires_at="2020-01-01T00:00:00+00:00")
    fresh_db = _record(
        name="new-db",
        entity_id="cmp-database-new-db",
        expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    )
    expired_queue = _record(
        name="old-jobs",
        kind="queue",
        entity_id="cmp-queue-old-jobs",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    expired = list_expired_components(
        (expired_db, fresh_db, expired_queue),
        reclaim_kinds=frozenset({"database"}),
        now=now,
    )
    assert [item.name for item in expired] == ["old-db"]


def test_decommission_removes_component_from_registry(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_component(registry, record)
    assert len(read_components(registry)) == 1
    decommission_component(registry, record)
    assert read_components(registry) == ()


def test_build_component_reclaim_pull_request_title() -> None:
    title = build_component_reclaim_pull_request_title(kind="database", name="checkout-db")
    assert "checkout-db" in title
    assert "reclaim" in title


def test_reclaim_component_dry_run(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_component(registry, record)
    result = reclaim_component(
        record,
        repo_root=repo_root,
        registry_path=registry,
        base_branch="main",
        github_token=None,
        dry_run=True,
    )
    assert result.reclaimed is False
    assert "Dry-run" in result.detail
    assert len(read_components(registry)) == 1


def test_reclaim_expired_components_dry_run(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_component(registry, _record())
    config = ComponentVendingConfig(
        enabled=True,
        gitops_repo="https://github.com/acme/gitops",
        file=registry,
        auto_reclaim_kinds=("database",),
    )
    now = datetime(2026, 8, 3, tzinfo=timezone.utc)
    summary = reclaim_expired_components(
        repo_root=repo_root,
        config=config,
        github_token=None,
        dry_run=True,
        now=now,
    )
    assert len(summary.results) == 1
    assert "Dry-run" in summary.results[0].detail
    assert len(read_components(registry)) == 1


class _FakeTempDir:
    def __init__(self, path: Path) -> None:
        self._path = path

    def __enter__(self) -> str:
        return str(self._path)

    def __exit__(self, *args: object) -> None:
        return None


def test_reclaim_component_opens_pr_and_decommissions(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_component(registry, record)

    work = tmp_path / "work"
    gitops_root = work / "gitops"
    (gitops_root / "components" / "database" / "checkout-db").mkdir(parents=True)

    class _Repo:
        owner = "acme"
        name = "gitops"
        web_url = "https://github.com/acme/gitops"

    with (
        patch(
            "repave_engine.component_reclaim.tempfile.TemporaryDirectory",
            return_value=_FakeTempDir(work),
        ),
        patch("repave_engine.component_reclaim.shallow_clone"),
        patch("repave_engine.component_reclaim.preflight_import") as preflight,
        patch("repave_engine.component_reclaim._commit_gitops_tree", return_value=True),
        patch(
            "repave_engine.component_reclaim.resolve_module_repository_from_git",
            return_value=_Repo(),
        ),
        patch("repave_engine.component_reclaim.push_import_branch"),
        patch(
            "repave_engine.component_reclaim.create_github_pull_request",
            return_value={"number": 42, "html_url": "https://github.com/acme/gitops/pull/42"},
        ),
        patch("repave_engine.component_reclaim.add_pull_request_labels"),
        patch("repave_engine.component_reclaim.shutil.rmtree"),
    ):
        preflight.return_value = type(
            "Preflight",
            (),
            {"has_existing_pull_request": False, "base_branch": "main"},
        )()
        result = reclaim_component(
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
    assert read_components(registry) == ()


def test_reclaim_missing_gitops_path_decommissions_without_pr(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record()
    register_component(registry, record)

    work = tmp_path / "work"
    (work / "gitops").mkdir(parents=True)

    with (
        patch(
            "repave_engine.component_reclaim.tempfile.TemporaryDirectory",
            return_value=_FakeTempDir(work),
        ),
        patch("repave_engine.component_reclaim.shallow_clone"),
        patch("repave_engine.component_reclaim.preflight_import") as preflight,
    ):
        preflight.return_value = type(
            "Preflight",
            (),
            {"has_existing_pull_request": False, "base_branch": "main"},
        )()
        result = reclaim_component(
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
    assert read_components(registry) == ()


def test_reclaim_named_component_not_registered_raises(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    config = ComponentVendingConfig(enabled=True, file=registry)
    with pytest.raises(ComponentReclaimError, match="not registered"):
        reclaim_expired_components(
            repo_root=repo_root,
            config=config,
            github_token=None,
            dry_run=True,
            name="missing-db",
        )


def test_load_component_vending_config_reclaim_kinds(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  default_ttl_hours: 168
  ttl_hours_by_kind:
    database: 72
  auto_reclaim_kinds:
    - bucket
    - queue
  decommission_review_kinds:
    - database
""",
        encoding="utf-8",
    )
    config = load_component_vending_config(tmp_path)
    assert config is not None
    assert config.default_ttl_hours == 168
    assert config.ttl_hours_by_kind == (("database", 72),)
    assert config.auto_reclaim_kinds == ("bucket", "queue")
    assert config.decommission_review_kinds == ("database",)


def test_resolve_decommission_review_kinds_defaults_to_non_auto() -> None:
    kinds = resolve_decommission_review_kinds(
        auto_reclaim_kinds=("database", "bucket", "queue"),
        configured_review_kinds=(),
        observed_kinds=frozenset({"database", "cache"}),
    )
    assert kinds == frozenset({"cache"})


def test_has_open_decommission_review() -> None:
    assert has_open_decommission_review(_record(status="expired", pull_request_number=9))
    assert not has_open_decommission_review(_record(status="active", pull_request_number=9))


def test_list_expired_components_for_decommission_review_skips_open_pr() -> None:
    expired = _record(
        name="prod-db",
        kind="cache",
        entity_id="cmp-cache-prod-db",
        expires_at="2020-01-01T00:00:00+00:00",
    )
    expired_with_pr = _record(
        name="prod-reviewed",
        kind="cache",
        entity_id="cmp-cache-prod-reviewed",
        expires_at="2020-01-01T00:00:00+00:00",
        status="expired",
        pull_request_number=55,
    )
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    eligible = list_expired_components_for_decommission_review(
        (expired, expired_with_pr),
        auto_reclaim_kinds=frozenset({"database"}),
        review_kinds=frozenset({"cache"}),
        now=now,
    )
    assert [item.name for item in eligible] == ["prod-db"]


def test_request_decommission_review_dry_run(repo_root: Path, tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = _record(kind="cache", entity_id="cmp-cache-checkout-db")
    register_component(registry, record)
    result = request_decommission_review(
        record,
        repo_root=repo_root,
        registry_path=registry,
        base_branch="main",
        github_token=None,
        dry_run=True,
    )
    assert result.mode == MODE_DECOMMISSION_REVIEW
    assert result.draft is True
    assert result.reclaimed is False
    assert len(read_components(registry)) == 1


def test_api_v2_components_reclaim_dry_run(tmp_path: Path, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_COMPONENT_VENDING", "1")
    monkeypatch.setenv("REPAVE_COMPONENT_REGISTRY_FILE", str(tmp_path / "registry.jsonl"))
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  default_ttl_hours: 1
""",
        encoding="utf-8",
    )
    register_component(tmp_path / "registry.jsonl", _record())
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    response = client.post("/api/v2/components/reclaim", json={"dry_run": True})
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["results"][0]["name"] == "checkout-db"
    assert "Dry-run" in body["results"][0]["detail"]
    assert len(read_components(tmp_path / "registry.jsonl")) == 1


def test_api_v2_components_reclaim_requires_vending(tmp_path: Path, output_config) -> None:
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    response = client.post("/api/v2/components/reclaim", json={"dry_run": True})
    assert response.status_code == 503
    assert "component_vending" in response.json()["detail"]
