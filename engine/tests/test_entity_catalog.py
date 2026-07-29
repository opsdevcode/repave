from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.entity_catalog import (
    build_catalog_entities,
    build_scorecard,
    entity_id_for_repo_url,
    find_catalog_entity,
    observability_embed_url,
)
from repave_engine.fleet import FleetEntry
from repave_engine.fleet_operator_status import FleetOperatorStatus


def test_entity_id_for_repo_url_stable() -> None:
    assert entity_id_for_repo_url("https://github.com/acme/tf-vpc.git") == "acme-tf-vpc"


def test_build_scorecard_passes_with_fleet_and_audit(tmp_path: Path) -> None:
    repo = tmp_path / "tf-vpc"
    repo.mkdir()
    (repo / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    (repo / "RUNBOOK.md").write_text("# Run", encoding="utf-8")
    fleet = FleetEntry(
        repo_url="https://github.com/acme/tf-vpc",
        blueprint_name="terraform-module-generic",
        blueprint_version="1.0.0",
        standard_source="standards/terraform-standards",
        standard_version="2.0.0",
    )
    audit = AuditHistoryEntry(
        timestamp="2026-01-02T03:04:05Z",
        event="generation",
        module_name="tf-vpc",
        blueprint_name="terraform-module-generic",
        blueprint_version="1.0.0",
        gates_outcome="passed",
        dry_run=True,
        acting_user="tester@example.com",
        repository_url="https://github.com/acme/tf-vpc",
        extra={},
    )
    dims = build_scorecard(
        repo_dir=repo,
        fleet_entry=fleet,
        operator=FleetOperatorStatus(repo_url=fleet.repo_url, phase="Ready", message="ok"),
        audit=audit,
    )
    levels = {dim.key: dim.level for dim in dims}
    assert levels["pins"] == "pass"
    assert levels["operator"] == "pass"
    assert levels["provenance"] == "pass"
    assert levels["runbook"] == "pass"
    assert levels["gates"] == "pass"


def test_build_catalog_merges_fleet_and_local(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    local_only = modules_root / "local-svc"
    local_only.mkdir()
    (local_only / "repave.yaml").write_text(
        yaml.dump({"spec": {"blueprint": "terraform-module-generic"}}),
        encoding="utf-8",
    )
    (local_only / "catalog-info.yaml").write_text(
        yaml.dump(
            {
                "metadata": {"name": "local-svc"},
                "spec": {"type": "service", "lifecycle": "production", "owner": "team-a"},
            }
        ),
        encoding="utf-8",
    )
    fleet_row = {
        "repo_url": "https://github.com/acme/tf-vpc",
        "blueprint_name": "terraform-module-generic",
        "blueprint_version": "0.9.0",
        "standard_source": "standards/terraform-standards",
        "standard_version": "1.0.0",
        "owner": "platform",
        "manifest_name": "tf-vpc",
        "manifest_namespace": "default",
    }
    fleet_repo = modules_root / "tf-vpc"
    fleet_repo.mkdir()
    (fleet_repo / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")

    entities = build_catalog_entities(
        fleet_rows=[fleet_row],
        modules_root=modules_root,
        operator_by_url={},
    )

    assert len(entities) == 2
    by_name = {item.display_name: item for item in entities}
    assert "local-svc" in by_name
    assert by_name["local-svc"].source == "modules_root"
    matched = find_catalog_entity(entities, entity_id_for_repo_url(fleet_row["repo_url"]))
    assert matched is not None
    assert matched.local_path == fleet_repo


def test_observability_embed_url_formats_placeholders() -> None:
    from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension

    entity = CatalogEntity(
        entity_id="acme-svc",
        display_name="acme-svc",
        repo_url=None,
        local_path=None,
        owner="",
        blueprint_name="",
        blueprint_version="",
        standard_source="",
        standard_version="",
        component_type="service",
        lifecycle="",
        operator_phase="",
        operator_message="",
        remediation_pr_url="",
        manifest_name="",
        manifest_namespace="",
        source="fleet",
        scorecard=(ScorecardDimension("pins", "Pins", "unknown", ""),),
    )
    url = observability_embed_url(
        "https://grafana/d/x?service={name}&id={entity_id}",
        entity,
    )
    assert url == "https://grafana/d/x?service=acme-svc&id=acme-svc"
