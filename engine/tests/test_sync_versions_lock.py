from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SAMPLE_LOCK = """\
# comment
engine_version: '1.0.0'
cli_version: '2.24.0'
operator_image: 'ghcr.io/opsdevcode/repave-operator:1.0.0'
corpus_image: 'ghcr.io/opsdevcode/repave-corpus:1.0.0'
portal_image: 'ghcr.io/opsdevcode/repave-engine-portal:1.0.0'
worker_image: 'ghcr.io/opsdevcode/repave-engine:1.0.0'
chart_version: '1.0.0'
"""


def _load_sync_module(repo_root: Path):
    path = repo_root / "scripts" / "sync_versions_lock.py"
    spec = importlib.util.spec_from_file_location("sync_versions_lock", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_versions_lock"] = module
    spec.loader.exec_module(module)
    return module


def test_sync_updates_engine_pins_and_keeps_cli(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    lock_path = tmp_path / "versions.lock"
    lock_path.write_text(SAMPLE_LOCK, encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        changed = sync.apply_sync("2.61.0")
        assert changed == [lock_path]
        text = lock_path.read_text(encoding="utf-8")
        assert "engine_version: '2.61.0'" in text
        assert "cli_version: '2.24.0'" in text
        assert "operator_image: 'ghcr.io/opsdevcode/repave-operator:2.61.0'" in text
        assert "corpus_image: 'ghcr.io/opsdevcode/repave-corpus:2.61.0'" in text
        assert "portal_image: 'ghcr.io/opsdevcode/repave-engine-portal:2.61.0'" in text
        assert "worker_image: 'ghcr.io/opsdevcode/repave-engine:2.61.0'" in text
        assert "chart_version: '2.61.0'" in text
        assert text.startswith("# comment\n")
    finally:
        sync.REPO_ROOT = original_root


def test_sync_accepts_prerelease(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    lock_path = tmp_path / "versions.lock"
    lock_path.write_text(SAMPLE_LOCK, encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        sync.apply_sync("2.61.0-rc.1")
        text = lock_path.read_text(encoding="utf-8")
        assert "engine_version: '2.61.0-rc.1'" in text
        assert "chart_version: '2.61.0-rc.1'" in text
        assert ":2.61.0-rc.1'" in text
    finally:
        sync.REPO_ROOT = original_root


def test_sync_check_fails_when_stale(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    lock_path = tmp_path / "versions.lock"
    lock_path.write_text(SAMPLE_LOCK, encoding="utf-8")

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        with pytest.raises(SystemExit, match="out of date"):
            sync.apply_sync("9.9.9", check=True)
    finally:
        sync.REPO_ROOT = original_root


def test_release_workflow_commits_versions_lock(repo_root: Path) -> None:
    sync = _load_sync_module(repo_root)
    workflow = (repo_root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "sync_versions_lock.py" in workflow
    assert sync.LOCK_REL_PATH in workflow
    prerelease = (repo_root / ".github/workflows/release-prerelease.yml").read_text(
        encoding="utf-8"
    )
    assert "sync_versions_lock.py" in prerelease
    assert sync.LOCK_REL_PATH in prerelease
