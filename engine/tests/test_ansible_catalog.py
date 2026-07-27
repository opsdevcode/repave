from __future__ import annotations

from pathlib import Path

from repave_engine.ansible_catalog import (
    catalog_for_api,
    load_ansible_catalog,
    playbook_pattern_by_id,
    role_pattern_by_id,
    role_patterns_for_platforms,
)


def test_load_ansible_catalog_has_patterns(repo_root: Path) -> None:
    catalog = load_ansible_catalog(repo_root)
    assert len(catalog.role_patterns) >= 3
    assert len(catalog.playbook_patterns) >= 3
    assert catalog.defaults.get("role_pattern_source") == "linux-service"
    assert catalog.defaults.get("playbook_pattern_source") == "linux-patch-baseline"
    linux = role_pattern_by_id(catalog, "linux-service")
    assert linux is not None
    assert linux.platform == "linux"


def test_role_patterns_filtered_for_windows_only(repo_root: Path) -> None:
    catalog = load_ansible_catalog(repo_root)
    patterns = role_patterns_for_platforms(
        catalog,
        support_linux=False,
        support_windows=True,
    )
    ids = {item.id for item in patterns}
    assert "windows-service" in ids
    assert "linux-service" not in ids
    assert "repave-baseline" in ids


def test_catalog_for_api_includes_form_preset(repo_root: Path) -> None:
    catalog = load_ansible_catalog(repo_root)
    payload = catalog_for_api(
        catalog,
        support_linux=True,
        support_windows=False,
        blueprint_name="ansible-role-generic",
    )
    assert payload["form_preset"]["decision_fields"][2] == "role_pattern_source"


def test_catalog_for_api_playbook_patterns(repo_root: Path) -> None:
    catalog = load_ansible_catalog(repo_root)
    payload = catalog_for_api(
        catalog,
        support_linux=True,
        support_windows=False,
        blueprint_name="ansible-playbook-project",
    )
    ids = {item["id"] for item in payload["playbook_patterns"]}
    assert "linux-patch-baseline" in ids
    assert payload["form_preset"]["decision_fields"][1] == "playbook_pattern_source"
    win = playbook_pattern_by_id(catalog, "windows-update-baseline")
    assert win is not None
    assert "ansible.windows" in win.requires_collections
