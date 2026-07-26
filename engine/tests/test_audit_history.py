from __future__ import annotations

import json
from pathlib import Path

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.audit_history import read_recent_audit_entries


def test_read_recent_audit_entries_newest_first(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    for idx, name in enumerate(("alpha", "beta", "gamma")):
        append_audit_record(
            path,
            AuditRecord(
                event="generation",
                blueprint_name=name,
                blueprint_version="0.1.0",
                module_name=f"mod-{idx}",
                dry_run=True,
                gates_outcome="passed",
                repository_url=None,
                acting_user="tester",
            ),
        )
    entries = read_recent_audit_entries(path, limit=2)
    assert len(entries) == 2
    assert entries[0].blueprint_name == "gamma"
    assert entries[1].blueprint_name == "beta"


def test_read_recent_audit_entries_skips_non_generation(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    path.write_text(
        json.dumps({"event": "other", "blueprint_name": "x"}) + "\n",
        encoding="utf-8",
    )
    append_audit_record(
        path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.11.0",
            module_name="tf-aws-demo",
            dry_run=False,
            gates_outcome="failed",
            repository_url=None,
            acting_user="alice",
        ),
    )
    entries = read_recent_audit_entries(path)
    assert len(entries) == 1
    assert entries[0].blueprint_name == "terraform-module-generic"
    assert entries[0].gates_outcome == "failed"
