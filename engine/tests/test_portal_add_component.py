from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.entity_catalog import entity_id_for_repo_url
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.provenance import write_provenance_file
from repave_engine.render import render_blueprint


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _seed_app_service(repo_root: Path, entity_dir: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "service_name": "checkout-api",
            "description": "Checkout HTTP API",
            "owner": "team:payments",
            "port": "8080",
            "runtime": "python",
            "include_helm_reference": "false",
        },
        repo_root=repo_root,
    )
    render_blueprint(blueprint, values, entity_dir)
    write_provenance_file(entity_dir, blueprint, values, filename="repave.yaml")
    _init_git(entity_dir)


def test_service_detail_shows_add_component_form(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    entry = FleetEntry(
        repo_url="https://github.com/acme/checkout-api",
        blueprint_name="app-service-generic",
        blueprint_version="0.4.1",
        standard_source="standards/app-service",
        standard_version="1.0.0",
        owner="team:payments",
        registered_by="tester@example.com",
    )
    register_repo(registry, entry)
    entity_dir = output_config.modules_root / "checkout-api"
    entity_dir.mkdir(parents=True)
    _seed_app_service(repo_root, entity_dir)
    entity_id = entity_id_for_repo_url(entry.repo_url)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get(f"/services/{entity_id}").text

    assert "Add component" in body
    assert "helm-chart-generic" in body
    assert "Primary" in body
    assert "app-service-generic" in body


def test_service_add_component_plan_redirect(
    repo_root: Path,
    output_config,
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    entry = FleetEntry(
        repo_url="https://github.com/acme/checkout-api",
        blueprint_name="app-service-generic",
        blueprint_version="0.4.1",
        standard_source="standards/app-service",
        standard_version="1.0.0",
        owner="team:payments",
        registered_by="tester@example.com",
    )
    register_repo(registry, entry)
    entity_dir = output_config.modules_root / "checkout-api"
    entity_dir.mkdir(parents=True)
    _seed_app_service(repo_root, entity_dir)
    entity_id = entity_id_for_repo_url(entry.repo_url)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.post(
        f"/services/{entity_id}/add-component",
        data={"blueprint": "helm-chart-generic", "action": "plan"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "add_status=ok" in response.headers["location"]
    follow = client.get(response.headers["location"])
    assert "Chart.yaml" in follow.text or "file(s) to add" in follow.text
