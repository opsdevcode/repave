from __future__ import annotations

from pathlib import Path

PACKAGE_NAMES = (
    "repave-engine",
    "repave-engine-portal",
    "repave-corpus",
    "repave-operator",
)


def test_ghcr_package_readmes_exist(repo_root: Path) -> None:
    index = repo_root / "deploy" / "packages" / "README.md"
    assert index.is_file(), "deploy/packages/README.md index is required"
    for name in PACKAGE_NAMES:
        readme = repo_root / "deploy" / "packages" / name / "README.md"
        assert readme.is_file(), f"missing package README: {readme}"
        body = readme.read_text(encoding="utf-8")
        assert f"# {name}" in body or f"# {name.replace('-', ' ')}" in body.lower()
        assert len(body.strip()) > 200, f"{name} README should describe the image role"


def test_container_workflow_sets_package_descriptions(repo_root: Path) -> None:
    workflow = (repo_root / ".github" / "workflows" / "container.yml").read_text(encoding="utf-8")
    for name in PACKAGE_NAMES:
        assert f"opsdevcode/{name}" in workflow
    assert workflow.count("org.opencontainers.image.description=") >= 1
    assert "description:" in workflow
    assert "fail-fast: false" in workflow
    assert "verify-ghcr-tag.sh" in workflow
    assert "ghcr-build-push.sh" in workflow
    assert "github.repository_owner" in workflow


def test_ghcr_publish_hack_scripts_exist(repo_root: Path) -> None:
    for name in ("ghcr-login.sh", "ghcr-build-push.sh", "verify-ghcr-tag.sh"):
        path = repo_root / "deploy" / "k8s" / "hack" / name
        assert path.is_file(), f"missing GHCR publish helper: {path}"
