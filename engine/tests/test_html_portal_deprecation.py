from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.api_deprecation import (
    HTML_PORTAL_DISABLED_DETAIL,
    V1_DEPRECATION_HEADERS,
    is_html_portal_path,
)
from repave_engine.settings import load_portal_config


def test_is_html_portal_path_excludes_api_and_probes() -> None:
    assert is_html_portal_path("/")
    assert is_html_portal_path("/home")
    assert is_html_portal_path("/sandbox")
    assert not is_html_portal_path("/api")
    assert not is_html_portal_path("/api/v2/runs")
    assert not is_html_portal_path("/health")
    assert not is_html_portal_path("/readyz")
    assert not is_html_portal_path("/metrics")
    assert not is_html_portal_path("/static/repave.css")
    assert not is_html_portal_path("/docs")
    assert not is_html_portal_path("/openapi.json")


def test_html_routes_do_not_send_sunset_headers(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    landing = client.get("/")
    assert landing.status_code == 200
    assert "Sunset" not in landing.headers
    assert "Deprecation" not in landing.headers

    health = client.get("/health")
    assert health.status_code == 200
    assert "Sunset" not in health.headers

    v2 = client.get("/api/v2/catalog/entities")
    assert v2.status_code == 200
    assert "Sunset" not in v2.headers

    v1 = client.get("/api/v1/catalog/entities")
    assert v1.status_code == 200
    for key, value in V1_DEPRECATION_HEADERS.items():
        assert v1.headers.get(key) == value


def test_html_disabled_returns_410(
    repo_root, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_PORTAL_HTML", "0")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    landing = client.get("/")
    assert landing.status_code == 410
    assert landing.json()["detail"] == HTML_PORTAL_DISABLED_DETAIL
    assert "Sunset" not in landing.headers

    home = client.get("/home")
    assert home.status_code == 410

    health = client.get("/health")
    assert health.status_code == 200
    v2 = client.get("/api/v2/catalog/entities")
    assert v2.status_code == 200


def test_load_portal_config_html_default(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  density: default\n", encoding="utf-8")
    cfg = load_portal_config(tmp_path)
    assert cfg.html is True
    assert cfg.backstage_url == ""


def test_load_portal_config_html_file(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  html: false\n", encoding="utf-8")
    cfg = load_portal_config(tmp_path)
    assert cfg.html is False


def test_load_portal_config_html_env_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  html: true\n", encoding="utf-8")
    monkeypatch.setenv("REPAVE_PORTAL_HTML", "false")
    cfg = load_portal_config(tmp_path)
    assert cfg.html is False


def test_html_nav_includes_catalog_handoff_when_backstage_url_set(
    repo_root, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_BACKSTAGE_URL", "/idp")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    library = client.get("/library")
    assert library.status_code == 200
    assert 'href="/idp"' in library.text
    primary = library.text.split("shell__nav--primary", 1)[1].split("shell__nav-more", 1)[0]
    assert ">Golden paths<" in primary
    assert ">Catalog<" in primary
    assert "Software catalog" not in library.text
    assert '"label": "Catalog"' in library.text
    assert '"href": "/idp"' in library.text
    assert "Ownership and lineage" in library.text


def test_html_nav_hides_catalog_without_backstage_url(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    home = client.get("/")
    assert home.status_code == 200
    primary = home.text.split("shell__nav--primary", 1)[1].split("shell__nav-more", 1)[0]
    assert ">Golden paths<" in primary
    assert ">Catalog<" not in primary
    assert '"label": "Golden paths"' in home.text
    assert '"label": "Catalog"' not in home.text


def test_load_portal_config_html_rejects_non_bool(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text("portal:\n  html: maybe\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"portal\.html must be a boolean"):
        load_portal_config(tmp_path)
