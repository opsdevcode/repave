from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.fleet import FleetEntry, register_repo
from repave_engine.fleet_operator_status import (
    FleetOperatorStatus,
    write_operator_status_snapshot,
)

PROVENANCE_ENTRY = FleetEntry(
    repo_url="https://github.com/acme/tf-vpc",
    blueprint_name="terraform-module-generic",
    blueprint_version="0.9.0",
    standard_source="standards/terraform-standards",
    standard_version="1.1.0",
    owner="platform",
    registered_by="tester@example.com",
)


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(path))
    return path


def test_fleet_page_shows_operator_phase(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, PROVENANCE_ENTRY)
    status_file = tmp_path / "operator-status.json"
    write_operator_status_snapshot(
        status_file,
        [
            FleetOperatorStatus(
                repo_url=PROVENANCE_ENTRY.repo_url,
                phase="OutOfDate",
                message="pins differ",
            )
        ],
    )
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n  operator_status_file: {status_file}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    body = client.get("/fleet").text

    assert "operator OutOfDate" in body
    assert "pins differ" in body
    assert "GitOps sync" in body


def test_fleet_page_lists_registered_repos(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/fleet")

    assert response.status_code == 200
    body = response.text
    assert "https://github.com/acme/tf-vpc" in body
    assert "terraform-module-generic@0.9.0" in body
    assert "standard 1.1.0" in body
    assert "platform" in body
    assert "1 repository" in body


def test_fleet_page_pluralizes_count(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    register_repo(
        registry,
        FleetEntry(
            repo_url="https://github.com/acme/tf-subnet",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
        ),
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert "2 repositories" in client.get("/fleet").text


def test_fleet_page_empty_state_points_at_register(
    repo_root, output_config, registry: Path
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/fleet")

    assert response.status_code == 200
    assert "No repositories are registered yet" in response.text
    assert "repave register" in response.text


def test_fleet_page_explains_unconfigured_registry(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_FLEET_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    response = client.get("/fleet")

    assert response.status_code == 200
    assert "repave.config.yaml" in response.text


def test_fleet_page_survives_invalid_fleet_config(
    repo_root, output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_FLEET_FILE", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "repave.config.yaml").write_text("fleet: not-a-mapping\n", encoding="utf-8")

    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    assert client.get("/fleet").status_code == 200


def test_nav_exposes_fleet_link(repo_root, output_config, registry: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/").text

    assert 'href="/fleet"' in body
    assert "Fleet" in body


def test_fleet_page_marks_nav_current(repo_root, output_config, registry: Path) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/fleet").text

    assert 'href="/fleet" aria-current="page"' in body
