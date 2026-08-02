from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from repave_engine.environment_record import (
    EnvironmentRecord,
    entity_id_for_environment,
    resolve_ttl_hours,
)
from repave_engine.environment_registry import (
    EnvironmentRegistryError,
    build_environment_record_from_vend,
    read_environments,
    register_environment,
    register_environment_from_vend,
)
from repave_engine.environment_vend import EnvironmentVendResult


def _vend_result(**overrides: object) -> EnvironmentVendResult:
    base = EnvironmentVendResult(
        kind="environment_vend",
        blueprint="terraform-environment-stack",
        blueprint_version="0.4.0",
        gates_outcome="passed",
        gates_passed=True,
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        owner="platform",
        env_class="sandbox",
        pull_request_url="https://github.com/acme/gitops/pull/7",
        pull_request_number=7,
        draft=False,
        detail="Opened pull request",
    )
    return EnvironmentVendResult(**{**base.__dict__, **overrides})


def test_entity_id_for_environment() -> None:
    assert entity_id_for_environment(cloud_provider="aws", stack_name="sandbox-alice") == (
        "env-aws-sandbox-alice"
    )


def test_resolve_ttl_hours_prefers_class_override() -> None:
    hours = resolve_ttl_hours(
        "sandbox",
        default_ttl_hours=0,
        ttl_hours_by_class=(("sandbox", 168), ("prod", 720)),
    )
    assert hours == 168


def test_register_then_read_environment(tmp_path: Path) -> None:
    registry = tmp_path / "environments" / "registry.jsonl"
    record = EnvironmentRecord(
        stack_name="sandbox-alice",
        entity_id="env-aws-sandbox-alice",
        cloud_provider="aws",
        environment_tier="dev",
        owner="platform",
        env_class="sandbox",
        blueprint_name="terraform-environment-stack",
        blueprint_version="0.4.0",
        gitops_repo="https://github.com/acme/gitops",
        gitops_path="environments/sandbox-alice",
        git_branch="repave/environment/sandbox-alice-dev",
        pull_request_url="https://github.com/acme/gitops/pull/7",
        pull_request_number=7,
        gates_outcome="passed",
        source_entity_id="acme-tf-live",
        run_id="run-1",
        vended_by="tester",
        vended_at="2026-08-02T12:00:00+00:00",
        expires_at="2026-08-09T12:00:00+00:00",
        status="active",
    )
    register_environment(registry, record)
    entries = read_environments(registry)
    assert len(entries) == 1
    assert entries[0].entity_id == "env-aws-sandbox-alice"
    assert entries[0].gitops_path == "environments/sandbox-alice"


def test_build_environment_record_from_vend_sets_expiry() -> None:
    record = build_environment_record_from_vend(
        vend_result=_vend_result(),
        payload={
            "entity_id": "acme-tf-live",
            "inputs": {
                "stack_name": "sandbox-alice",
                "description": "Alice sandbox",
                "cloud_provider": "aws",
                "environment": "dev",
            },
        },
        run_id="run-abc",
        acting_user="tester",
        ttl_hours=168,
    )
    assert record.entity_id == "env-aws-sandbox-alice"
    assert record.status == "active"
    assert record.expires_at
    expires = datetime.fromisoformat(record.expires_at)
    now = datetime.now(timezone.utc)
    assert expires > now + timedelta(hours=167)


def test_register_environment_from_vend_writes_jsonl(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    record = register_environment_from_vend(
        registry,
        vend_result=_vend_result(draft=True),
        payload={
            "entity_id": "acme-tf-live",
            "inputs": {
                "stack_name": "sandbox-alice",
                "description": "Alice sandbox",
                "cloud_provider": "aws",
                "environment": "dev",
            },
        },
        run_id="run-abc",
        acting_user="tester",
        default_ttl_hours=0,
        ttl_hours_by_class=(("sandbox", 48),),
    )
    assert record.status == "pending"
    assert read_environments(registry)[0].stack_name == "sandbox-alice"
    line = registry.read_text(encoding="utf-8").strip()
    payload = json.loads(line)
    assert payload["event"] == "register"
    assert payload["entity_id"] == "env-aws-sandbox-alice"


def test_register_requires_stack_name() -> None:
    with pytest.raises(EnvironmentRegistryError, match="stack_name"):
        build_environment_record_from_vend(
            vend_result=_vend_result(),
            payload={"inputs": {}},
            run_id="run-abc",
            acting_user="tester",
            ttl_hours=None,
        )
