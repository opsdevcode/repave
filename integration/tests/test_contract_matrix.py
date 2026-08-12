"""Cross-repo contract checks against versions.lock (ADR 007 Phase 4)."""

from __future__ import annotations

from pathlib import Path

import yaml


def _load_lock() -> dict[str, str]:
    lock_path = Path(__file__).resolve().parents[2] / "versions.lock"
    data = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return {str(k): str(v) for k, v in data.items()}


def test_versions_lock_has_required_keys() -> None:
    lock = _load_lock()
    required = {
        "engine_version",
        "cli_version",
        "operator_image",
        "corpus_image",
        "portal_image",
        "worker_image",
        "chart_version",
    }
    assert required <= set(lock.keys())


def test_engine_version_matches_pyproject() -> None:
    lock = _load_lock()
    engine_pyproject = Path(__file__).resolve().parents[2] / "engine" / "pyproject.toml"
    import tomllib

    data = tomllib.loads(engine_pyproject.read_text(encoding="utf-8"))
    assert lock["engine_version"] == data["project"]["version"]


def test_image_tags_match_engine_version() -> None:
    lock = _load_lock()
    version = lock["engine_version"]
    for key in ("operator_image", "corpus_image", "portal_image", "worker_image"):
        assert lock[key].endswith(f":{version}"), f"{key} tag must match engine_version"
