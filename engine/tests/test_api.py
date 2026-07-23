from __future__ import annotations

from fastapi.testclient import TestClient

from repave_engine.api import create_app


def test_health(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_lists_blueprints(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")

    assert response.status_code == 200
    assert "terraform-module-generic" in response.text


def test_generate_form_submission(
    repo_root,
    output_config,
    sample_inputs,
    monkeypatch,
) -> None:
    monkeypatch.setenv("REPAVE_GITHUB_ORG", output_config.github_org)
    monkeypatch.setenv("REPAVE_MODULES_ROOT", str(output_config.modules_root))

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            **sample_inputs,
        },
    )

    assert response.status_code == 200
    assert "tf-aws-example" in response.text
    assert "Dry-run" in response.text
