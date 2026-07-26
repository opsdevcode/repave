from __future__ import annotations

import json
from pathlib import Path

from repave_engine.audit import AuditRecord, append_audit_record


def test_append_audit_record_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    append_audit_record(
        path,
        AuditRecord(
            event="generation",
            blueprint_name="demo",
            blueprint_version="1.0.0",
            module_name="mod",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="tester",
        ),
    )
    line = path.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["blueprint_name"] == "demo"
    assert payload["acting_user"] == "tester"
    assert "timestamp" in payload


def test_load_audit_config_from_file(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "audit:\n  enabled: true\n  file: logs/audit.jsonl\n",
        encoding="utf-8",
    )
    from repave_engine.settings import load_audit_config

    cfg = load_audit_config(tmp_path)
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.file == (tmp_path / "logs/audit.jsonl").resolve()
