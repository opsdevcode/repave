from __future__ import annotations

import logging
from email.utils import parsedate_to_datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.api_deprecation import V1_DEPRECATION_HEADERS, V1_SUNSET_HTTP
from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.settings import CONFIG_API_VERSION, _load_config_file


def test_api_v1_responses_include_deprecation_headers(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/health")
    assert response.status_code == 200
    for key in V1_DEPRECATION_HEADERS:
        assert key not in response.headers

    v1 = client.get("/api/v1/catalog/entities")
    assert v1.status_code == 200
    for key, value in V1_DEPRECATION_HEADERS.items():
        assert v1.headers.get(key) == value


def test_v1_sunset_matches_published_migration_date() -> None:
    sunset = parsedate_to_datetime(V1_SUNSET_HTTP)
    assert sunset.year == 2027
    assert sunset.month == 8
    assert sunset.day == 1


def test_api_v2_audit_query_parity(repo_root, output_config, tmp_path, monkeypatch) -> None:
    audit_path = tmp_path / "audit.jsonl"
    monkeypatch.setenv("REPAVE_AUDIT_FILE", str(audit_path))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    append_audit_record(
        audit_path,
        AuditRecord(
            event="generation",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.11.0",
            module_name="v2-audit-test",
            dry_run=True,
            gates_outcome="passed",
            repository_url=None,
            acting_user="audit-tester",
        ),
        repo_root=repo_root,
    )
    response = client.get(
        "/api/v2/audit",
        params={"blueprint": "terraform-module-generic", "acting_user": "audit-tester"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(row["module_name"] == "v2-audit-test" for row in body["entries"])


def test_service_mode_requires_database_url(
    repo_root, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REPAVE_SERVICE_MODE", "1")
    monkeypatch.setenv("REPAVE_SESSION_SECRET", "test-secret")
    monkeypatch.setenv("REPAVE_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_ID", "client")
    monkeypatch.setenv("REPAVE_OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setenv("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")

    with pytest.raises(RuntimeError, match="database_url"):
        create_app(repo_root=repo_root, output_config=output_config)


def test_config_missing_api_version_warns(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    config_path = tmp_path / "repave.config.yaml"
    config_path.write_text("output:\n  github_org: example\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        _load_config_file(config_path)
    assert CONFIG_API_VERSION in caplog.text


def test_config_unknown_api_version_rejected(tmp_path: Path) -> None:
    config_path = tmp_path / "repave.config.yaml"
    config_path.write_text("apiVersion: repave.dev/v99\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported apiVersion"):
        _load_config_file(config_path)
