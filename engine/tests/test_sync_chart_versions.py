from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_sync_module(repo_root: Path):
    path = repo_root / "scripts" / "sync_chart_versions.py"
    spec = importlib.util.spec_from_file_location("sync_chart_versions", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["sync_chart_versions"] = module
    spec.loader.exec_module(module)
    return module


def test_sync_updates_chart_versions(repo_root: Path, tmp_path: Path) -> None:
    sync = _load_sync_module(repo_root)
    engine_chart = tmp_path / "deploy/k8s/chart/Chart.yaml"
    operator_chart = tmp_path / "deploy/k8s/operator-chart/Chart.yaml"
    for path in (engine_chart, operator_chart):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            'apiVersion: v2\nname: test\nversion: 0.1.0\nappVersion: "1.0.0"\n',
            encoding="utf-8",
        )

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        changed = sync.apply_sync("2.15.0")
        assert len(changed) == 2
        for path in (engine_chart, operator_chart):
            text = path.read_text(encoding="utf-8")
            assert "version: 2.15.0" in text
            assert 'appVersion: "2.15.0"' in text
    finally:
        sync.REPO_ROOT = original_root


def test_sync_check_fails_when_stale(repo_root: Path, tmp_path: Path) -> None:
    import pytest

    sync = _load_sync_module(repo_root)
    engine_chart = tmp_path / "deploy/k8s/chart/Chart.yaml"
    operator_chart = tmp_path / "deploy/k8s/operator-chart/Chart.yaml"
    for path in (engine_chart, operator_chart):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            'apiVersion: v2\nname: test\nversion: 0.1.0\nappVersion: "1.0.0"\n',
            encoding="utf-8",
        )

    original_root = sync.REPO_ROOT
    try:
        sync.REPO_ROOT = tmp_path
        with pytest.raises(SystemExit, match="out of date"):
            sync.apply_sync("9.9.9", check=True)
    finally:
        sync.REPO_ROOT = original_root


def test_release_workflow_commits_all_chart_targets(repo_root: Path) -> None:
    sync = _load_sync_module(repo_root)
    workflow = (repo_root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "sync_chart_versions.py" in workflow
    for rel_path in sync.CHART_PATHS:
        assert rel_path in workflow, f"release.yml must git add {rel_path}"
