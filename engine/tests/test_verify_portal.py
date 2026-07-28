from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app


def test_verify_form_page(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/verify")

    assert response.status_code == 200
    assert "Verify existing repository" in response.text
    assert 'name="target_repo"' in response.text
    assert "Verify repo" in response.text


def test_verify_post_on_fixture(
    repo_root,
    output_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/verify", data={"target_repo": str(fixture)})

    assert response.status_code == 200
    assert "Verify report" in response.text
    assert "Pin drift vs catalog" in response.text
    assert "gate-table" in response.text


def test_api_verify_json(
    repo_root,
    output_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: False,
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v1/verify",
        json={"path": str(fixture)},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert body["pins_aligned"] is False
    assert len(body["pin_changes"]) >= 1
    assert "gates" in body


def test_api_verify_rejects_remote_url(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v1/verify",
        json={"path": "https://github.com/acme/mod"},
    )
    assert response.status_code == 400
    assert "clone locally" in response.json()["detail"]


def test_nav_exposes_verify_link(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/").text
    assert 'href="/verify"' in body
    assert "Verify repo" in body
