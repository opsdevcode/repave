"""Object storage for async run artifacts (service decomposition Phase 2)."""

from __future__ import annotations

import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ArtifactStoreSettings:
    uri: str | None = None


def load_artifact_store_settings(repo_root: Path) -> ArtifactStoreSettings:
    from repave_engine.settings import _load_config_file

    uri = os.environ.get("REPAVE_ARTIFACT_STORE_URI", "").strip()
    if not uri:
        block = _load_config_file(repo_root / "repave.config.yaml").get("durability")
        if isinstance(block, dict):
            raw = block.get("artifact_store_uri")
            if raw is not None:
                uri = str(raw).strip()
    return ArtifactStoreSettings(uri=uri or None)


class ArtifactStore(ABC):
    @abstractmethod
    def local_staging_dir(self, repo_root: Path, run_id: str) -> Path:
        """Writable directory for gate staging during a run."""

    @abstractmethod
    def persist_run_artifacts(self, run_id: str, staging_dir: Path) -> dict[str, str]:
        """Return fields to merge into the stored run result after a successful run."""

    @abstractmethod
    def materialize_run_artifacts(self, stored: dict[str, object]) -> Path | None:
        """Resolve stored result payload to a local directory for portal rehydrate."""


class LocalArtifactStore(ArtifactStore):
    def local_staging_dir(self, repo_root: Path, run_id: str) -> Path:
        path = repo_root / "data" / "async-run-artifacts" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def persist_run_artifacts(self, run_id: str, staging_dir: Path) -> dict[str, str]:
        _ = run_id
        return {"artifact_root": str(staging_dir)}

    def materialize_run_artifacts(self, stored: dict[str, object]) -> Path | None:
        raw = stored.get("artifact_root") or stored.get("output_dir")
        if raw is None:
            return None
        path = Path(str(raw))
        return path if path.is_dir() else None


class S3ArtifactStore(ArtifactStore):
    def __init__(self, bucket: str, prefix: str) -> None:
        self._bucket = bucket
        self._prefix = prefix.rstrip("/")

    def _run_prefix(self, run_id: str) -> str:
        base = f"{self._prefix}/runs/{run_id}" if self._prefix else f"runs/{run_id}"
        return base.rstrip("/")

    def local_staging_dir(self, repo_root: Path, run_id: str) -> Path:
        path = repo_root / "data" / "async-run-artifacts" / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def persist_run_artifacts(self, run_id: str, staging_dir: Path) -> dict[str, str]:
        import boto3

        client = boto3.client("s3")
        prefix = self._run_prefix(run_id)
        for file_path in staging_dir.rglob("*"):
            if not file_path.is_file():
                continue
            rel = file_path.relative_to(staging_dir).as_posix()
            key = f"{prefix}/{rel}" if rel else prefix
            client.upload_file(str(file_path), self._bucket, key)
        uri = f"s3://{self._bucket}/{prefix}"
        return {"artifact_uri": uri}

    def materialize_run_artifacts(self, stored: dict[str, object]) -> Path | None:
        uri_raw = stored.get("artifact_uri")
        if isinstance(uri_raw, str) and uri_raw.startswith("s3://"):
            return self._download_tree(uri_raw)
        raw = stored.get("artifact_root") or stored.get("output_dir")
        if raw is None:
            return None
        path = Path(str(raw))
        return path if path.is_dir() else None

    def _download_tree(self, uri: str) -> Path | None:
        import boto3

        parsed = urlparse(uri)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/").rstrip("/")
        if not bucket or not prefix:
            return None

        client = boto3.client("s3")
        temp_dir = Path(tempfile.mkdtemp(prefix="repave-artifact-"))
        paginator = client.get_paginator("list_objects_v2")
        found = False
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/"):
            for obj in page.get("Contents", []):
                key = str(obj.get("Key", ""))
                if not key or key.endswith("/"):
                    continue
                rel = key[len(prefix) + 1 :]
                if not rel:
                    continue
                found = True
                dest = temp_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(dest))
        if not found:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
        return temp_dir


def build_artifact_store(settings: ArtifactStoreSettings) -> ArtifactStore:
    uri = settings.uri
    if uri and uri.startswith("s3://"):
        parsed = urlparse(uri)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip("/")
        if not bucket:
            raise ValueError(f"invalid artifact store URI (missing bucket): {uri!r}")
        return S3ArtifactStore(bucket, prefix)
    return LocalArtifactStore()


def resolve_artifact_store(repo_root: Path) -> ArtifactStore:
    return build_artifact_store(load_artifact_store_settings(repo_root))
