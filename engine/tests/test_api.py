from __future__ import annotations

from fastapi.testclient import TestClient

from repave_engine.api import create_app


def test_health(repo_root) -> None:
    client = TestClient(create_app(repo_root=repo_root))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_lists_blueprints(repo_root) -> None:
    client = TestClient(create_app(repo_root=repo_root))
    response = client.get("/")

    assert response.status_code == 200
    assert "terraform-module-generic" in response.text


def test_blueprint_form(repo_root) -> None:
    client = TestClient(create_app(repo_root=repo_root))
    response = client.get("/blueprints/terraform-module-generic")

    assert response.status_code == 200
    assert "module_name" in response.text


def test_generate_form_submission(repo_root, sample_inputs) -> None:
    client = TestClient(create_app(repo_root=repo_root))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert "example" in response.text
    assert "Dry-run" in response.text
