from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.environment_vend import (
    EnvironmentVendResult,
    build_environment_vend_pull_request_body,
    build_environment_vend_pull_request_title,
    is_environment_vend_run,
    resolve_vend_request_fields,
)
from repave_engine.gates import GateResult
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
