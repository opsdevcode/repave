from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

import yaml

from repave_engine.github import GitHubError, list_repository_tags
from repave_engine.target_repo import _git_executable, resolve_module_repository_from_git


@dataclass(frozen=True)
class InventoryModule:
    repo_name: str
    cloud_provider: str
    module_name: str
    source_kind: str
    git_url: str | None = None
    local_source: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


LOCAL_EXAMPLE = InventoryModule(
    repo_name="_example",
    cloud_provider="",
    module_name="foundation",
    source_kind="local",
    local_source="./modules/_example",
)


def _load_repave_spec(repo_dir: Path) -> dict[str, Any] | None:
    path = repo_dir / "repave.yaml"
    if not path.is_file():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    spec = data.get("spec")
    return cast(dict[str, Any], spec) if isinstance(spec, dict) else None


def _terraform_module_from_spec(spec: dict[str, Any]) -> dict[str, Any] | None:
    if spec.get("artifactType") != "terraform-module":
        return None
    module = spec.get("terraformModule")
    return cast(dict[str, Any], module) if isinstance(module, dict) else None


def _git_clone_url(repo_dir: Path, fallback_org: str, repo_name: str) -> str:
    try:
        repository = resolve_module_repository_from_git(repo_dir)
        return repository.clone_url
    except (OSError, RuntimeError, subprocess.CalledProcessError):
        return f"https://github.com/{fallback_org}/{repo_name}.git"


def _list_local_git_tags(repo_dir: Path) -> list[str]:
    if not (repo_dir / ".git").is_dir():
        return []
    result = subprocess.run(
        [_git_executable(), "tag", "--list", "--sort=-v:refname"],
        cwd=repo_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def list_inventory_modules(
    modules_root: Path,
    *,
    github_org: str,
    cloud_provider: str | None = None,
) -> list[InventoryModule]:
    """Scan REPAVE_MODULES_ROOT for terraform-module repos (tf-* / tfm-*)."""
    modules: list[InventoryModule] = [LOCAL_EXAMPLE]
    if not modules_root.is_dir():
        return _filter_by_provider(modules, cloud_provider)

    for entry in sorted(modules_root.iterdir()):
        if not entry.is_dir():
            continue
        name = entry.name
        if not (name.startswith("tf-") or name.startswith("tfm-")):
            continue
        spec = _load_repave_spec(entry)
        if spec is None:
            continue
        tf_module = _terraform_module_from_spec(spec)
        if tf_module is None:
            continue
        provider = str(tf_module.get("cloud_provider", "")).strip()
        module_name = str(tf_module.get("module_name", name)).strip()
        modules.append(
            InventoryModule(
                repo_name=name,
                cloud_provider=provider,
                module_name=module_name,
                source_kind="git",
                git_url=_git_clone_url(entry, github_org, name),
            )
        )

    return _filter_by_provider(modules, cloud_provider)


def _filter_by_provider(
    modules: list[InventoryModule],
    cloud_provider: str | None,
) -> list[InventoryModule]:
    if not cloud_provider:
        return modules
    provider = cloud_provider.strip().lower()
    filtered: list[InventoryModule] = []
    for item in modules:
        if item.repo_name == "_example":
            filtered.append(item)
            continue
        if item.cloud_provider.lower() == provider:
            filtered.append(item)
    return filtered


def list_repo_versions(
    modules_root: Path,
    repo_name: str,
    *,
    github_org: str,
    github_token: str | None = None,
) -> list[str]:
    repo_dir = modules_root / repo_name
    if not repo_dir.is_dir():
        return []

    tags = _list_local_git_tags(repo_dir)
    if tags:
        return tags

    if github_token:
        owner = github_org
        name = repo_name
        try:
            repository = resolve_module_repository_from_git(repo_dir)
            owner = repository.owner
            name = repository.name
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            pass
        try:
            remote_tags = list_repository_tags(owner, name, github_token)
            if remote_tags:
                return remote_tags
        except GitHubError:
            pass

    spec = _load_repave_spec(repo_dir)
    if spec is not None:
        blueprint = spec.get("blueprint")
        if isinstance(blueprint, dict):
            version = str(blueprint.get("version", "")).strip()
            if version:
                return [f"v{version}" if not version.startswith("v") else version, "main"]

    return ["main"]


def list_inventory_module_versions(
    modules_root: Path,
    repo_name: str,
    *,
    github_org: str,
    github_token: str | None = None,
) -> list[str]:
    if repo_name == "_example":
        return ["local"]

    return list_repo_versions(
        modules_root,
        repo_name,
        github_org=github_org,
        github_token=github_token,
    )


def build_git_module_source(git_url: str, ref: str) -> str:
    base = git_url.removesuffix(".git")
    if not base.endswith(".git"):
        base = f"{base}.git"
    return f"git::{base}?ref={ref}"


def inventory_modules_json(
    modules_root: Path,
    *,
    github_org: str,
    cloud_provider: str | None = None,
) -> dict[str, Any]:
    items = list_inventory_modules(
        modules_root,
        github_org=github_org,
        cloud_provider=cloud_provider,
    )
    return {"modules": [item.to_json() for item in items]}


def inventory_versions_json(
    modules_root: Path,
    repo_name: str,
    *,
    github_org: str,
    github_token: str | None = None,
) -> dict[str, Any]:
    versions = list_inventory_module_versions(
        modules_root,
        repo_name,
        github_org=github_org,
        github_token=github_token,
    )
    return {"repo_name": repo_name, "versions": versions}
