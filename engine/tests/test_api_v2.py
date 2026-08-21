from __future__ import annotations

import shutil
import time
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.github_repo_provision import OrgTeam
from repave_engine.org_import_scan import OrgScanResult, ScannedRepository


def test_api_v2_metadata(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2")

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_version"] == "v2"
    assert "engine_version" in payload
    assert "POST /api/v2/upgrades/plan" in payload["endpoints"]
    assert "POST /api/v2/runs" in payload["endpoints"]
    assert "GET /api/v2/runs" in payload["endpoints"]
    assert "GET /api/v2/audit" in payload["endpoints"]
    assert "GET /api/v2/estate" in payload["endpoints"]
    assert "GET /api/v2/governance/annotations/{blueprint_name}" in payload["endpoints"]
    assert "GET /api/v2/github/teams" in payload["endpoints"]
    assert "GET /api/v2/github/teams/{slug}/members" in payload["endpoints"]
    assert "POST /api/v2/github/org-scan" in payload["endpoints"]
    assert "GET /api/v2/fleet" in payload["endpoints"]
    assert "GET /api/v2/platform/metrics" in payload["endpoints"]
    assert "GET /api/v2/platform/compliance" in payload["endpoints"]
    assert "GET /api/v2/platform/value-stream" in payload["endpoints"]
    assert "GET /api/v2/platform/roadmap-evidence" in payload["endpoints"]
    assert "GET /api/v2/platform/feedback" in payload["endpoints"]
    assert "GET /api/v2/platform/finops/export" in payload["endpoints"]
    assert "POST /api/v2/platform/feedback" in payload["endpoints"]
    assert "GET /api/v2/platform/ops" in payload["endpoints"]
    assert "GET /api/v2/platform/standards" in payload["endpoints"]
    assert "GET /api/v2/platform/campaigns" in payload["endpoints"]
    assert "POST /api/v2/platform/campaigns/{namespace}/{name}/paused" in payload["endpoints"]
    assert "GET /api/v2/deployment-sets" in payload["endpoints"]
    assert "POST /api/v2/environments/vend" in payload["endpoints"]
    assert "GET /api/v2/component-kinds" in payload["endpoints"]
    assert "POST /api/v2/components/vend" in payload["endpoints"]
    assert "POST /api/v2/components/reclaim" in payload["endpoints"]
    assert "GET /api/v2/catalog/blueprints" in payload["endpoints"]
    assert "POST /api/v2/assistant/resolve" in payload["endpoints"]
    assert "POST /api/v2/assistant/confirm" in payload["endpoints"]
    assert "GET /api/v2/bundles" in payload["endpoints"]
    assert "GET /api/v2/bundles/{name}" in payload["endpoints"]
    assert "GET /api/v2/library" in payload["endpoints"]


def test_api_v2_upgrades_plan(repo_root, output_config, tmp_path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v2/upgrades/plan",
        json={
            "target_repo": str(fixture),
            "staging_root": str(tmp_path / "staging"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["blueprint_name"] == "terraform-module-generic"
    assert payload["changed_file_count"] > 0
    assert "summary" in payload
    assert "added" in payload
    assert "modified" in payload
    assert "removed" in payload


def test_api_v2_upgrades_plan_requires_target_repo(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/api/v2/upgrades/plan", json={})

    assert response.status_code == 400
    assert "target_repo" in response.json()["detail"]


@pytest.fixture
def async_v2_client(repo_root, output_config, monkeypatch, tmp_path):
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "test-v2-runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    yield client
    queue = client.app.state.run_queue
    if queue is not None:
        queue.close()


def test_api_v2_runs_submit(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_v2_client.post(
            "/api/v2/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"v2-api-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            poll = async_v2_client.get(f"/api/v2/runs/{run_id}")
            assert poll.status_code == 200
            if poll.json()["status"] == "succeeded":
                assert poll.json()["result"]["gates_outcome"] == "passed"
                return
            time.sleep(0.05)
        pytest.fail("v2 run did not complete")


def test_api_v2_runs_list_filters_by_status(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        submit = async_v2_client.post(
            "/api/v2/runs",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "client_request_id": f"v2-list-{uuid.uuid4()}",
            },
        )
        assert submit.status_code == 202
        run_id = submit.json()["run_id"]
        deadline = time.time() + 5.0
        while time.time() < deadline:
            listed = async_v2_client.get("/api/v2/runs?status=succeeded&limit=10")
            assert listed.status_code == 200
            runs = listed.json()["runs"]
            if any(item["run_id"] == run_id for item in runs):
                return
            time.sleep(0.05)
        pytest.fail("v2 run did not appear in succeeded list")


def test_api_v2_generate_async_matches_runs(async_v2_client) -> None:
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": "/tmp/out",
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        response = async_v2_client.post(
            "/api/v2/generate",
            json={
                "blueprint": "terraform-module-generic",
                "inputs": {"module_name": "demo"},
                "dry_run": True,
                "async": True,
                "client_request_id": f"v2-gen-{uuid.uuid4()}",
            },
        )
        assert response.status_code in (200, 202)
        assert "run_id" in response.json()


def test_api_v2_github_org_scan(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    with patch(
        "repave_engine.api_v2.router.scan_github_org",
        return_value=OrgScanResult(
            org="acme",
            listed=2,
            limit=100,
            truncated=False,
            discovery_mode="search",
            search_query="org:acme language:HCL archived:false fork:false",
            repos=(
                ScannedRepository(
                    url="https://github.com/acme/vpc",
                    owner="acme",
                    name="vpc",
                    governed=False,
                    classification_error=None,
                    top_candidate=None,
                ),
            ),
        ),
    ) as scanned:
        response = client.post(
            "/api/v2/github/org-scan",
            json={"org": "acme", "families": ["terraform"]},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["org"] == "acme"
    assert body["listed"] == 2
    assert len(body["repos"]) == 1
    scanned.assert_called_once()


def test_api_v2_github_org_scan_requires_org(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/api/v2/github/org-scan", json={})
    assert response.status_code == 400
    assert "org is required" in response.json()["detail"]


def test_api_v2_github_teams(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    with patch(
        "repave_engine.api_v2.router.list_org_teams",
        return_value=(OrgTeam(slug="platform", name="Platform", description="ops"),),
    ) as listed:
        response = client.get("/api/v2/github/teams")
    assert response.status_code == 200
    body = response.json()
    assert body["org"] == output_config.github_org
    assert body["teams"] == [
        {"slug": "platform", "name": "Platform", "description": "ops"},
    ]
    listed.assert_called_once()


def test_api_v2_github_teams_requires_token(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_APP_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_INSTALLATION_ID", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("GITHUB_APP_PRIVATE_KEY_FILE", raising=False)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    with patch("repave_engine.api_v2.router.resolve_github_access_token", return_value=None):
        response = client.get("/api/v2/github/teams")
    assert response.status_code == 503
    assert "GitHub credentials" in response.json()["detail"]


def test_api_v2_github_team_members(repo_root, output_config, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    with patch(
        "repave_engine.api_v2.router.list_team_members",
        return_value=("alice", "bob"),
    ) as listed:
        response = client.get("/api/v2/github/teams/platform/members")
    assert response.status_code == 200
    body = response.json()
    assert body["org"] == output_config.github_org
    assert body["team"] == "platform"
    assert body["members"] == ["alice", "bob"]
    assert body["count"] == 2
    listed.assert_called_once()
    assert listed.call_args.args[0] == output_config.github_org
    assert listed.call_args.args[1] == "platform"


def test_api_v2_deployment_sets_empty_without_catalog(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/deployment-sets")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0
    assert body["deployment_sets"] == []
    assert body["vend_available"] is False


def test_api_v2_deployment_sets_lists_lab_catalog(
    repo_root, output_config, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "workspace"
    shutil.copytree(repo_root / "examples" / "platform-dev", root / "examples" / "platform-dev")
    (root / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  developer_lab:\n    enabled: true\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(root)
    client = TestClient(create_app(repo_root=root, output_config=output_config))
    response = client.get("/api/v2/deployment-sets")
    assert response.status_code == 200
    body = response.json()
    assert body["developer_lab"] is True
    assert body["count"] >= 1
    ids = {item["id"] for item in body["deployment_sets"]}
    assert "api-sandbox-7d" in ids
    assert body["vend_available"] is False


def test_api_v2_environments_vend_queues_run(
    repo_root, output_config, tmp_path, monkeypatch
) -> None:
    from repave_engine.environment_vend import EnvironmentVendResult

    root = tmp_path / "workspace"
    shutil.copytree(repo_root / "examples" / "platform-dev", root / "examples" / "platform-dev")
    (root / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  developer_lab:\n    enabled: true\n"
        "durability:\n  async_generation: true\n"
        "environment_vending:\n  enabled: true\n"
        "  gitops_repo: https://github.com/acme/gitops\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "vend-runs.sqlite"))
    monkeypatch.chdir(root)
    fake = EnvironmentVendResult(
        kind="environment_vend",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/my-feature-sandbox",
        git_branch="repave/environment/my-feature-sandbox-dev",
        owner="group:platform",
        env_class="sandbox",
        pull_request_url="",
        pull_request_number=0,
        draft=False,
        detail="Plan only",
    )
    client = TestClient(create_app(repo_root=root, output_config=output_config))
    try:
        with patch("repave_engine.run_queue.run_environment_vend", return_value=fake):
            response = client.post(
                "/api/v2/environments/vend",
                json={
                    "deployment_set": "api-sandbox-7d",
                    "stack_name": "my-feature-sandbox",
                    "owner": "group:platform",
                    "dry_run": True,
                },
            )
        assert response.status_code == 202
        body = response.json()
        assert body["kind"] == "environment_vend"
        assert "run_id" in body
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close(wait=False)


def test_api_v2_environments_vend_rejects_unknown_set(
    repo_root, output_config, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "workspace"
    shutil.copytree(repo_root / "examples" / "platform-dev", root / "examples" / "platform-dev")
    (root / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  developer_lab:\n    enabled: true\n"
        "durability:\n  async_generation: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "vend-bad.sqlite"))
    monkeypatch.chdir(root)
    client = TestClient(create_app(repo_root=root, output_config=output_config))
    try:
        response = client.post(
            "/api/v2/environments/vend",
            json={
                "deployment_set": "missing",
                "stack_name": "my-feature-sandbox",
            },
        )
        assert response.status_code == 400
        assert "Unknown deployment set" in response.json()["detail"]
    finally:
        queue = client.app.state.run_queue
        if queue is not None:
            queue.close(wait=False)


def test_api_v2_catalog_blueprints_groups_families(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/catalog/blueprints")

    assert response.status_code == 200
    payload = response.json()
    names = [blueprint["name"] for group in payload["groups"] for blueprint in group["blueprints"]]
    assert payload["count"] == len(names)
    assert "terraform-module-generic" in names
    terraform = next(group for group in payload["groups"] if group["family"] == "terraform")
    assert terraform["title"]
    assert terraform["blueprints"][0]["artifact_type"]
    generic = next(
        item for item in terraform["blueprints"] if item["name"] == "terraform-module-generic"
    )
    input_names = [field["name"] for field in generic["inputs"]]
    assert "cloud_provider" in input_names
    assert "module_name" in input_names
    cloud = next(field for field in generic["inputs"] if field["name"] == "cloud_provider")
    assert cloud["required"] is True
    assert "aws" in cloud["enum"]


def test_api_v2_bundles_list_and_detail(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    listed = client.get("/api/v2/bundles")

    assert listed.status_code == 200
    names = [item["name"] for item in listed.json()["bundles"]]
    assert "service-stack" in names
    assert listed.json()["count"] == len(names)

    detail = client.get("/api/v2/bundles/service-stack")
    assert detail.status_code == 200
    body = detail.json()
    assert body["name"] == "service-stack"
    assert body["members"]
    assert body["topology"]["nodes"]
    assert client.get("/api/v2/bundles/missing-bundle").status_code == 404


def test_api_v2_library_groups_and_unknown_family(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/api/v2/library")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entity_count"] == sum(group["count"] for group in payload["groups"])
    assert "scorecard" in payload
    assert payload["family"] is None

    terraform = client.get("/api/v2/library?family=terraform")
    assert terraform.status_code == 200
    assert terraform.json()["family"] == "terraform"

    unknown = client.get("/api/v2/library?family=not-a-family")
    assert unknown.status_code == 404
    assert "unknown library family" in unknown.json()["detail"]
