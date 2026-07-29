from __future__ import annotations

from pathlib import Path

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.audit_history import read_recent_audit_entries
from repave_engine.durability_store import load_durability_store_settings
from repave_engine.fleet import FleetEntry, read_fleet, register_repo
from repave_engine.run_queue import RunQueue, RunQueueConfig
from repave_engine.run_store import RunStatus, RunStore
from repave_engine.settings import OutputConfig
from repave_engine.sql_store import parse_database_url


def _write_durability_config(repo_root: Path, db_rel: str) -> None:
    (repo_root / "repave.config.yaml").write_text(
        f"""
durability:
  async_generation: true
  database_url: sqlite:///{db_rel}
  export_jsonl: true
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
