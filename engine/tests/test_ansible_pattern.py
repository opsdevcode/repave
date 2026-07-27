from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.ansible_pattern import (
    normalize_role_pattern_inputs,
    resolve_default_role_pattern,
)
from repave_engine.blueprint import load_blueprint


def test_resolve_default_role_pattern_windows_only() -> None:
    assert (
        resolve_default_role_pattern(support_linux=False, support_windows=True) == "windows-service"
    )


def test_resolve_default_role_pattern_mixed_prefers_linux() -> None:
    assert resolve_default_role_pattern(support_linux=True, support_windows=True) == "linux-service"


def test_normalize_platform_aware_default(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "ansible-role-generic", repo_root)
    normalized: dict[str, str] = {
        "role_name": "web",
        "namespace": "acme",
        "description": "Web role",
        "min_ansible_version": "2.18",
        "support_linux": "true",
        "support_windows": "false",
        "windows_server_generation": "2022",
        "target_platforms_advanced": "",
    }
    normalize_role_pattern_inputs(blueprint, normalized, repo_root)
    assert normalized["role_pattern_source"] == "linux-service"


def test_normalize_rejects_linux_pattern_on_windows_only(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "ansible-role-generic", repo_root)
    normalized: dict[str, str] = {
        "role_name": "web",
        "namespace": "acme",
        "description": "Web role",
        "min_ansible_version": "2.18",
        "support_linux": "false",
        "support_windows": "true",
        "windows_server_generation": "2022",
        "target_platforms_advanced": "",
        "target_platforms": "Windows:2022",
        "role_pattern_source": "linux-service",
    }
    with pytest.raises(ValueError, match="not valid for selected platforms"):
        normalize_role_pattern_inputs(blueprint, normalized, repo_root)
