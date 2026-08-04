from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    AuthConfig,
    build_idp_logout_url,
    groups_from_claims,
    logout_return_to,
    role_for_groups,
)
from repave_engine.settings import load_portal_config


def _auth_config(
    *,
    oidc_issuer: str = "https://idp.example.com",
    groups_claim: str = "groups",
    oidc_logout_return_to: str = "",
    session_https_only: bool = True,
) -> AuthConfig:
    return AuthConfig(
        service_enabled=True,
        session_secret="secret",
        api_token="",
        oidc_issuer=oidc_issuer,
        oidc_client_id="client",
        oidc_client_secret="sec",
        oidc_redirect_uri="https://repave.example.com/auth/callback",
        oidc_scopes=("openid", "profile", "email"),
        groups_claim=groups_claim,
        admin_groups=frozenset({"repave-admins"}),
        generator_groups=frozenset({"repave-generators"}),
        session_https_only=session_https_only,
        oidc_logout_return_to=oidc_logout_return_to,
    )


def test_load_portal_config_compact(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  density: compact\n", encoding="utf-8")
    cfg = load_portal_config(tmp_path)
    assert cfg.density == "compact"


def test_load_portal_config_invalid_density(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  density: wide\n", encoding="utf-8")
    with pytest.raises(ValueError, match="density"):
        load_portal_config(tmp_path)


def test_load_portal_config_observability_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  observability_dashboard_url: https://from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_OBSERVABILITY_DASHBOARD_URL", "https://from-env")
    cfg = load_portal_config(tmp_path)
    assert cfg.observability_dashboard_url == "https://from-env"


def test_load_auth_config_reads_api_token_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repave_engine.settings import load_auth_config

    (tmp_path / "repave.config.yaml").write_text("auth:\n  service_mode: true\n", encoding="utf-8")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "secret")
    monkeypatch.setenv("REPAVE_API_TOKEN", "service-token")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    cfg = load_auth_config(tmp_path)
    assert cfg is not None
    assert cfg.api_token == "service-token"
    assert cfg.session_https_only is True


def test_load_auth_config_session_https_only_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repave_engine.settings import load_auth_config

    (tmp_path / "repave.config.yaml").write_text("auth:\n  service_mode: true\n", encoding="utf-8")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    monkeypatch.setenv("REPAVE_SESSION_HTTPS_ONLY", "0")

    cfg = load_auth_config(tmp_path)
    assert cfg is not None
    assert cfg.session_https_only is False


def test_load_auth_config_session_https_only_from_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from repave_engine.settings import load_auth_config

    (tmp_path / "repave.config.yaml").write_text(
        "auth:\n  service_mode: true\n  session_https_only: false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    cfg = load_auth_config(tmp_path)
    assert cfg is not None
    assert cfg.session_https_only is False


def test_role_for_groups() -> None:
    config = _auth_config()
    assert role_for_groups(["repave-admins"], config) == ROLE_ADMIN
    assert role_for_groups(["repave-generators"], config) == ROLE_GENERATOR
    assert role_for_groups(["other"], config) == "viewer"


def test_groups_from_claims_auth0_namespaced() -> None:
    claim = "https://repave.opsdevcode/groups"
    claims = {
        "sub": "auth0|abc",
        "email": "user@example.com",
        claim: ["repave-admins", "repave-generators"],
    }
    groups = groups_from_claims(claims, claim)
    assert groups == ["repave-admins", "repave-generators"]
    config = _auth_config(groups_claim=claim)
    assert role_for_groups(groups, config) == ROLE_ADMIN


def test_logout_return_to_derives_from_redirect_uri() -> None:
    config = _auth_config()
    assert logout_return_to(config) == "https://repave.example.com/"


def test_logout_return_to_explicit() -> None:
    config = _auth_config(oidc_logout_return_to="https://repave.example.com/logged-out")
    assert logout_return_to(config) == "https://repave.example.com/logged-out"


def test_build_idp_logout_url_prefers_end_session_endpoint() -> None:
    config = _auth_config()
    url = build_idp_logout_url(
        config,
        {"end_session_endpoint": "https://idp.example.com/oidc/logout"},
    )
    assert url is not None
    parsed = urlparse(url)
    assert parsed.path == "/oidc/logout"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client"]
    assert query["post_logout_redirect_uri"] == ["https://repave.example.com/"]


def test_build_idp_logout_url_auth0_v2_fallback() -> None:
    config = _auth_config(oidc_issuer="https://tenant.us.auth0.com/")
    url = build_idp_logout_url(config, {})
    assert url is not None
    parsed = urlparse(url)
    assert parsed.netloc == "tenant.us.auth0.com"
    assert parsed.path == "/v2/logout"
    query = parse_qs(parsed.query)
    assert query["client_id"] == ["client"]
    assert query["returnTo"] == ["https://repave.example.com/"]


def test_build_idp_logout_url_non_auth0_without_end_session() -> None:
    config = _auth_config(oidc_issuer="https://login.okta.com/oauth2/default")
    assert build_idp_logout_url(config, {}) is None
