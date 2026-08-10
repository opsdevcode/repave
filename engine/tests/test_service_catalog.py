"""Service catalog overlay, maturity rubric, profiles, and initiatives."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.initiatives import (
    append_initiative,
    build_initiative_from_form,
    evaluate_initiative_for_entity,
    read_initiatives,
)
from repave_engine.maturity_rubric import evaluate_maturity, load_maturity_rubric
from repave_engine.service_catalog_overlay import (
    enrich_entity_with_overlay,
    extract_catalog_overlay_fields,
    filter_entities_by_team,
    team_slug_from_owner,
)
from repave_engine.settings import ServiceCatalogConfig, load_service_catalog_config
from repave_engine.workload_profiles import (
    build_vend_payload_from_deployment_set,
    find_deployment_set,
    find_workload_profile,
    load_deployment_sets,
    load_workload_profiles,
)


def _entity(**overrides: object) -> CatalogEntity:
    base = dict(
        entity_id="svc-demo",
        display_name="demo",
        repo_url="https://github.com/acme/demo",
        local_path=None,
        owner="group:platform",
        blueprint_name="app-service-generic",
        blueprint_version="1.0.0",
        standard_source="standards/app.md",
        standard_version="1.0.0",
        component_type="service",
        lifecycle="production",
        operator_phase="Ready",
        operator_message="",
        remediation_pr_url="",
        manifest_name="",
        manifest_namespace="",
        source="fleet",
        scorecard=(
            ScorecardDimension("provenance", "Provenance", "pass", "ok"),
            ScorecardDimension("pins", "Pins", "pass", "ok"),
            ScorecardDimension("has-runbook", "Runbook", "pass", "ok"),
        ),
    )
    base.update(overrides)
    return CatalogEntity(**base)  # type: ignore[arg-type]


def test_team_slug_from_owner() -> None:
    assert team_slug_from_owner("group:platform") == "platform"
    assert team_slug_from_owner("group:default/payments") == "payments"
    assert team_slug_from_owner("alice@example.com") == "alice"


def test_load_maturity_rubric_default() -> None:
    rubric = load_maturity_rubric(None)
    result = evaluate_maturity(_entity(), rubric)
    assert result.level >= 3
    assert result.label == "Operable"


def test_load_maturity_rubric_from_platform_dev(repo_root: Path) -> None:
    path = repo_root / "examples/platform-dev/config/maturity-rubric.yaml"
    rubric = load_maturity_rubric(path)
    assert len(rubric.levels) == 5
    result = evaluate_maturity(_entity(), rubric)
    assert result.level == 3


def test_workload_profiles_and_vend_payload(repo_root: Path) -> None:
    profiles = load_workload_profiles(
        repo_root / "examples/platform-dev/config/workload-profiles.yaml"
    )
    sets = load_deployment_sets(repo_root / "examples/platform-dev/config/deployment-sets.yaml")
    assert len(profiles) >= 2
    assert len(sets) >= 1
    dep = find_deployment_set(sets, "api-sandbox-7d")
    assert dep is not None
    profile = find_workload_profile(profiles, dep.workload_profile)
    assert profile is not None
    payload = build_vend_payload_from_deployment_set(
        dep,
        profile,
        stack_name="my-sandbox",
        owner="group:platform",
        dry_run=True,
    )
    assert payload["kind"] == "environment_vend"
    assert payload["blueprint"] == "terraform-environment-stack"
    assert payload["inputs"]["stack_name"] == "my-sandbox"
    assert payload["inputs"]["workload_profile"] == "api-sandbox"


def test_initiatives_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "initiatives.jsonl"
    initiative = build_initiative_from_form(
        {
            "title": "Ship runbooks",
            "target_level": "3",
            "target_rule_keys": "has-runbook",
            "owning_team": "platform",
        }
    )
    append_initiative(path, initiative)
    loaded = read_initiatives(path)
    assert len(loaded) == 1
    assert loaded[0].title == "Ship runbooks"
    status = evaluate_initiative_for_entity(
        loaded[0],
        _entity(),
        rubric=load_maturity_rubric(None),
    )
    assert status.passed is True


def test_extract_overlay_from_checkout(repo_root: Path) -> None:
    checkout = repo_root / "examples/platform-dev/fixtures/modules/checkout-api"
    fields = extract_catalog_overlay_fields(checkout)
    assert fields["oncall"] == "platform-oncall"
    assert "component:default/tf-vpc" in fields["dependencies"]
    assert fields["workload_profile"] == "api-sandbox"


def test_enrich_entity_with_overlay(repo_root: Path) -> None:
    checkout = repo_root / "examples/platform-dev/fixtures/modules/checkout-api"
    config = ServiceCatalogConfig(
        enabled=True,
        maturity_rubric=repo_root / "examples/platform-dev/config/maturity-rubric.yaml",
        initiatives=repo_root / "examples/platform-dev/fixtures/platform-metrics/initiatives.jsonl",
        default_team="platform",
    )
    entity = _entity(local_path=checkout, owner="group:platform")
    enriched = enrich_entity_with_overlay(
        entity,
        config=config,
        rubric=load_maturity_rubric(config.maturity_rubric),
        initiatives=read_initiatives(config.initiatives) if config.initiatives else (),
    )
    assert enriched.oncall == "platform-oncall"
    assert enriched.team_slug == "platform"
    assert enriched.maturity_level >= 1
    assert enriched.dependencies


def test_filter_entities_by_team() -> None:
    entities = [
        _entity(entity_id="a", team_slug="platform", owner="group:platform"),
        _entity(entity_id="b", team_slug="payments", owner="group:payments"),
    ]
    matched = filter_entities_by_team(entities, "platform")
    assert [item.entity_id for item in matched] == ["a"]


def test_load_service_catalog_config(platform_dev_root: Path) -> None:
    cfg = load_service_catalog_config(platform_dev_root)
    assert cfg is not None
    assert cfg.enabled is True
    assert cfg.maturity_rubric is not None
    assert cfg.maturity_rubric.is_file()
    assert cfg.workload_profiles is not None
    assert cfg.deployment_sets is not None


def test_portal_service_catalog_pages(
    platform_dev_repo: Path,
    output_config,
) -> None:
    client = TestClient(create_app(repo_root=platform_dev_repo, output_config=output_config))
    home = client.get("/home")
    assert home.status_code == 200
    assert "My services" in home.text

    sandbox = client.get("/sandbox")
    assert sandbox.status_code == 200
    assert "Request a sandbox" in sandbox.text
    assert "api-sandbox-7d" in sandbox.text

    maturity = client.get("/platform/maturity")
    assert maturity.status_code == 200
    assert "Service maturity" in maturity.text

    initiatives = client.get("/platform/initiatives")
    assert initiatives.status_code == 200
    assert "Runbook coverage" in initiatives.text

    api_maturity = client.get("/api/v2/platform/maturity")
    assert api_maturity.status_code == 200
    body = api_maturity.json()
    assert body["catalog_enabled"] is True

    catalog = client.get("/api/v2/catalog/entities?team=platform")
    assert catalog.status_code == 200
    assert catalog.json()["count"] >= 1

    team = client.get("/teams/platform")
    assert team.status_code == 200
    assert "Team platform" in team.text


@pytest.fixture
def platform_dev_root(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    dev_root = repo_root / "examples" / "platform-dev"
    raw = (dev_root / "repave.config.platform-dev.yaml").read_text(encoding="utf-8")
    resolved = raw.replace("examples/platform-dev/", f"{dev_root}/")
    (tmp_path / "repave.config.yaml").write_text(resolved, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture
def platform_dev_repo(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    import yaml

    from repave_engine import settings

    dev_yaml = repo_root / "examples" / "platform-dev" / "repave.config.platform-dev.yaml"
    dev_data = yaml.safe_load(dev_yaml.read_text(encoding="utf-8"))
    assert isinstance(dev_data, dict)
    config_path = (repo_root / "repave.config.yaml").resolve()
    real_load = settings._load_config_file

    def patched_load(path: Path) -> dict:
        if path.resolve() == config_path:
            return dev_data
        return real_load(path)

    monkeypatch.setattr(settings, "_load_config_file", patched_load)
    return repo_root
