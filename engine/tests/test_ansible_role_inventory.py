from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from repave_engine.ansible_role_inventory import (
    inventory_role_versions_json,
    inventory_roles_json,
    list_inventory_roles,
    normalize_pinned_roles_raw,
)


def _write_role_repo(
    modules_root: Path,
    repo_name: str,
    *,
    namespace: str = "acme",
    role_name: str = "webserver",
    blueprint_version: str = "1.0.0",
) -> Path:
    repo_dir = modules_root / repo_name
    repo_dir.mkdir(parents=True)
    doc = {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": role_name},
        "spec": {
            "artifactType": "ansible-role",
            "ansibleRole": {
                "namespace": namespace,
                "role_name": role_name,
            },
            "blueprint": {"name": "ansible-role-generic", "version": blueprint_version},
            "standard": {"source": "standards", "version": "0.4.0"},
            "generation": {
                "engine_version": "1.0.0",
                "generated_at": "2026-01-01T00:00:00+00:00",
            },
        },
    }
    (repo_dir / "repave.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return repo_dir


def test_list_inventory_roles_scans_ansible_role_repos(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    _write_role_repo(modules_root, "ansible-role-webserver", role_name="webserver")

    items = list_inventory_roles(modules_root, github_org="acme")

    assert len(items) == 1
    assert items[0].repo_name == "ansible-role-webserver"
    assert items[0].galaxy_name == "acme.webserver"
    assert items[0].git_url == "https://github.com/acme/ansible-role-webserver.git"


def test_inventory_role_versions_json_uses_blueprint_fallback(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    _write_role_repo(modules_root, "ansible-role-demo", blueprint_version="3.2.1")

    payload = inventory_role_versions_json(
        modules_root,
        "ansible-role-demo",
        github_org="acme",
    )

    assert payload["repo_name"] == "ansible-role-demo"
    assert "3.2.1" in payload["versions"][0]


def test_normalize_pinned_roles_raw_parses_json_string() -> None:
    raw = json.dumps(
        [
            {
                "galaxy_name": "acme.web",
                "version": "1.0.0",
                "src": "https://github.com/acme/ansible-role-web",
                "repo_name": "ansible-role-web",
            }
        ]
    )
    items = normalize_pinned_roles_raw(raw)
    assert items[0]["galaxy_name"] == "acme.web"
    assert items[0]["src"] == "https://github.com/acme/ansible-role-web"


def test_normalize_pinned_roles_raw_rejects_incomplete_entry() -> None:
    with pytest.raises(ValueError, match="galaxy_name"):
        normalize_pinned_roles_raw('[{"version": "1.0.0", "src": "https://example.com/r"}]')


def test_inventory_roles_json_shape(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    _write_role_repo(modules_root, "ansible-role-a", role_name="a")

    payload = inventory_roles_json(modules_root, github_org="org")
    assert "roles" in payload
    assert payload["roles"][0]["galaxy_name"] == "acme.a"
