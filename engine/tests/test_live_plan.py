from __future__ import annotations

import json
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.entity_catalog import entity_id_for_repo_url
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.gates import GateResult
from repave_engine.live_plan import (
    LIVE_PLAN_BLUEPRINT_SENTINEL,
    LivePlanSummary,
    run_live_plan,
    summarize_plan_json,
)
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.run_submit import submit_async_run
from repave_engine.settings import OutputConfig, load_live_plan_config


def test_summarize_plan_json_counts_actions() -> None:
    payload = {
        "resource_changes": [
            {"change": {"actions": ["create"]}},
            {"change": {"actions": ["update"]}},
            {"change": {"actions": ["delete"]}},
            {"change": {"actions": ["create", "delete"]}},
            {"change": {"actions": ["no-op"]}},
        ]
    }
    assert summarize_plan_json(payload) == (2, 1, 2)


def test_load_live_plan_config(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
live_plan:
  enabled: true
  policies_dir: policy/opa/policies
  environments:
    svc-a:
      target: /tmp/mod-a
      secret_name: tf-creds-a
    "*":
      target: /tmp/default
""",
        encoding="utf-8",
    )
    config = load_live_plan_config(tmp_path)
    assert config is not None
    assert config.enabled
    env = config.environment_for("svc-a")
    assert env is not None
    assert env.target == "/tmp/mod-a"
    assert env.secret_name == "tf-creds-a"
    fallback = config.environment_for("other")
    assert fallback is not None
    assert fallback.target == "/tmp/default"


def test_run_live_plan_scrubs_artifacts_and_omits_raw_json(tmp_path: Path) -> None:
    module = tmp_path / "module"
    module.mkdir()
    (module / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")

    def fake_plan(output_dir: Path, plan_subdir: str, *, use_backend: bool = True) -> Path:
        del use_backend
        work = output_dir / plan_subdir
        work.mkdir(parents=True, exist_ok=True)
        path = work / "tfplan.json"
        path.write_text(
            json.dumps({"resource_changes": [{"change": {"actions": ["create"]}}]}),
            encoding="utf-8",
        )
        return path

    @contextmanager
    def fake_materialize(target: str):
        del target
        yield module

    with (
        patch("repave_engine.live_plan.materialize_upgrade_target", side_effect=fake_materialize),
        patch("repave_engine.live_plan.terraform_live_plan_json", side_effect=fake_plan),
        patch(
            "repave_engine.live_plan.run_conftest_on_plan",
            return_value=GateResult("opa", True, False, "conftest passed"),
        ),
    ):
        summary = run_live_plan(
            repo_root=tmp_path,
            target=str(module),
            entity_id="svc-a",
            use_backend=False,
        )

    assert summary.plan_ok
    assert summary.opa_passed
    assert summary.resource_add == 1
    public = summary.to_public_dict()
    dumped = json.dumps(public)
    assert "resource_changes" not in dumped
    assert "tfplan" not in dumped
    assert not (module / ".repave" / "live-plan").exists()


def test_submit_and_queue_live_plan(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        """
live_plan:
  enabled: true
  environments:
    entity-1:
      target: /tmp/mod
      secret_name: env-secret
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
    fake = LivePlanSummary(
        entity_id="entity-1",
        target="/tmp/mod",
        plan_ok=True,
        opa_passed=True,
        opa_skipped=False,
        opa_detail="conftest passed",
        resource_add=1,
        resource_change=0,
        resource_destroy=0,
        detail="Plan: +1 ~0 -0; OPA passed",
    )
    with patch("repave_engine.run_queue.run_live_plan", return_value=fake):
        record = submit_async_run(
            queue,
            payload={"kind": "live_plan", "entity_id": "entity-1"},
            acting_user="tester",
            repo_root=tmp_path,
        )
        assert record.blueprint_name == LIVE_PLAN_BLUEPRINT_SENTINEL
        assert record.payload["kind"] == "live_plan"
        assert record.payload["live_plan_secret_name"] == "env-secret"
        public = record.to_public_dict()
        assert public["kind"] == "live_plan"
        assert public["entity_id"] == "entity-1"
        assert "blueprint" not in public

        deadline = time.time() + 5.0
        terminal = None
        while time.time() < deadline:
            terminal = store.get(record.run_id)
            if terminal and terminal.status == RunStatus.SUCCEEDED:
                break
            time.sleep(0.05)
        assert terminal is not None
        assert terminal.result is not None
        assert terminal.result["gates_outcome"] == "passed"
        assert "resource_changes" not in terminal.result
    queue.close()


def test_api_v2_live_plan_submit(tmp_path: Path, output_config, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    (tmp_path / "repave.config.yaml").write_text(
        """
durability:
  async_generation: true
live_plan:
  enabled: true
  environments:
    entity-api:
      target: /tmp/mod
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    fake = LivePlanSummary(
        entity_id="entity-api",
        target="/tmp/mod",
        plan_ok=True,
        opa_passed=False,
        opa_skipped=False,
        opa_detail="denied",
        resource_add=0,
        resource_change=1,
        resource_destroy=0,
        detail="OPA failed",
    )
    try:
        with patch("repave_engine.run_queue.run_live_plan", return_value=fake):
            response = client.post(
                "/api/v2/runs",
                json={"kind": "live_plan", "entity_id": "entity-api"},
            )
            assert response.status_code == 202
            body = response.json()
            assert body["kind"] == "live_plan"
            run_id = body["run_id"]
            deadline = time.time() + 5.0
            while time.time() < deadline:
                poll = client.get(f"/api/v2/runs/{run_id}")
                assert poll.status_code == 200
                if poll.json()["status"] == "succeeded":
                    assert poll.json()["result"]["gates_outcome"] == "failed"
                    return
                time.sleep(0.05)
            pytest.fail("live_plan run did not complete")
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()


def test_service_detail_live_plan_button(tmp_path: Path, output_config, monkeypatch) -> None:
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
    (tmp_path / "repave.config.yaml").write_text(
        f"""
fleet:
  enabled: true
  file: {registry}
durability:
  async_generation: true
live_plan:
  enabled: true
  environments:
    "{entity_id}":
      target: /tmp/mod
""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    try:
        detail = client.get(f"/services/{entity_id}")
        assert detail.status_code == 200
        assert "Plan against live state" in detail.text
        with patch(
            "repave_engine.run_queue.run_live_plan",
            return_value=LivePlanSummary(
                entity_id=entity_id,
                target="/tmp/mod",
                plan_ok=True,
                opa_passed=True,
                opa_skipped=False,
                opa_detail="ok",
                resource_add=0,
                resource_change=0,
                resource_destroy=0,
                detail="ok",
            ),
        ):
            response = client.post(
                f"/services/{entity_id}/live-plan",
                follow_redirects=False,
            )
        assert response.status_code == 303
        assert response.headers["location"].startswith("/runs/")
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close()
