from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.entity_catalog import entity_id_for_repo_url
from repave_engine.environment_vend import (
    EnvironmentVendResult,
    build_environment_vend_pull_request_body,
    build_environment_vend_pull_request_title,
    is_environment_vend_run,
    resolve_vend_request_fields,
)
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.gates import GateResult
from repave_engine.portal_context import build_portal_catalog_entities
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.run_submit import submit_async_run
from repave_engine.settings import (
    EnvironmentVendingConfig,
    OutputConfig,
    load_environment_vending_config,
)


def test_load_environment_vending_config(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/platform-gitops
  base_branch: main
  path_prefix: clusters/dev
""",
        encoding="utf-8",
    )
    config = load_environment_vending_config(tmp_path)
    assert config is not None
    assert config.gitops_repo == "https://github.com/acme/platform-gitops"
    assert config.path_prefix == "clusters/dev"
    assert config.file == tmp_path / "data" / "environments" / "registry.jsonl"


def test_resolve_vend_request_fields_uses_config_defaults(tmp_path: Path) -> None:
    config = EnvironmentVendingConfig(
        enabled=True,
        gitops_repo="https://github.com/acme/gitops",
        base_branch="main",
        path_prefix="environments",
    )
    blueprint, repo, path, owner, env_class, base, dry_run = resolve_vend_request_fields(
        {
            "kind": "environment_vend",
            "inputs": {
                "stack_name": "sandbox-alice",
                "description": "Alice sandbox",
                "cloud_provider": "aws",
                "environment": "dev",
            },
            "owner": "team-platform",
        },
        config,
    )
    assert blueprint == "terraform-environment-stack"
    assert repo == "https://github.com/acme/gitops"
    assert path == "environments/sandbox-alice"
    assert owner == "team-platform"
    assert env_class == "sandbox"
    assert base == "main"
    assert dry_run is False


def test_resolve_vend_request_fields_requires_stack_name() -> None:
    config = EnvironmentVendingConfig(enabled=True)
    with pytest.raises(ValueError, match="stack_name"):
        resolve_vend_request_fields({"kind": "environment_vend", "inputs": {}}, config)


def test_is_environment_vend_run() -> None:
    assert is_environment_vend_run({"kind": "environment_vend"})
    assert not is_environment_vend_run({"kind": "live_plan"})


def test_build_environment_vend_pull_request_title() -> None:
    title = build_environment_vend_pull_request_title(
        stack_name="sandbox-alice",
        environment="dev",
        cloud_provider="aws",
    )
    assert "sandbox-alice" in title
    assert "dev" in title


def test_build_environment_vend_pull_request_body_includes_evidence(repo_root: Path) -> None:
    body = build_environment_vend_pull_request_body(
        stack_name="sandbox-alice",
        environment="dev",
        cloud_provider="aws",
        gitops_path="environments/sandbox-alice",
        owner="team-platform",
        env_class="sandbox",
        blueprint_name="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates=(
            GateResult(name="checkov", passed=True, skipped=False, message="ok"),
            GateResult(name="opa", passed=False, skipped=False, message="deny"),
        ),
        repo_root=repo_root,
    )
    assert "terraform apply" in body
    assert "Gate evidence" in body
    assert "`opa` (failed)" in body


def test_submit_environment_vend_queues_run(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  path_prefix: environments
""",
        encoding="utf-8",
    )
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake = EnvironmentVendResult(
        kind="environment_vend",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        owner="team-platform",
        env_class="sandbox",
        pull_request_url="https://github.com/acme/gitops/pull/7",
        pull_request_number=7,
        draft=False,
        detail="Opened pull request",
    )
    with patch("repave_engine.run_queue.run_environment_vend", return_value=fake):
        record = submit_async_run(
            queue,
            payload={
                "kind": "environment_vend",
                "dry_run": True,
                "inputs": {
                    "stack_name": "sandbox-alice",
                    "description": "Alice sandbox",
                    "cloud_provider": "aws",
                    "environment": "dev",
                },
                "owner": "team-platform",
            },
            acting_user="tester",
            repo_root=tmp_path,
        )
        assert record.payload["kind"] == "environment_vend"
        assert record.payload["blueprint"] == "terraform-environment-stack"
        assert record.payload["gitops_path"] == "environments/sandbox-alice"

        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(record.run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.result is not None
        assert terminal.result["pull_request_url"] == fake.pull_request_url
    queue.close()


def test_vend_run_registers_environment_record(tmp_path: Path) -> None:
    registry = tmp_path / "data" / "environments" / "registry.jsonl"
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  path_prefix: environments
  ttl_hours_by_class:
    sandbox: 168
""",
        encoding="utf-8",
    )
    store = RunStore(tmp_path / "runs.sqlite")
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4),
    )
    fake = EnvironmentVendResult(
        kind="environment_vend",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        owner="team-platform",
        env_class="sandbox",
        pull_request_url="https://github.com/acme/gitops/pull/7",
        pull_request_number=7,
        draft=False,
        detail="Opened pull request",
    )
    with patch("repave_engine.run_queue.run_environment_vend", return_value=fake):
        record = submit_async_run(
            queue,
            payload={
                "kind": "environment_vend",
                "dry_run": False,
                "inputs": {
                    "stack_name": "sandbox-alice",
                    "description": "Alice sandbox",
                    "cloud_provider": "aws",
                    "environment": "dev",
                },
                "owner": "team-platform",
                "class": "sandbox",
            },
            acting_user="tester",
            repo_root=tmp_path,
        )
        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(record.run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.result is not None
        assert terminal.result.get("catalog_entity_id") == "env-aws-sandbox-alice"
    from repave_engine.environment_registry import read_environments

    entries = read_environments(registry)
    assert len(entries) == 1
    assert entries[0].stack_name == "sandbox-alice"
    assert entries[0].expires_at
    queue.close()


def test_portal_catalog_includes_vended_environment(tmp_path: Path, output_config) -> None:
    registry = tmp_path / "data" / "environments" / "registry.jsonl"
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
""",
        encoding="utf-8",
    )
    from repave_engine.environment_record import EnvironmentRecord
    from repave_engine.environment_registry import register_environment

    register_environment(
        registry,
        EnvironmentRecord(
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
            vended_at="2026-08-02T12:00:00+00:00",
            expires_at="",
            status="active",
        ),
    )
    entities = build_portal_catalog_entities(
        tmp_path,
        output_config,
        cost_actuals_configured=False,
    )
    match = [item for item in entities if item.entity_id == "env-aws-sandbox-alice"]
    assert len(match) == 1
    assert match[0].source == "environment"


def _link_vend_test_repo(tmp_path: Path, repo_root: Path) -> None:
    for name in ("blueprints", "policy", "standards", "schemas"):
        src = repo_root / name
        if src.is_dir():
            dest = tmp_path / name
            if not dest.exists():
                dest.symlink_to(src, target_is_directory=True)


def test_service_detail_environment_vend_form(
    tmp_path: Path, output_config, repo_root: Path, monkeypatch
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    registry = tmp_path / "registry.jsonl"
    entry = FleetEntry(
        repo_url="https://github.com/acme/tf-live",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.9.0",
        standard_source="standards/terraform-standards",
        standard_version="1.1.0",
        owner="platform",
        registered_by="tester@example.com",
    )
    register_repo(registry, entry)
    entity_id = entity_id_for_repo_url(entry.repo_url)
    entity_dir = output_config.modules_root / "tf-live"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    _link_vend_test_repo(tmp_path, repo_root)
    (tmp_path / "repave.config.yaml").write_text(
        f"""
fleet:
  enabled: true
  file: {registry}
durability:
  async_generation: true
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  path_prefix: environments
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    try:
        detail = client.get(f"/services/{entity_id}")
        assert_surface_moved(detail, "services")
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()


def test_service_request_environment_preview(
    tmp_path: Path, output_config, repo_root: Path, monkeypatch
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    registry = tmp_path / "registry.jsonl"
    entry = FleetEntry(
        repo_url="https://github.com/acme/tf-live",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.9.0",
        standard_source="standards/terraform-standards",
        standard_version="1.1.0",
        owner="platform",
        registered_by="tester@example.com",
    )
    register_repo(registry, entry)
    entity_id = entity_id_for_repo_url(entry.repo_url)
    entity_dir = output_config.modules_root / "tf-live"
    entity_dir.mkdir(parents=True)
    (entity_dir / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    _link_vend_test_repo(tmp_path, repo_root)
    (tmp_path / "repave.config.yaml").write_text(
        f"""
fleet:
  enabled: true
  file: {registry}
durability:
  async_generation: true
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
  path_prefix: environments
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    fake = EnvironmentVendResult(
        kind="environment_vend",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        owner="platform",
        env_class="sandbox",
        pull_request_url="",
        pull_request_number=0,
        draft=False,
        detail="Dry-run: gates evaluated; GitOps PR not opened.",
    )
    try:
        with patch("repave_engine.run_queue.run_environment_vend", return_value=fake):
            response = client.post(
                f"/services/{entity_id}/request-environment",
                data={
                    "action": "preview",
                    "stack_name": "sandbox-alice",
                    "description": "Alice sandbox",
                    "cloud_provider": "aws",
                    "environment": "dev",
                    "owner": "platform",
                    "class": "sandbox",
                },
                follow_redirects=False,
            )
            assert response.status_code == 303
            run_url = response.headers["location"]
            assert run_url.startswith("/runs/")
            console = client.get(run_url)
            assert console.status_code == 200
            assert "data-environment-vend" in console.text
            assert "Environment stack vend" in console.text

            run_id = run_url.rstrip("/").split("/")[-1]
            deadline = time.time() + 5.0
            while time.time() < deadline:
                result_page = client.get(f"/runs/{run_id}/result")
                if result_page.status_code == 200:
                    break
                time.sleep(0.05)
            assert result_page.status_code == 200
            assert "Environment vend" in result_page.text
            assert "Gate preview complete" in result_page.text
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()
