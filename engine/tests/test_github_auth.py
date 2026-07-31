from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from repave_engine.github_auth import (
    GitHubAppConfig,
    clear_installation_token_cache,
    fetch_installation_token,
    github_credentials_configured,
    load_github_app_config,
    mint_app_jwt,
    resolve_github_access_token,
)


def _test_private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


@pytest.fixture(autouse=True)
def _clear_token_cache() -> None:
    clear_installation_token_cache()


def test_load_github_app_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = _test_private_key_pem()
    monkeypatch.setenv("GITHUB_APP_ID", "12345")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "67890")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem.replace("\n", "\\n"))

    config = load_github_app_config()
    assert config is not None
    assert config.app_id == "12345"
    assert config.installation_id == "67890"
    assert "BEGIN RSA PRIVATE KEY" in config.private_key_pem


def test_pat_precedence_over_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_pat")
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _test_private_key_pem())

    assert resolve_github_access_token() == "ghp_pat"


def test_explicit_token_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_pat")
    assert resolve_github_access_token("ghp_explicit") == "ghp_explicit"


def test_mint_app_jwt_contains_app_id() -> None:
    pem = _test_private_key_pem()
    config = GitHubAppConfig(app_id="42", installation_id="99", private_key_pem=pem)
    token = mint_app_jwt(config)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == "42"


def test_fetch_installation_token_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = _test_private_key_pem()
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "42")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "99")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", pem)
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        assert request.method == "POST"
        assert request.url.path.endswith("/app/installations/99/access_tokens")
        expires = (
            (datetime.now(tz=timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        )
        return httpx.Response(201, json={"token": "ghs_installation", "expires_at": expires})

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "repave_engine.github_auth.httpx.post",
        lambda url, **kwargs: httpx.Client(transport=transport).post(url, **kwargs),
    )

    first = resolve_github_access_token()
    second = resolve_github_access_token()
    assert first == "ghs_installation"
    assert second == "ghs_installation"
    assert calls["count"] == 1


def test_github_credentials_configured_with_app_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", _test_private_key_pem())
    assert github_credentials_configured() is True


def test_fetch_installation_token_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    pem = _test_private_key_pem()
    config = GitHubAppConfig(app_id="42", installation_id="99", private_key_pem=pem)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, content=b"not-json")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        "repave_engine.github_auth.httpx.post",
        lambda url, **kwargs: httpx.Client(transport=transport).post(url, **kwargs),
    )

    with pytest.raises(json.JSONDecodeError):
        fetch_installation_token(config)
