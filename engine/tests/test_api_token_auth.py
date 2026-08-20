from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from license_helpers import install_repave_license
from repave_engine.api import create_app


@pytest.fixture
def service_mode_with_api_token(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_API_TOKEN", "service-token")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{tmp_path}/repave.sqlite")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    install_repave_license(monkeypatch, tmp_path)


def test_api_token_allows_v2_fleet_read(
    service_mode_with_api_token,
    repo_root,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    unauth = client.get("/api/v2/fleet")
    assert unauth.status_code == 401

    authed = client.get(
        "/api/v2/fleet",
        headers={"Authorization": "Bearer service-token"},
    )
    assert authed.status_code in (200, 404)


def test_api_token_allows_environment_reclaim_dry_run(
    service_mode_with_api_token,
    repo_root,
    output_config,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_ENVIRONMENT_VENDING", "1")
    monkeypatch.setenv("REPAVE_ENVIRONMENT_REGISTRY_FILE", str(registry))
    (repo_root / "repave.config.yaml").write_text(
        "environment_vending:\n  enabled: true\n  gitops_repo: https://github.com/acme/gitops\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.post(
        "/api/v2/environments/reclaim",
        headers={"Authorization": "Bearer service-token"},
        json={"dry_run": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 0


def test_api_token_allows_v1_generate_auth(
    service_mode_with_api_token,
    repo_root,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/api/v1/generate",
        headers={"Authorization": "Bearer service-token"},
        json={"blueprint": "terraform-module-generic", "dry_run": True, "inputs": {}},
    )
    assert response.status_code != 401
    assert response.status_code in (200, 400)


def test_combined_app_state_backend_accepts_basic_auth(
    service_mode_with_api_token,
    repo_root,
    output_config,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import base64

    monkeypatch.setenv("REPAVE_STATE_STORE_URL", f"sqlite:///{tmp_path}/state.db")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    encoded = base64.b64encode(b"terraform:service-token").decode()
    response = client.get(
        "/api/state/v1/backend/acme/prod",
        headers={"Authorization": f"Basic {encoded}"},
    )
    assert response.status_code != 401
    if response.status_code == 404:
        assert response.json()["detail"] == "state not found"
    else:
        assert response.status_code == 200


def test_invalid_api_token_returns_401(
    service_mode_with_api_token,
    repo_root,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get(
        "/api/v2/fleet",
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
