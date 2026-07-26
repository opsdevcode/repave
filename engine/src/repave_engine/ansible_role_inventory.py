from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from repave_engine.module_inventory import (
    _git_clone_url,
    _load_repave_spec,
    list_repo_versions,
)


@dataclass(frozen=True)
class InventoryRole:
    repo_name: str
    galaxy_name: str
    namespace: str
    role_name: str
    git_url: str

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


def _ansible_role_from_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    if spec.get("artifactType") != "ansible-role":
        return None
    role = spec.get("ansibleRole")
    return cast(dict[str, Any], role) if isinstance(role, dict) else None


def list_inventory_roles(
    modules_root: Path,
    *,
    github_org: str,
) -> list[InventoryRole]:
    roles: list[InventoryRole] = []
    if not modules_root.is_dir():
        return roles

    for entry in sorted(modules_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if not name.startswith("ansible-role-"):
            continue
        spec = _load_repave_spec(entry)
        if spec is None:
            continue
        role_spec = _ansible_role_from_spec(spec)
        if role_spec is None:
            continue
        namespace = str(role_spec.get("namespace", "")).strip()
        role_name = str(role_spec.get("role_name", "")).strip()
        if not namespace or not role_name:
            continue
        galaxy_name = f"{namespace}.{role_name}"
        roles.append(
            InventoryRole(
                repo_name=name,
                galaxy_name=galaxy_name,
                namespace=namespace,
                role_name=role_name,
                git_url=_git_clone_url(entry, github_org, name),
            )
        )
    return roles


def inventory_roles_json(
    modules_root: Path,
    *,
    github_org: str,
) -> dict[str, Any]:
    items = list_inventory_roles(modules_root, github_org=github_org)
    return {"roles": [item.to_json() for item in items]}


def inventory_role_versions_json(
    modules_root: Path,
    repo_name: str,
    *,
    github_org: str,
    github_token: str | None = None,
) -> dict[str, Any]:
    versions = list_repo_versions(
        modules_root,
        repo_name,
        github_org=github_org,
        github_token=github_token,
    )
    return {"repo_name": repo_name, "versions": versions}


def normalize_pinned_roles_raw(raw: Any) -> list[dict[str, str]]:
    if raw in (None, "", "[]"):
        return []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, str):
        import json

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("pinned_roles must be a JSON array")
        items = parsed
    else:
        raise ValueError("pinned_roles must be a JSON array")

    normalized: list[dict[str, str]] = []
    for entry in items:
        if not isinstance(entry, dict):
            raise ValueError("each pinned_roles entry must be an object")
        galaxy_name = str(entry.get("galaxy_name", "")).strip()
        version = str(entry.get("version", "")).strip()
        src = str(entry.get("src", entry.get("git_url", ""))).strip()
        if not galaxy_name or not version or not src:
            raise ValueError("pinned_roles entries require galaxy_name, version, and src")
        normalized.append(
            {
                "galaxy_name": galaxy_name,
                "version": version,
                "src": src.removesuffix(".git"),
                "repo_name": str(entry.get("repo_name", "")).strip(),
            }
        )
    return normalized
