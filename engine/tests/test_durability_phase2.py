from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.audit_history import (
    AuditQueryFilters,
    query_audit_entries,
    read_recent_audit_entries,
)
from repave_engine.durability_store import load_durability_store_settings
from repave_engine.fleet import FleetEntry, read_fleet, register_repo
from repave_engine.run_queue import RunQueue, RunQueueConfig, build_run_queue
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.settings import OutputConfig
from repave_engine.sql_store import load_database_config, parse_database_url


def _write_durability_config(
    repo_root: Path,
    db_rel: str,
    *,
    export_jsonl: bool = True,
) -> None:
    (repo_root / "repave.config.yaml").write_text(
        f"""
durability:
  async_generation: true
  database_url: sqlite:///{db_rel}
  export_jsonl: {"true" if export_jsonl else "false"}
audit:
  enabled: true
  file: data/audit/generation.jsonl
fleet:
  enabled: true
  file: data/fleet/registry.jsonl
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_parse_sqlite_database_url(tmp_path: Path) -> None:
    cfg = parse_database_url("sqlite:///data/repave.sqlite", repo_root=tmp_path)
    assert cfg.sqlite_path == (tmp_path / "data" / "repave.sqlite").resolve()


def test_parse_postgresql_database_url(tmp_path: Path) -> None:
    dsn = "postgresql://repave:secret@postgres.repave.svc:5432/repave"
    cfg = parse_database_url(dsn, repo_root=tmp_path)
    assert cfg.dialect == "postgresql"
    assert cfg.postgres_dsn == dsn
    assert cfg.sqlite_path is None


def test_database_url_env_overrides_config_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_durability_config(tmp_path, "data/config.sqlite")
    monkeypatch.setenv("REPAVE_DATABASE_URL", "sqlite:///data/env.sqlite")
    cfg = load_database_config(tmp_path)
    assert cfg is not None
    assert cfg.sqlite_path == (tmp_path / "data" / "env.sqlite").resolve()


def test_audit_and_fleet_use_sql_store(tmp_path: Path) -> None:
    _write_durability_config(tmp_path, "data/repave.sqlite")
    settings = load_durability_store_settings(tmp_path)
    assert settings is not None

    audit_path = tmp_path / "data" / "audit" / "generation.jsonl"
    fleet_path = tmp_path / "data" / "fleet" / "registry.jsonl"

    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.1.0",
            module_name="demo",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="tester",
        ),
        repo_root=tmp_path,
    )
    entries = read_recent_audit_entries(audit_path, limit=5, repo_root=tmp_path)
    assert len(entries) == 1
    assert entries[0].blueprint_name == "terraform-module-generic"
    assert audit_path.is_file()

    register_repo(
        fleet_path,
        FleetEntry(
            repo_url="https://github.com/acme/mod.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
        ),
        repo_root=tmp_path,
    )
    fleet = read_fleet(fleet_path, repo_root=tmp_path)
    assert len(fleet) == 1
    assert fleet[0].repo_url == "https://github.com/acme/mod"


def test_export_jsonl_false_writes_sql_only(tmp_path: Path) -> None:
    _write_durability_config(tmp_path, "data/repave.sqlite", export_jsonl=False)
    audit_path = tmp_path / "data" / "audit" / "generation.jsonl"
    fleet_path = tmp_path / "data" / "fleet" / "registry.jsonl"

    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.1.0",
            module_name="demo",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="tester",
        ),
        repo_root=tmp_path,
    )
    assert not audit_path.exists()

    register_repo(
        fleet_path,
        FleetEntry(
            repo_url="https://github.com/acme/mod.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
        ),
        repo_root=tmp_path,
    )
    assert not fleet_path.exists()
    assert len(read_fleet(fleet_path, repo_root=tmp_path)) == 1


def test_audit_query_reads_from_sql_store(tmp_path: Path) -> None:
    _write_durability_config(tmp_path, "data/repave.sqlite", export_jsonl=False)
    audit_path = tmp_path / "data" / "audit" / "generation.jsonl"
    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.1.0",
            module_name="demo",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="tester",
        ),
        repo_root=tmp_path,
    )
    result = query_audit_entries(
        audit_path,
        AuditQueryFilters(limit=10, offset=0),
        repo_root=tmp_path,
    )
    assert result.total == 1
    assert result.entries[0].acting_user == "tester"


def test_build_run_queue_uses_unified_database(tmp_path: Path) -> None:
    _write_durability_config(tmp_path, "data/repave.sqlite")
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = build_run_queue(
        tmp_path,
        output,
        RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4, external_workers=True),
    )
    try:
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="tester",
        )
        assert record.run_id
        db_path = tmp_path / "data" / "repave.sqlite"
        assert db_path.is_file()
        settings = load_durability_store_settings(tmp_path)
        assert settings is not None
        store = RunStore(settings.database)
        stored = store.get(record.run_id)
        assert stored is not None
        assert stored.status == RunStatus.QUEUED
    finally:
        queue.close()


def test_external_worker_claim_and_process(tmp_path: Path) -> None:
    from unittest.mock import patch

    _write_durability_config(tmp_path, "data/repave.sqlite")
    db_cfg = parse_database_url("sqlite:///data/repave.sqlite", repo_root=tmp_path)
    store = RunStore(db_cfg)
    output = OutputConfig(github_org="example", modules_root=tmp_path / "modules")
    queue = RunQueue(
        repo_root=tmp_path,
        output_config=output,
        store=store,
        config=RunQueueConfig(max_concurrent_runs=1, queue_max_depth=4, external_workers=True),
    )
    fake = {
        "blueprint": "terraform-module-generic",
        "gates_outcome": "passed",
        "gates_passed": True,
        "gates": [],
        "rendered_files": 0,
        "output_dir": str(tmp_path / "out"),
    }
    with patch("repave_engine.run_queue.run_generate_api", return_value=fake):
        record = queue.submit(
            blueprint_name="terraform-module-generic",
            inputs={"module_name": "demo"},
            dry_run=True,
            acting_user="worker",
        )
        assert store.get(record.run_id).status == RunStatus.QUEUED
        assert queue.claim_and_process() is True
        terminal = store.get(record.run_id)
        assert terminal is not None
        assert terminal.status == RunStatus.SUCCEEDED
    queue.close()


def test_postgresql_connect_requires_psycopg(tmp_path: Path) -> None:
    psycopg = pytest.importorskip("psycopg", reason="postgres extra not installed")
    from repave_engine.sql_store import connect

    cfg = parse_database_url(
        "postgresql://repave:secret@127.0.0.1:5432/repave",
        repo_root=tmp_path,
    )
    with pytest.raises(psycopg.OperationalError):
        connect(cfg).close()
