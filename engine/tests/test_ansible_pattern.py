from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.ansible_pattern import (
    normalize_collection_sample_pattern_inputs,
    normalize_playbook_pattern_inputs,
    normalize_role_pattern_inputs,
    resolve_default_playbook_pattern,
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


def test_resolve_default_playbook_pattern_windows_only() -> None:
    assert (
        resolve_default_playbook_pattern(support_linux=False, support_windows=True)
        == "windows-update-baseline"
    )


def test_normalize_playbook_pattern_default(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "ansible-playbook-project", repo_root)
    normalized: dict[str, str] = {
        "project_name": "patch",
        "description": "Patch playbooks",
        "min_ansible_version": "2.18",
        "environment": "dev",
        "pinned_roles": "[]",
        "support_linux": "true",
        "support_windows": "false",
    }
    normalize_playbook_pattern_inputs(blueprint, normalized, repo_root)
    assert normalized["playbook_pattern_source"] == "linux-patch-baseline"


def test_normalize_playbook_pinned_rollout_requires_roles(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "ansible-playbook-project", repo_root)
    normalized: dict[str, str | list[dict[str, str]]] = {
        "project_name": "rollout",
        "description": "Role rollout",
        "min_ansible_version": "2.18",
        "environment": "dev",
        "pinned_roles": [],
        "support_linux": "true",
        "support_windows": "false",
        "playbook_pattern_source": "pinned-roles-rollout",
    }
    with pytest.raises(ValueError, match="requires at least one pinned Galaxy role"):
        normalize_playbook_pattern_inputs(blueprint, normalized, repo_root)


def test_normalize_collection_sample_pattern_default(repo_root: Path) -> None:
    blueprint = load_blueprint(repo_root / "blueprints" / "ansible-collection-generic", repo_root)
    normalized: dict[str, str] = {
        "namespace": "acme",
        "collection_name": "platform",
        "description": "Platform collection",
        "sample_role_name": "sample",
        "min_ansible_version": "2.18",
        "support_linux": "true",
        "support_windows": "false",
    }
    normalize_collection_sample_pattern_inputs(blueprint, normalized, repo_root)
    assert normalized["sample_role_pattern_source"] == "linux-service"
    assert normalized["role_name"] == "sample"
