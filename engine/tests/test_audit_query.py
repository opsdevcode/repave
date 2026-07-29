from __future__ import annotations

import json
from pathlib import Path

from repave_engine.audit import AuditRecord
from repave_engine.audit_history import AuditQueryFilters, query_audit_entries


def _append(
    path: Path,
    *,
    blueprint: str,
    user: str,
    outcome: str,
    module: str,
    ts: str,
) -> None:
    record = AuditRecord(
        event="generation",
        blueprint_name=blueprint,
        blueprint_version="0.1.0",
        module_name=module,
        dry_run=True,
        gates_outcome=outcome,
        repository_url=None,
        acting_user=user,
    )
    payload = record.to_dict()
    payload["timestamp"] = ts
    line = json.dumps(payload, separators=(",", ":"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def test_query_audit_filters_blueprint_and_user(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _append(
        path,
        blueprint="terraform-module-generic",
        user="alice",
        outcome="passed",
        module="mod-a",
        ts="2026-01-02T10:00:00+00:00",
    )
    _append(
        path,
        blueprint="helm-chart-generic",
        user="bob",
        outcome="failed",
        module="mod-b",
        ts="2026-01-03T10:00:00+00:00",
    )
    result = query_audit_entries(
        path,
        AuditQueryFilters(
            blueprint_name="terraform-module-generic",
            acting_user="alice",
            limit=10,
        ),
    )
    assert result.total == 1
    assert result.entries[0].module_name == "mod-a"


def test_query_audit_time_range(tmp_path: Path) -> None:
    path = tmp_path / "audit.jsonl"
    _append(
        path,
        blueprint="terraform-module-generic",
        user="alice",
        outcome="passed",
        module="early",
        ts="2026-01-01T00:00:00+00:00",
    )
    _append(
        path,
        blueprint="terraform-module-generic",
        user="alice",
        outcome="passed",
        module="late",
        ts="2026-02-01T00:00:00+00:00",
    )
    result = query_audit_entries(
        path,
        AuditQueryFilters(
            since="2026-01-15T00:00:00+00:00",
            limit=10,
        ),
    )
    assert result.total == 1
    assert result.entries[0].module_name == "late"
