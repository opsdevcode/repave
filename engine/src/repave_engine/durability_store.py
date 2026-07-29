"""Resolve durability SQL settings and JSONL export mirrors."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from repave_engine.sql_store import DatabaseConfig, load_database_config, parse_database_url


@dataclass(frozen=True)
class DurabilityStoreSettings:
    """Phase 2 unified SQL store (audit, fleet, runs) plus optional JSONL export."""

    database: DatabaseConfig
    export_jsonl: bool = True
    external_workers: bool = False


def load_durability_store_settings(repo_root: Path) -> DurabilityStoreSettings | None:
    db = load_database_config(repo_root)
    if db is None:
        return None

    from repave_engine.settings import _load_config_file

    export_jsonl = True
    external_workers = False
    block = _load_config_file(repo_root / "repave.config.yaml").get("durability")
    if isinstance(block, dict):
        raw_export = block.get("export_jsonl", True)
        if not isinstance(raw_export, bool):
            raise ValueError("durability.export_jsonl must be a boolean")
        export_jsonl = raw_export
        worker_raw = block.get("worker_mode", "inline")
        if str(worker_raw).strip().lower() in ("external", "kubernetes", "job"):
            external_workers = True

    env_workers = os.environ.get("REPAVE_EXTERNAL_WORKERS", "").strip().lower()
    if env_workers in ("1", "true", "yes"):
        external_workers = True

    return DurabilityStoreSettings(
        database=db,
        export_jsonl=export_jsonl,
        external_workers=external_workers,
    )


def resolve_runs_database(
    repo_root: Path,
    *,
    runs_db: Path,
    store_settings: DurabilityStoreSettings | None,
) -> DatabaseConfig:
    if store_settings is not None:
        return store_settings.database
    return parse_database_url(f"sqlite:///{runs_db}", repo_root=repo_root)
