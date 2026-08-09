"""Platform dev profile loads and drives populated console pages."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from repave_engine import settings
from repave_engine.api import create_app
from repave_engine.settings import (
    load_audit_config,
    load_durability_config,
    load_fleet_config,
    load_platform_metrics_config,
    load_portal_config,
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


def test_platform_dev_pages_render(
    platform_dev_repo: Path,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=platform_dev_repo, output_config=output_config))
    for path, needle in (
        ("/platform/fleet", "Governed repositories"),
        ("/platform/ops", "Estate health"),
        ("/platform/standards", "Standards blast radius"),
        ("/platform/finops", "FinOps showback"),
        ("/platform/adoption", "Golden path adoption"),
        ("/platform/compliance", "Compliance posture"),
        ("/platform/value-stream", "Value stream"),
        ("/platform/feedback", "Developer feedback"),
        ("/platform/campaigns", "Operator campaigns"),
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert needle in response.text, path

    campaigns = client.get("/platform/campaigns").text
    assert "platform-rollout" in campaigns

    home = client.get("/").text
    more_start = home.index("shell__nav-more")
    more_end = home.index("</details>", more_start)
    more_section = home[more_start:more_end]
    assert 'href="/platform/finops"' in more_section
    assert 'href="/platform/compliance"' in more_section
    assert 'href="/platform/value-stream"' in more_section
    assert 'href="/platform/feedback"' in more_section
    assert 'href="/platform/roadmap"' in more_section

    roadmap = client.get("/platform/roadmap").text
    assert "Roadmap evidence" in roadmap
    assert "Theme adoption evidence" in roadmap
    assert "shell__footer-link" in home
    assert 'href="/platform/ops"' in home
    assert 'href="/platform/fleet"' in home
    assert 'class="platform-subnav shell__nav"' in client.get("/platform/fleet").text
