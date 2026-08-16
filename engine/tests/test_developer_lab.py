"""Tests for v3 developer lab defaults."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.developer_lab import is_developer_lab_enabled, load_developer_lab_paths
from repave_engine.settings import (
    load_environment_vending_config,
    load_service_catalog_config,
)
from repave_engine.v3_foundation import load_v3_foundation_config
from repave_engine.workload_profiles import WorkloadProfile

_LAB = "v3:\n  enabled: true\n  developer_lab:\n    enabled: true\n"


def _write_min_config(root: Path, *, extra: str = "") -> None:
    (root / "repave.config.yaml").write_text(
        f"apiVersion: repave.dev/v1\noutput:\n  github_org: acme\n  modules_root: ../mods\n{extra}",
        encoding="utf-8",
    )


@pytest.fixture
def v3_lab_root(repo_root: Path, tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    shutil.copytree(
        repo_root / "examples" / "platform-dev",
        root / "examples" / "platform-dev",
    )
    return root


def test_workload_profile_family_follows_blueprint() -> None:
    profile = WorkloadProfile(
        id="api-sandbox",
        label="API sandbox",
        blueprint="terraform-environment-stack",
    )
    assert profile.family == "terraform"


def test_developer_lab_disabled_without_v3(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    assert is_developer_lab_enabled(tmp_path) is False
    assert load_developer_lab_paths(tmp_path) is None
    assert load_service_catalog_config(tmp_path) is None
    assert load_environment_vending_config(tmp_path) is None


def test_developer_lab_requires_v3_enabled(tmp_path: Path) -> None:
    _write_min_config(
        tmp_path,
        extra="v3:\n  enabled: false\n  developer_lab:\n    enabled: true\n",
    )
    with pytest.raises(ValueError, match=r"v3\.enabled is false"):
        load_v3_foundation_config(tmp_path)


def test_developer_lab_stays_off_when_only_v3_enabled(v3_lab_root: Path) -> None:
    _write_min_config(v3_lab_root, extra="v3:\n  enabled: true\n")
    config = load_v3_foundation_config(v3_lab_root)
    assert config.enabled is True
    assert config.developer_lab_enabled is False
    assert load_developer_lab_paths(v3_lab_root) is None
    assert load_service_catalog_config(v3_lab_root) is None
    assert load_environment_vending_config(v3_lab_root) is None


def test_developer_lab_opt_in_wires_catalog_not_vending(v3_lab_root: Path) -> None:
    _write_min_config(v3_lab_root, extra=_LAB)
    config = load_v3_foundation_config(v3_lab_root)
    assert config.developer_lab_enabled is True

    paths = load_developer_lab_paths(v3_lab_root)
    assert paths is not None
    assert paths.maturity_rubric.is_file()

    catalog = load_service_catalog_config(v3_lab_root)
    assert catalog is not None
    assert catalog.enabled is True
    assert catalog.deployment_sets == paths.deployment_sets
    assert load_environment_vending_config(v3_lab_root) is None


def test_developer_lab_errors_when_fixtures_missing(tmp_path: Path) -> None:
    _write_min_config(tmp_path, extra=_LAB)
    with pytest.raises(ValueError, match="bundled fixtures are missing"):
        load_developer_lab_paths(tmp_path)


def test_developer_lab_portal_routes(v3_lab_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_min_config(v3_lab_root, extra=_LAB)
    monkeypatch.chdir(v3_lab_root)
    client = TestClient(create_app(repo_root=v3_lab_root))

    home = client.get("/home")
    assert_surface_moved(home, "home")

    lab = client.get("/lab")
    assert_surface_moved(lab, "sandbox")
    assert "Request developer lab" not in lab.text
    assert_surface_moved(client.get("/sandbox"), "sandbox")


def test_lab_route_404_when_developer_lab_disabled(
    v3_lab_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_min_config(
        v3_lab_root,
        extra=(
            "service_catalog:\n"
            "  enabled: true\n"
            "  maturity_rubric: examples/platform-dev/config/maturity-rubric.yaml\n"
            "  workload_profiles: examples/platform-dev/config/workload-profiles.yaml\n"
            "  deployment_sets: examples/platform-dev/config/deployment-sets.yaml\n"
        ),
    )
    monkeypatch.chdir(v3_lab_root)
    client = TestClient(create_app(repo_root=v3_lab_root))
    assert client.get("/lab").status_code == 404
    assert client.get("/sandbox").status_code == 200
    assert "Sandbox" in client.get("/").text
