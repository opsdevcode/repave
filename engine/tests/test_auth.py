from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.auth import ROLE_ADMIN, ROLE_GENERATOR, AuthConfig, role_for_groups
from repave_engine.settings import load_portal_config


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


def test_role_for_groups() -> None:
    config = AuthConfig(
        service_enabled=True,
        session_secret="secret",
        api_token="",
        oidc_issuer="https://idp.example.com",
        oidc_client_id="client",
        oidc_client_secret="sec",
        oidc_redirect_uri="https://repave.example.com/auth/callback",
        oidc_scopes=("openid", "profile", "email"),
        groups_claim="groups",
        admin_groups=frozenset({"repave-admins"}),
        generator_groups=frozenset({"repave-generators"}),
    )
    assert role_for_groups(["repave-admins"], config) == ROLE_ADMIN
    assert role_for_groups(["repave-generators"], config) == ROLE_GENERATOR
    assert role_for_groups(["other"], config) == "viewer"
