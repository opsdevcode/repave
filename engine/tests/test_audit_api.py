from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app
from repave_engine.audit import AuditRecord, append_audit_record


def test_api_audit_query_json(repo_root, output_config, tmp_path: Path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("REPAVE_AUDIT_FILE", str(audit_path))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.11.0",
            module_name="tf-filter-test",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="audit-tester",
        ),
        repo_root=repo_root,
    )
    response = client.get(
        "/api/v1/audit",
        params={"blueprint": "terraform-module-generic", "acting_user": "audit-tester"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(row["module_name"] == "tf-filter-test" for row in body["entries"])


def test_activity_page_filter_form(repo_root, output_config, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("REPAVE_AUDIT_FILE", str(tmp_path / "audit.jsonl"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/activity", params={"blueprint": "terraform-module-generic"})
    assert_surface_moved(response, "activity")
