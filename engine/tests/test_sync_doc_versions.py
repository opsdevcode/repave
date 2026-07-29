from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _load_sync_module(repo_root: Path):
    path = repo_root / "scripts" / "sync_doc_versions.py"
    spec = importlib.util.spec_from_file_location("sync_doc_versions", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_doc_versions"] = module
    spec.loader.exec_module(module)
    return module


def test_list_paths_includes_all_doc_targets(repo_root: Path) -> None:
    sync = _load_sync_module(repo_root)
    paths = set(sync.DOC_TARGET_REL_PATHS)
    assert paths == {
        "docs/roadmap.md",
        "README.md",
        "docs/portal-design.md",
        "docs/demo-verification.md",
        "docs/operator-ga.md",
    }


def test_sync_updates_doc_pointers(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    roadmap = tmp_path / "docs" / "roadmap.md"
    readme = tmp_path / "README.md"
    portal = tmp_path / "docs" / "portal-design.md"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    portal.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text(
        "**Current release:** v1.0.0\n\n```text\nv1.0.0  today     old line\n```\n",
        encoding="utf-8",
    )
    readme.write_text(
        "[v1.0.0](https://github.com/opsdevcode/repave/releases/tag/v1.0.0)\n",
        encoding="utf-8",
    )
    portal.write_text("(engine tags through **v1.0.0**).\n", encoding="utf-8")
    demo = tmp_path / "docs" / "demo-verification.md"
    demo.write_text("(engine v1.0.0, blueprint\n", encoding="utf-8")
    op_ga = tmp_path / "docs" / "operator-ga.md"
    op_ga.write_text("(engine **v1.0.0**).\n", encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        changed = sync.apply_sync("2.5.0")
        assert len(changed) == 5
        assert "**Current release:** v2.5.0" in roadmap.read_text(encoding="utf-8")
        assert "v2.5.0  today" in roadmap.read_text(encoding="utf-8")
        assert "[v2.5.0](https://github.com/opsdevcode/repave/releases/tag/v2.5.0)" in (
            readme.read_text(encoding="utf-8")
        )
        assert "(engine tags through **v2.5.0**)" in portal.read_text(encoding="utf-8")
    finally:
        sync.REPO_ROOT = original_root


def test_sync_updates_generic_releases_link(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    readme = tmp_path / "README.md"
    readme.write_text(
        "[v1.0.0](https://github.com/opsdevcode/repave/releases)\n",
        encoding="utf-8",
    )
    roadmap = tmp_path / "docs" / "roadmap.md"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text("**Current release:** v1.0.0\n", encoding="utf-8")
    portal = tmp_path / "docs" / "portal-design.md"
    portal.write_text("(engine tags through **v1.0.0**).\n", encoding="utf-8")
    demo = tmp_path / "docs" / "demo-verification.md"
    demo.write_text("Last (engine v1.0.0, blueprint\n", encoding="utf-8")
    op_ga = tmp_path / "docs" / "operator-ga.md"
    op_ga.write_text("(engine **v1.0.0**).\n", encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        changed = sync.apply_sync("2.5.0")
        assert len(changed) == 5
        assert "[v2.5.0](https://github.com/opsdevcode/repave/releases/tag/v2.5.0)" in (
            readme.read_text(encoding="utf-8")
        )
        assert "engine v2.5.0," in demo.read_text(encoding="utf-8")
        assert "engine **v2.5.0**" in op_ga.read_text(encoding="utf-8")
    finally:
        sync.REPO_ROOT = original_root


def test_sync_check_fails_when_stale(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    roadmap = tmp_path / "docs" / "roadmap.md"
    readme = tmp_path / "README.md"
    portal = tmp_path / "docs" / "portal-design.md"
    roadmap.parent.mkdir(parents=True, exist_ok=True)
    portal.parent.mkdir(parents=True, exist_ok=True)
    roadmap.write_text("**Current release:** v1.0.0\n", encoding="utf-8")
    readme.write_text(
        "[v1.0.0](https://github.com/opsdevcode/repave/releases/tag/v1.0.0)\n",
        encoding="utf-8",
    )
    portal.write_text("(engine tags through **v1.0.0**).\n", encoding="utf-8")
    demo = tmp_path / "docs" / "demo-verification.md"
    demo.write_text("(engine v1.0.0, blueprint\n", encoding="utf-8")
    op_ga = tmp_path / "docs" / "operator-ga.md"
    op_ga.write_text("(engine **v1.0.0**).\n", encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        with pytest.raises(SystemExit, match="out of date"):
            sync.apply_sync("9.9.9", check=True)
    finally:
        sync.REPO_ROOT = original_root
