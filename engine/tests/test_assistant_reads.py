"""Tests for assistant read-only fleet/drift/audit tools."""

from __future__ import annotations

import json
from pathlib import Path

from helpers import make_blueprint
from repave_engine.assistant import resolve_catalog_intent
from repave_engine.assistant_reads import collect_assistant_reads, reads_allowed
from repave_engine.fleet import FleetEntry, register_repo


def _write_config(root: Path) -> Path:
    fleet = root / "fleet" / "registry.jsonl"
    audit = root / "audit" / "generation.jsonl"
    fleet.parent.mkdir(parents=True)
    audit.parent.mkdir(parents=True)
    (root / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  assistant:\n    enabled: true\n"
        "fleet:\n  enabled: true\n  file: fleet/registry.jsonl\n"
        "audit:\n  enabled: true\n  file: audit/generation.jsonl\n",
        encoding="utf-8",
    )
    return fleet


def test_reads_denied_when_auth_role_cannot_view() -> None:
    assert reads_allowed(role=None, auth_enabled=True) is False
    assert reads_allowed(role="unknown", auth_enabled=True) is False
    assert reads_allowed(role="viewer", auth_enabled=True) is True
    assert reads_allowed(role=None, auth_enabled=False) is True


def test_denied_role_gets_no_fleet_rows(tmp_path: Path) -> None:
    fleet = _write_config(tmp_path)
    register_repo(
        fleet,
        FleetEntry(
            repo_url="https://github.com/acme/tf-vpc.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
            owner="platform",
        ),
        repo_root=tmp_path,
    )
    blueprint = make_blueprint(tmp_path, name="terraform-module-generic")
    hits, tools = collect_assistant_reads(
        tmp_path,
        intent="fleet drift behind terraform",
        blueprints=(blueprint,),
        role=None,
        auth_enabled=True,
    )
    assert hits == ()
    assert tools == ()


def test_allowed_role_cites_fleet_and_drift(tmp_path: Path) -> None:
    fleet = _write_config(tmp_path)
    register_repo(
        fleet,
        FleetEntry(
            repo_url="https://github.com/acme/tf-vpc.git",
            blueprint_name="terraform-module-generic",
            blueprint_version="0.9.0",
            standard_version="9.9.9",
            owner="platform",
        ),
        repo_root=tmp_path,
    )
    blueprint = make_blueprint(tmp_path, name="terraform-module-generic")
    hits, tools = collect_assistant_reads(
        tmp_path,
        intent="show fleet drift behind pins",
        blueprints=(blueprint,),
        role="viewer",
        auth_enabled=True,
    )
    assert "fleet.reads" in tools
    assert "fleet.drift" in tools
    sources = {item.source for item in hits}
    assert any(item.startswith("fleet:") for item in sources)
    assert any(item.startswith("fleet-drift:") for item in sources)


def test_audit_history_hits_when_intent_asks(tmp_path: Path) -> None:
    _write_config(tmp_path)
    audit = tmp_path / "audit" / "generation.jsonl"
    audit.write_text(
        json.dumps(
            {
                "event": "generation",
                "blueprint_name": "terraform-module-generic",
                "blueprint_version": "0.0.1",
                "module_name": "vpc-core",
                "dry_run": True,
                "gates_outcome": "failed",
                "timestamp": "2026-08-20T00:00:00Z",
                "acting_user": "tester",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    blueprint = make_blueprint(tmp_path, name="terraform-module-generic")
    hits, tools = collect_assistant_reads(
        tmp_path,
        intent="gate history failed outcomes",
        blueprints=(blueprint,),
        role="viewer",
        auth_enabled=True,
    )
    assert "audit.history" in tools
    assert any(item.tool_id == "audit.history" for item in hits)
    assert any("failed" in item.excerpt for item in hits)


def test_resolve_catalog_intent_skips_reads_when_role_denied(repo_root: Path) -> None:
    result = resolve_catalog_intent(
        repo_root,
        intent="fleet drift and gate history",
        role=None,
        auth_enabled=True,
    )
    assert result.reads == ()
    assert "fleet.reads" not in result.tools
