"""Service-mode auth enforcement over HTTP.

`enforce_service_auth` reads `request.session`, so SessionMiddleware must sit outside it.
Starlette runs the most recently added middleware outermost, which makes registration
order load-bearing: with SessionMiddleware added first, every authenticated path raised
`AssertionError: SessionMiddleware must be installed` and returned 500 instead of 401.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from license_helpers import install_repave_license
from repave_engine.api import create_app


@pytest.fixture
def service_mode(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_DATABASE_URL", f"sqlite:///{tmp_path}/repave.sqlite")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    install_repave_license(monkeypatch, tmp_path)


def test_api_paths_return_401_not_500(service_mode, repo_root, output_config) -> None:
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
    )

    assert client.post("/api/v1/generate", json={}).status_code == 401


def test_portal_root_is_public_landing(service_mode, repo_root, output_config) -> None:
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
        follow_redirects=False,
    )

    response = client.get("/")

    assert response.status_code == 200
    assert "Create account" in response.text
    assert "Sign in" in response.text
    assert "The intelligent platform layer" in response.text
    assert "What the platform does" in response.text
    assert "Gates that block" in response.text
    assert "Hosted catalog" in response.text
    assert "Who it is for" in response.text
    assert "shell__nav--primary" not in response.text
    assert "data-surface-moved" not in response.text
    assert 'href="/auth/login"' in response.text
    assert 'href="/signup"' in response.text


def test_signup_page_is_public(service_mode, repo_root, output_config) -> None:
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
        follow_redirects=False,
    )

    response = client.get("/signup")

    assert response.status_code == 200
    assert "Create an account" in response.text
    assert 'href="/auth/signup"' in response.text
    assert 'href="/auth/login"' in response.text
    assert "data-surface-moved" not in response.text


def test_protected_portal_paths_redirect_to_login(service_mode, repo_root, output_config) -> None:
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
        follow_redirects=False,
    )

    response = client.get("/library")

    assert response.status_code == 302
    assert response.headers["location"] == "/auth/login?next=/library"


def test_public_paths_stay_open(service_mode, repo_root, output_config) -> None:
    client = TestClient(
        create_app(repo_root=repo_root, output_config=output_config),
        raise_server_exceptions=False,
    )

    assert client.get("/health").status_code == 200
    pricing = client.get("/pricing")
    assert pricing.status_code == 200
    assert "Request a license" in pricing.text


def test_session_available_without_service_mode(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    assert client.get("/health").status_code == 200
    assert client.get("/").status_code == 200
