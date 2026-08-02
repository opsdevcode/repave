from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.entity_catalog import (
    CatalogEntity,
    ScorecardDimension,
    ScoreLevel,
    build_catalog_entities,
    build_catalog_from_environments,
    build_scorecard,
    entity_id_for_repo_url,
    fetch_remote_entity_docs,
    filter_entities_by_owner,
    find_catalog_entity,
    group_catalog_entities,
    merge_catalog_entities,
    observability_embed_url,
    read_entity_docs,
    rollup_fleet_scorecard,
)
from repave_engine.environment_record import EnvironmentRecord
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
    assert levels["cost"] == "unknown"


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


def test_group_catalog_entities_by_family() -> None:
    def entity(name: str, blueprint: str, component_type: str = "") -> CatalogEntity:
        return CatalogEntity(
            entity_id=name,
            display_name=name,
            repo_url=f"https://github.com/acme/{name}",
            local_path=None,
            owner="platform",
            blueprint_name=blueprint,
            blueprint_version="1.0.0",
            standard_source="standards/terraform-standards",
            standard_version="1.0.0",
            component_type=component_type,
            lifecycle="production",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="",
            manifest_namespace="",
            source="fleet",
            scorecard=(ScorecardDimension("pins", "Pins", "pass", ""),),
        )

    groups = group_catalog_entities(
        [
            entity("tf-vpc", "terraform-module-generic"),
            entity("ansible-role", "ansible-role-generic"),
            entity("my-svc", "", component_type="service"),
        ],
        blueprint_artifact_types={
            "terraform-module-generic": "terraform-module",
            "ansible-role-generic": "ansible-role",
        },
    )
    families = [group.family for group in groups]
    assert families == ["terraform", "ansible", "app"]
    assert groups[0].entities[0].display_name == "tf-vpc"


def test_observability_embed_url_formats_placeholders() -> None:
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


def test_read_entity_docs_includes_upgrade_and_provenance(tmp_path: Path) -> None:
    repo = tmp_path / "svc"
    repo.mkdir()
    (repo / "repave.yaml").write_text("spec:\n  blueprint: x\n", encoding="utf-8")
    (repo / "UPGRADE.md").write_text("# Upgrade\n\nSteps.", encoding="utf-8")
    docs = read_entity_docs(repo)
    assert "upgrade" in docs
    assert "provenance" in docs


def test_rollup_fleet_scorecard_counts_levels() -> None:
    def entity(levels: dict[str, ScoreLevel]) -> CatalogEntity:
        scorecard = tuple(
            ScorecardDimension(key, key.title(), level, "") for key, level in levels.items()
        )
        return CatalogEntity(
            entity_id="x",
            display_name="x",
            repo_url=None,
            local_path=None,
            owner="platform",
            blueprint_name="terraform-module-generic",
            blueprint_version="1.0.0",
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
            scorecard=scorecard,
        )

    rollup = rollup_fleet_scorecard(
        [
            entity({"pins": "pass", "gates": "pass"}),
            entity({"pins": "warn", "gates": "fail"}),
        ]
    )
    assert rollup.entity_count == 2
    pins = next(cell for cell in rollup.dimensions if cell.key == "pins")
    assert pins.pass_count == 1
    assert pins.warn_count == 1
    assert rollup.overall_level == "fail"


def test_filter_entities_by_owner() -> None:
    entities = [
        CatalogEntity(
            entity_id="a",
            display_name="a",
            repo_url=None,
            local_path=None,
            owner="group:platform",
            blueprint_name="",
            blueprint_version="",
            standard_source="",
            standard_version="",
            component_type="",
            lifecycle="",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="",
            manifest_namespace="",
            source="fleet",
            scorecard=(),
        ),
        CatalogEntity(
            entity_id="b",
            display_name="b",
            repo_url=None,
            local_path=None,
            owner="group:payments",
            blueprint_name="",
            blueprint_version="",
            standard_source="",
            standard_version="",
            component_type="",
            lifecycle="",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="",
            manifest_namespace="",
            source="fleet",
            scorecard=(),
        ),
    ]
    filtered = filter_entities_by_owner(entities, "platform")
    assert len(filtered) == 1
    assert filtered[0].entity_id == "a"


def test_fetch_remote_entity_docs(monkeypatch) -> None:
    def fake_fetch(owner: str, repo: str, rel_path: str, token: str) -> str:
        if rel_path == "README.md":
            return "# Remote readme"
        if rel_path == "repave.yaml":
            return "spec:\n  blueprint: remote\n"
        return ""

    monkeypatch.setattr(
        "repave_engine.github_inventory.fetch_github_file_text",
        fake_fetch,
    )
    docs = fetch_remote_entity_docs("https://github.com/acme/tf-vpc", "token")
    assert docs["readme"].startswith("# Remote")
    assert "blueprint" in docs["provenance"]


def test_build_catalog_from_environments() -> None:
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
    entities = build_catalog_from_environments((record,))
    assert len(entities) == 1
    entity = entities[0]
    assert entity.source == "environment"
    assert entity.component_type == "environment"
    public = entity.to_public_dict()
    assert public["environment"]["gitops_path"] == "environments/sandbox-alice"
    assert public["environment"]["status"] == "active"


def test_merge_catalog_entities_skips_duplicate_ids() -> None:
    base = [
        CatalogEntity(
            entity_id="env-aws-sandbox-alice",
            display_name="repo-a",
            repo_url="https://github.com/acme/a",
            local_path=None,
            owner="platform",
            blueprint_name="terraform-module-generic",
            blueprint_version="1.0.0",
            standard_source="",
            standard_version="",
            component_type="component",
            lifecycle="",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="",
            manifest_namespace="",
            source="fleet",
        )
    ]
    extra = [
        CatalogEntity(
            entity_id="env-aws-sandbox-alice",
            display_name="sandbox-alice",
            repo_url=None,
            local_path=None,
            owner="platform",
            blueprint_name="terraform-environment-stack",
            blueprint_version="0.4.0",
            standard_source="",
            standard_version="",
            component_type="environment",
            lifecycle="dev",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="sandbox-alice",
            manifest_namespace="environments/sandbox-alice",
            source="environment",
        ),
        CatalogEntity(
            entity_id="env-aws-sandbox-bob",
            display_name="sandbox-bob",
            repo_url=None,
            local_path=None,
            owner="platform",
            blueprint_name="terraform-environment-stack",
            blueprint_version="0.4.0",
            standard_source="",
            standard_version="",
            component_type="environment",
            lifecycle="dev",
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name="sandbox-bob",
            manifest_namespace="environments/sandbox-bob",
            source="environment",
        ),
    ]
    merged = merge_catalog_entities(base, extra)
    assert len(merged) == 2
    assert {item.entity_id for item in merged} == {
        "env-aws-sandbox-alice",
        "env-aws-sandbox-bob",
    }
