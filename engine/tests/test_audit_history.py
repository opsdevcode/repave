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


def test_audit_entry_activity_labels_prefer_module_name() -> None:
    from repave_engine.audit_history import AuditHistoryEntry

    entry = AuditHistoryEntry(
        timestamp="2026-01-01T00:00:00+00:00",
        event="generation",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.12.0",
        module_name="vpc-demo",
        dry_run=False,
        gates_outcome="passed",
        acting_user="alice",
        repository_url="https://github.com/opsdevcode/tf-aws-vpc-demo",
        extra={"artifact_version": "0.1.0"},
    )
    assert entry.activity_artifact_name() == "vpc-demo"
    assert entry.activity_version_label() == "v0.1.0"
    assert entry.activity_blueprint_pin() == "terraform-module-generic@0.12.0"
    assert entry.activity_href() == "/services/opsdevcode-tf-aws-vpc-demo"


def test_audit_entry_activity_labels_fall_back_to_repo_slug() -> None:
    from repave_engine.audit_history import AuditHistoryEntry

    entry = AuditHistoryEntry(
        timestamp="2026-01-01T00:00:00+00:00",
        event="generation",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.12.0",
        module_name="terraform-module-generic",
        dry_run=True,
        gates_outcome="passed",
        acting_user="bob",
        repository_url="https://github.com/acme/tf-aws-vpc-demo",
        extra={},
    )
    assert entry.activity_artifact_name() == "tf-aws-vpc-demo"
    assert entry.activity_version_label() is None


def test_audit_entry_activity_outcome_publish_failed() -> None:
    from repave_engine.audit_history import AuditHistoryEntry

    entry = AuditHistoryEntry(
        timestamp="2026-01-01T00:00:00+00:00",
        event="generation",
        blueprint_name="terraform-module-generic",
        blueprint_version="0.12.0",
        module_name="tf-aws-eks",
        dry_run=False,
        gates_outcome="passed",
        acting_user="alice",
        repository_url="https://github.com/opsdevcode/tf-aws-eks",
        extra={"publish_succeeded": False, "run_id": "run-123"},
    )
    assert entry.activity_outcome_failed() is True
    assert entry.activity_outcome_label() == "Publish failed"
    assert entry.activity_run_href() == "/runs/run-123/result"
