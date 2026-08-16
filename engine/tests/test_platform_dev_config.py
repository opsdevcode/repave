"""Platform dev profile loads and drives populated console pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine import settings
from repave_engine.api import create_app
from repave_engine.settings import (
    load_audit_config,
    load_durability_config,
    load_environment_vending_config,
    load_fleet_config,
    load_platform_metrics_config,
    load_portal_config,
    load_service_catalog_config,
)


@pytest.fixture
def platform_dev_root(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dev_root = repo_root / "examples" / "platform-dev"
    raw = (dev_root / "repave.config.platform-dev.yaml").read_text(encoding="utf-8")
    resolved = raw.replace("examples/platform-dev/", f"{dev_root}/")
    (tmp_path / "repave.config.yaml").write_text(resolved, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def platform_dev_repo(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Inject platform-dev config without writing repave.config.yaml (parallel-safe)."""
    dev_yaml = repo_root / "examples" / "platform-dev" / "repave.config.platform-dev.yaml"
    dev_data = yaml.safe_load(dev_yaml.read_text(encoding="utf-8"))
    assert isinstance(dev_data, dict)
    config_path = (repo_root / "repave.config.yaml").resolve()
    real_load = settings._load_config_file

    def patched_load(path: Path) -> dict[str, Any]:
        if path.resolve() == config_path:
            return dev_data
        return real_load(path)

    monkeypatch.setattr(settings, "_load_config_file", patched_load)
    return repo_root


def test_platform_dev_config_loads(platform_dev_root: Path) -> None:
    fleet = load_fleet_config(platform_dev_root)
    assert fleet is not None
    assert fleet.enabled is True
    assert fleet.file.is_file()

    metrics = load_platform_metrics_config(platform_dev_root)
    assert metrics is not None
    assert metrics.enabled is True
    assert metrics.search_limit == 100

    durability = load_durability_config(platform_dev_root)
    assert durability is not None
    assert durability.async_generation is True

    portal = load_portal_config(platform_dev_root)
    assert portal.cost_reader == "focus"
    assert portal.cost_focus.file.endswith("export.json")
    assert portal.cost_snapshots_file is not None
    assert portal.cost_anomalies.enabled is True

    audit = load_audit_config(platform_dev_root)
    assert audit is not None
    assert audit.enabled is True

    catalog = load_service_catalog_config(platform_dev_root)
    assert catalog is not None
    assert catalog.enabled is True
    assert catalog.maturity_rubric is not None
    assert catalog.maturity_rubric.is_file()

    vend = load_environment_vending_config(platform_dev_root)
    assert vend is not None
    assert vend.enabled is True
    assert vend.file.is_file()


def test_platform_dev_pages_render(
    platform_dev_repo: Path,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=platform_dev_repo, output_config=output_config))
    for path, surface_id in (
        ("/platform/fleet", "platform-fleet"),
        ("/platform/ops", "platform-ops"),
        ("/platform/standards", "platform-standards"),
        ("/platform/finops", "platform-finops"),
        ("/platform/adoption", "platform-adoption"),
        ("/platform/compliance", "platform-compliance"),
        ("/platform/value-stream", "platform-value-stream"),
        ("/platform/feedback", "platform-feedback"),
        ("/platform/campaigns", "platform-campaigns"),
        ("/platform/maturity", "platform-maturity"),
        ("/platform/initiatives", "platform-initiatives"),
        ("/home", "home"),
    ):
        response = client.get(path)
        assert_surface_moved(response, surface_id)

    sandbox = client.get("/sandbox")
    assert sandbox.status_code == 200
    assert "Request a sandbox" in sandbox.text

    home = client.get("/").text
    primary = home.split("shell__nav--primary", 1)[1].split("shell__nav-more", 1)[0]
    assert 'href="/platform/fleet"' in primary
    assert ">Platform<" in primary
    assert 'href="/home"' in primary
    assert 'href="/sandbox"' in primary
    more_start = home.index("shell__nav-more")
    more_end = home.index("</details>", more_start)
    more_section = home[more_start:more_end]
    assert 'href="/platform/finops"' not in more_section
    assert 'href="/import"' in more_section
    # Deep platform routes live in the command palette and platform subnav.
    assert '"/platform/finops"' in home
    assert '"/platform/compliance"' in home
    assert '"/platform/value-stream"' in home
    assert '"/platform/feedback"' in home
    assert '"/platform/roadmap"' in home
    assert '"/platform/maturity"' in home
    assert '"/platform/initiatives"' in home
    footer = home[home.index("shell__footer") :]
    assert "repave v3 · The intelligent platform layer" in footer
    assert "shell__footer-link" not in footer

    assert_surface_moved(client.get("/platform/roadmap"), "platform-roadmap")
    assert_surface_moved(client.get("/platform/finops"), "platform-finops")
    assert 'href="/platform/fleet"' in primary
