from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.artifact_store import (
    LocalArtifactStore,
    S3ArtifactStore,
    build_artifact_store,
    load_artifact_store_settings,
)


def test_load_artifact_store_settings_from_env(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_ARTIFACT_STORE_URI", "s3://my-bucket/prefix")
    settings = load_artifact_store_settings(repo_root)
    assert settings.uri == "s3://my-bucket/prefix"


def test_build_artifact_store_local() -> None:
    store = build_artifact_store(load_artifact_store_settings(Path("/tmp")))
    assert isinstance(store, LocalArtifactStore)


def test_local_artifact_store_roundtrip(repo_root: Path, tmp_path: Path) -> None:
    store = LocalArtifactStore()
    staging = store.local_staging_dir(repo_root, "run-abc")
    (staging / "main.tf").write_text("# stub\n", encoding="utf-8")
    fields = store.persist_run_artifacts("run-abc", staging)
    materialized = store.materialize_run_artifacts(fields)
    assert materialized is not None
    assert (materialized / "main.tf").is_file()


def test_s3_run_prefix() -> None:
    store = S3ArtifactStore("bucket", "prod")
    assert store._run_prefix("run-1") == "prod/runs/run-1"
    root = S3ArtifactStore("bucket", "")
    assert root._run_prefix("run-1") == "runs/run-1"


def test_materialize_prefers_artifact_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    store = S3ArtifactStore("bucket", "prod")
    downloaded = Path("/tmp/repave-artifact-test")
    monkeypatch.setattr(store, "_download_tree", lambda uri: downloaded)
    path = store.materialize_run_artifacts(
        {"artifact_uri": "s3://bucket/prod/runs/run-1", "artifact_root": "/gone"}
    )
    assert path == downloaded
