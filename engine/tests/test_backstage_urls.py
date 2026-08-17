from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.backstage_urls import backstage_catalog_entity_href
from repave_engine.settings import load_portal_config, normalize_portal_backstage_url


def test_backstage_catalog_entity_href_builds_component_path() -> None:
    assert (
        backstage_catalog_entity_href("/idp", name="tf-aws-demo")
        == "/idp/catalog/default/component/tf-aws-demo"
    )
    assert (
        backstage_catalog_entity_href("https://backstage.example.com/", name="checkout")
        == "https://backstage.example.com/catalog/default/component/checkout"
    )


def test_backstage_catalog_entity_href_empty_without_base_or_name() -> None:
    assert backstage_catalog_entity_href("", name="tf-aws-demo") == ""
    assert backstage_catalog_entity_href("/idp", name="") == ""


def test_normalize_portal_backstage_url_accepts_path_and_http() -> None:
    assert normalize_portal_backstage_url("/idp/") == "/idp"
    assert normalize_portal_backstage_url("https://backstage.example.com/") == (
        "https://backstage.example.com"
    )


def test_normalize_portal_backstage_url_rejects_javascript() -> None:
    with pytest.raises(ValueError, match=r"portal\.backstage_url"):
        normalize_portal_backstage_url("javascript:alert(1)")


def test_load_portal_config_backstage_url_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "portal:\n  backstage_url: /from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REPAVE_BACKSTAGE_URL", "https://idp.example.com")
    cfg = load_portal_config(tmp_path)
    assert cfg.backstage_url == "https://idp.example.com"
