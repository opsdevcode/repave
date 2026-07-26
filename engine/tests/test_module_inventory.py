from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repave_engine.module_inventory import (
    build_git_module_source,
    list_inventory_module_versions,
    list_inventory_modules,
    normalize_pinned_modules_raw,
)


def _write_module_repo(
    modules_root: Path,
    repo_name: str,
    *,
    cloud_provider: str = "aws",
    module_name: str = "example",
    blueprint_version: str = "1.0.0",
) -> Path:
    repo_dir = modules_root / repo_name
    repo_dir.mkdir(parents=True)
    doc = {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": module_name},
        "spec": {
            "artifactType": "terraform-module",
            "terraformModule": {
                "module_name": module_name,
                "cloud_provider": cloud_provider,
                "provider_services": ["s3"],
            },
            "blueprint": {"name": "terraform-module-generic", "version": blueprint_version},
            "standard": {"source": "standards", "version": "0.4.0"},
            "generation": {
                "engine_version": "1.0.0",
                "generated_at": "2026-01-01T00:00:00+00:00",
            },
        },
    }
    (repo_dir / "repave.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return repo_dir


def test_list_inventory_modules_includes_example_and_scanned_repo(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    _write_module_repo(modules_root, "tf-aws-networking", module_name="networking")

    items = list_inventory_modules(modules_root, github_org="acme", cloud_provider="aws")

    repo_names = [item.repo_name for item in items]
    assert "_example" in repo_names
    assert "tf-aws-networking" in repo_names
    networking = next(item for item in items if item.repo_name == "tf-aws-networking")
    assert networking.module_name == "networking"
    assert networking.git_url == "https://github.com/acme/tf-aws-networking.git"


def test_list_inventory_modules_filters_cloud_provider(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    _write_module_repo(modules_root, "tf-aws-a", cloud_provider="aws")
    _write_module_repo(modules_root, "tf-azure-b", cloud_provider="azure")

    items = list_inventory_modules(modules_root, github_org="acme", cloud_provider="azure")

    repo_names = {item.repo_name for item in items}
    assert "tf-azure-b" in repo_names
    assert "tf-aws-a" not in repo_names
    assert "_example" in repo_names


def test_list_inventory_module_versions_falls_back_to_blueprint_version(
    tmp_path: Path,
) -> None:
    modules_root = tmp_path / "modules"
    _write_module_repo(modules_root, "tf-aws-demo", blueprint_version="2.3.4")

    versions = list_inventory_module_versions(
        modules_root,
        "tf-aws-demo",
        github_org="acme",
    )

    assert versions[0].startswith("v")


def test_build_git_module_source() -> None:
    assert (
        build_git_module_source("https://github.com/acme/tf-aws-x.git", "v1.0.0")
        == "git::https://github.com/acme/tf-aws-x.git?ref=v1.0.0"
    )


def test_normalize_pinned_modules_raw_requires_unique_names() -> None:
    raw = '[{"name":"a","source":"./m1"},{"name":"a","source":"./m2"}]'
    with pytest.raises(ValueError, match="duplicate"):
        normalize_pinned_modules_raw(raw)
