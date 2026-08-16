from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.component_kinds import builtin_component_kinds, find_component_kind
from repave_engine.component_record import ComponentRecord, entity_id_for_component
from repave_engine.component_registry import read_components, register_component
from repave_engine.component_vend import (
    ComponentVendResult,
    build_component_vend_pull_request_title,
    is_component_vend_run,
    resolve_component_vend_fields,
)
from repave_engine.portal_context import build_portal_catalog_entities
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.run_submit import submit_async_run
from repave_engine.settings import (
    ComponentVendingConfig,
    OutputConfig,
    load_component_vending_config,
)


def test_builtin_component_kinds() -> None:
    kinds = builtin_component_kinds()
    assert {item.id for item in kinds} == {"database", "bucket", "queue"}
    assert find_component_kind(kinds, "database") is not None


def test_load_component_vending_config(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/platform-gitops
  path_prefix: managed
""",
        encoding="utf-8",
    )
    config = load_component_vending_config(tmp_path)
    assert config is not None
    assert config.gitops_repo == "https://github.com/acme/platform-gitops"
    assert config.path_prefix == "managed"
    assert config.file == tmp_path / "data" / "components" / "registry.jsonl"


def test_component_vending_falls_back_to_environment_gitops(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
environment_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
component_vending:
  enabled: true
""",
        encoding="utf-8",
    )
    config = load_component_vending_config(tmp_path)
    assert config is not None
    assert config.gitops_repo == "https://github.com/acme/gitops"


def test_resolve_component_vend_fields() -> None:
    config = ComponentVendingConfig(
        enabled=True,
        gitops_repo="https://github.com/acme/gitops",
        path_prefix="components",
    )
    kind, name, repo, path, owner, _base, dry_run, inputs = resolve_component_vend_fields(
        {
            "kind": "database",
            "name": "checkout-db",
            "owner": "team-checkout",
            "dry_run": True,
        },
        config,
        builtin_component_kinds(),
    )
    assert kind.id == "database"
    assert name == "checkout-db"
    assert repo == "https://github.com/acme/gitops"
    assert path == "components/database/checkout-db"
    assert owner == "team-checkout"
    assert dry_run is True
    assert inputs["stack_name"] == "checkout-db"
    assert inputs["component_kind"] == "database"


def test_resolve_component_vend_fields_rejects_unknown_kind() -> None:
    config = ComponentVendingConfig(enabled=True)
    try:
        resolve_component_vend_fields(
            {"kind": "cache", "name": "checkout-cache"},
            config,
            builtin_component_kinds(),
        )
    except ValueError as exc:
        assert "unknown component kind" in str(exc)
    else:
        raise AssertionError("expected ComponentVendError")


def test_is_component_vend_run() -> None:
    assert is_component_vend_run({"kind": "component_vend"})
    assert not is_component_vend_run({"kind": "environment_vend"})


def test_build_component_vend_pull_request_title() -> None:
    title = build_component_vend_pull_request_title(
        kind="database", name="checkout-db", environment="dev"
    )
    assert "checkout-db" in title
    assert "database" in title


def test_submit_component_vend_queues_run(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
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
    fake = ComponentVendResult(
        kind="database",
        name="checkout-db",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="components/database/checkout-db",
        git_branch="repave/component/checkout-db",
        owner="team-checkout",
        pull_request_url="https://github.com/acme/gitops/pull/9",
        pull_request_number=9,
        draft=False,
        detail="Opened pull request",
    )
    with patch("repave_engine.run_queue.run_component_vend", return_value=fake):
        record = submit_async_run(
            queue,
            payload={
                "kind": "component_vend",
                "component_kind": "database",
                "name": "checkout-db",
                "owner": "team-checkout",
                "dry_run": True,
            },
            acting_user="tester",
            repo_root=tmp_path,
        )
        assert record.payload["kind"] == "component_vend"
        assert record.payload["component_kind"] == "database"
        assert record.payload["gitops_path"] == "components/database/checkout-db"
        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(record.run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.result is not None
        assert terminal.result["component_kind"] == "database"
    queue.close()


def test_vend_run_registers_component_record(tmp_path: Path) -> None:
    registry = tmp_path / "data" / "components" / "registry.jsonl"
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
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
    fake = ComponentVendResult(
        kind="bucket",
        name="checkout-assets",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="components/bucket/checkout-assets",
        git_branch="repave/component/checkout-assets",
        owner="team-checkout",
        pull_request_url="https://github.com/acme/gitops/pull/11",
        pull_request_number=11,
        draft=False,
        detail="Opened pull request",
    )
    with patch("repave_engine.run_queue.run_component_vend", return_value=fake):
        record = submit_async_run(
            queue,
            payload={
                "kind": "component_vend",
                "component_kind": "bucket",
                "name": "checkout-assets",
                "owner": "team-checkout",
                "dry_run": False,
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
        assert terminal.result.get("catalog_entity_id") == "cmp-bucket-checkout-assets"
    entries = read_components(registry)
    assert len(entries) == 1
    assert entries[0].name == "checkout-assets"
    assert entries[0].kind == "bucket"
    queue.close()


def test_portal_catalog_includes_vended_component(tmp_path: Path, output_config) -> None:
    registry = tmp_path / "data" / "components" / "registry.jsonl"
    (tmp_path / "repave.config.yaml").write_text(
        """
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
""",
        encoding="utf-8",
    )
    register_component(
        registry,
        ComponentRecord(
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
            vended_at="2026-08-16T12:00:00+00:00",
            status="active",
        ),
    )
    entities = build_portal_catalog_entities(
        tmp_path,
        output_config,
        cost_actuals_configured=False,
    )
    match = [item for item in entities if item.entity_id == "cmp-database-checkout-db"]
    assert len(match) == 1
    assert match[0].source == "component"
    assert match[0].to_public_dict()["component"]["kind"] == "database"


def test_api_v2_component_kinds_and_vend(tmp_path: Path, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    (tmp_path / "repave.config.yaml").write_text(
        """
durability:
  async_generation: true
component_vending:
  enabled: true
  gitops_repo: https://github.com/acme/gitops
""",
        encoding="utf-8",
    )
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    kinds = client.get("/api/v2/component-kinds")
    assert kinds.status_code == 200
    body = kinds.json()
    assert body["count"] == 3
    assert {item["id"] for item in body["kinds"]} == {"database", "bucket", "queue"}

    fake = ComponentVendResult(
        kind="queue",
        name="checkout-jobs",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="components/queue/checkout-jobs",
        git_branch="repave/component/checkout-jobs",
        owner="team-checkout",
        pull_request_url="",
        pull_request_number=0,
        draft=False,
        detail="Dry-run",
    )
    try:
        with patch("repave_engine.run_queue.run_component_vend", return_value=fake):
            response = client.post(
                "/api/v2/components/vend",
                json={"kind": "queue", "name": "checkout-jobs", "owner": "team-checkout"},
            )
        assert response.status_code == 202
        body = response.json()
        assert body["kind"] == "component_vend"
        assert body["dry_run"] is True
        assert body["stack_name"] == "checkout-jobs"
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()
