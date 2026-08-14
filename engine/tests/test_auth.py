from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    AuthConfig,
    build_idp_logout_url,
    build_login_redirect,
    groups_from_claims,
    is_public_path,
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
    coarse_rbac_enabled: bool = False,
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
        coarse_rbac_enabled=coarse_rbac_enabled,
    )


def test_load_portal_config_compact(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  density: compact\n", encoding="utf-8")
    cfg = load_portal_config(tmp_path)
    assert cfg.density == "compact"


def test_load_portal_config_white_label(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  logo_url: /static/brand/custom.svg\n  accent_color: '#F59E0B'\n",
        encoding="utf-8",
    )
    cfg = load_portal_config(tmp_path)
    assert cfg.logo_url == "/static/brand/custom.svg"
    assert cfg.accent_color == "#f59e0b"


def test_load_portal_config_white_label_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  logo_url: /static/from-file.svg\n  accent_color: '#111111'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_PORTAL_LOGO_URL", "https://cdn.example.com/mark.svg")
    monkeypatch.setenv("REPAVE_PORTAL_ACCENT_COLOR", "#0ea5e9")
    cfg = load_portal_config(tmp_path)
    assert cfg.logo_url == "https://cdn.example.com/mark.svg"
    assert cfg.accent_color == "#0ea5e9"


def test_load_portal_config_rejects_unsafe_logo_url(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  logo_url: javascript:alert(1)\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="logo_url"):
        load_portal_config(tmp_path)


def test_load_portal_config_rejects_invalid_accent(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  accent_color: orange\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="accent_color"):
        load_portal_config(tmp_path)


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


def test_merge_oidc_user_claims_reads_groups_from_id_token() -> None:
    import jwt

    from repave_engine.auth import merge_oidc_user_claims, role_for_groups

    id_token = jwt.encode(
        {
            "sub": "auth0|abc",
            "groups": ["repave-generators"],
        },
        "secret",
        algorithm="HS256",
    )
    merged = merge_oidc_user_claims(
        {"sub": "auth0|abc", "email": "user@example.com"},
        id_token,
        groups_claim="groups",
    )
    config = _auth_config()
    assert role_for_groups(groups_from_claims(merged, "groups"), config) == ROLE_GENERATOR


def test_merge_oidc_user_claims_prefers_userinfo_when_present() -> None:
    import jwt

    from repave_engine.auth import merge_oidc_user_claims

    id_token = jwt.encode({"groups": ["repave-generators"]}, "secret", algorithm="HS256")
    merged = merge_oidc_user_claims(
        {"groups": ["repave-admins"]},
        id_token,
        groups_claim="groups",
    )
    assert groups_from_claims(merged, "groups") == ["repave-admins"]


def test_session_role_from_oidc_groups_grants_admin_when_coarse_rbac_disabled() -> None:
    from repave_engine.auth import session_role_from_oidc_groups

    config = _auth_config(coarse_rbac_enabled=False)
    assert session_role_from_oidc_groups([], config) == ROLE_ADMIN


def test_session_role_from_oidc_groups_honors_groups_when_coarse_rbac_enabled() -> None:
    from repave_engine.auth import session_role_from_oidc_groups

    config = _auth_config(coarse_rbac_enabled=True)
    assert session_role_from_oidc_groups([], config) == ROLE_VIEWER
    assert session_role_from_oidc_groups(["repave-generators"], config) == ROLE_GENERATOR


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


def test_public_paths_include_marketing_pages() -> None:
    assert is_public_path("/")
    assert is_public_path("/signup")
    assert is_public_path("/auth/login")
    assert is_public_path("/auth/signup")
    assert is_public_path("/static/repave.css")
    assert not is_public_path("/library")
    assert not is_public_path("/home")


def test_build_login_redirect_includes_signup_hint() -> None:
    request = SimpleNamespace(session={}, query_params={"next": "/"})
    response = build_login_redirect(
        request,  # type: ignore[arg-type]
        _auth_config(),
        {"authorization_endpoint": "https://idp.example.com/authorize"},
        screen_hint="signup",
    )
    parsed = urlparse(response.headers["location"])
    query = parse_qs(parsed.query)
    assert query["screen_hint"] == ["signup"]
    assert request.session["oidc_next"] == "/"


def test_build_idp_logout_url_non_auth0_without_end_session() -> None:
    config = _auth_config(oidc_issuer="https://login.okta.com/oauth2/default")
    assert build_idp_logout_url(config, {}) is None
