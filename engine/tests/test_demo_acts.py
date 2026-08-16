"""Portal demo acts 1-6 - automated smoke for live demo script (docs/seven-minute-demo.md)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
from repave_engine.api import create_app

pytestmark = pytest.mark.slow


def test_act1_home_catalog(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/")
    assert_surface_moved(response, "catalog")


def test_act2_and_3_terraform_dry_run_preview(repo_root, output_config, sample_inputs) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    sample_inputs = {**sample_inputs, "module_name": "demo"}
    response = client.post(
        "/generate",
        data={"blueprint_name": "terraform-module-generic", "dry_run": "true", **sample_inputs},
    )
    assert_surface_moved(response, "result")


def test_act4_update_repo_preview(repo_root, output_config) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/update", data={"target_repo": str(fixture)})
    assert response.status_code == 200
    assert "Upgrade preview" in response.text


def test_act5_opa_destructive_delete_blocks(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "opa-policy-generic",
            "dry_run": "true",
            "policy_name": "demo",
            "organization": "platform",
            "description": "Demo OPA policy pack for stakeholder demo",
            "plan_demo": "destructive_delete",
        },
    )
    assert_surface_moved(response, "result")


def test_act5b_azure_policy_dry_run_preview(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "azure-policy-generic",
            "dry_run": "true",
            "policy_name": "demo",
            "organization": "platform",
            "description": "Demo Azure Policy definitions",
        },
    )
    assert_surface_moved(response, "result")


def test_act6_backstage_catalog_in_terraform_preview(
    repo_root, output_config, sample_inputs
) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    sample_inputs = {
        **sample_inputs,
        "module_name": "demo",
        "include_backstage_catalog": "true",
        "owner": "group:platform",
    }
    response = client.post(
        "/generate",
        data={"blueprint_name": "terraform-module-generic", "dry_run": "true", **sample_inputs},
    )
    assert_surface_moved(response, "result")
