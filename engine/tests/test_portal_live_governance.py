from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.fleet import FleetEntry, register_repo

PROVENANCE_ENTRY = FleetEntry(
    repo_url="https://github.com/acme/tf-vpc",
    blueprint_name="terraform-module-generic",
    blueprint_version="0.9.0",
    standard_source="standards/terraform-standards",
    standard_version="1.1.0",
    owner="platform",
    registered_by="tester@example.com",
)


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(path))
    return path


def test_platform_finops_page_renders(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    snapshot_file = tmp_path / "data" / "fleet" / "cost-snapshots.jsonl"
    snapshot_file.parent.mkdir(parents=True)
    snapshot_file.write_text(
        "\n".join(
            [
                '{"entity_id":"acme-tf-vpc","captured_at":"2026-07-09T00:00:00Z",'
                '"currency":"USD","amount_30d":"120.00"}',
                '{"entity_id":"acme-tf-vpc","captured_at":"2026-08-06T00:00:00Z",'
                '"currency":"USD","amount_30d":"200.00"}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "repave.config.yaml").write_text(
        (
            f"fleet:\n  enabled: true\n  file: {registry}\n"
            "portal:\n"
            "  cost_snapshots:\n"
            "    enabled: true\n"
            f"    file: {snapshot_file}\n"
            "  cost_budgets:\n"
            "    default_monthly_usd: 100\n"
            "  cost_anomalies:\n"
            "    enabled: true\n"
            "    wow_threshold_pct: 25\n"
            "    mom_threshold_pct: 50\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))
    response = client.get("/platform/finops")
    assert response.status_code == 200
    assert "FinOps showback" in response.text
    assert "Fleet rollup" in response.text
    assert "tf-vpc" in response.text
    assert "Cost anomalies" in response.text
    assert "Month over month" in response.text
    assert "+66.7%" in response.text


def test_estate_map_page_lists_tiles(
    output_config, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, registry: Path
) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    (tmp_path / "repave.config.yaml").write_text(
        f"fleet:\n  enabled: true\n  file: {registry}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app(repo_root=tmp_path, output_config=output_config))

    response = client.get("/estate")

    assert response.status_code == 200
    assert "Repo status" in response.text
    assert "Which governed repositories are current" in response.text
    assert "tf-vpc" in response.text
    assert "estate-tile" in response.text
    assert "estate-summary" in response.text
    assert "data-estate-map" in response.text
    assert 'data-view-mode="table"' in response.text
    assert "/blueprints/terraform-module-generic" in response.text
    assert "/update?target_repo=" in response.text


def test_presenter_mode_shell(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/?presenter=1").text
    assert "shell--presenter" in body
    assert "Presenter mode" in body


def test_update_form_prefills_target_repo(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get(
        "/update",
        params={"target_repo": "https://github.com/acme/tf-vpc"},
    ).text
    assert 'value="https://github.com/acme/tf-vpc"' in body


def test_blueprint_preflight_panel(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/blueprints/terraform-module-generic").text

    assert "preflight-panel" in body
    assert "form-actions__preflight-details" in body
    assert "Example repo" in body
    assert "Gate list" in body


def test_bundle_topology_section(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    body = client.get("/bundles/service-stack").text

    assert "bundle-topology" in body


def test_bundle_result_includes_topology(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post(
        "/generate",
        data={
            "bundle_name": "service-stack",
            "dry_run": "true",
            "service_name": "portal-bundle",
            "description": "Portal bundle dry-run test",
            "owner": "group:platform",
            "organization": "platform",
            "team": "payments",
            "port": "8080",
            "runtime": "python",
            "catalog_lifecycle": "experimental",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
        },
    )
    assert response.status_code == 200
    assert "bundle-topology" in response.text


def test_upgrade_preview_unified_diffs(repo_root, output_config) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/update", data={"target_repo": str(fixture)})
    assert response.status_code == 200
    body = response.text
    assert "Unified diffs" in body or "diff-viewer" in body


def test_api_estate_json(repo_root, output_config, registry: Path) -> None:
    register_repo(registry, PROVENANCE_ENTRY)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))

    response = client.get("/api/v1/estate")

    assert response.status_code == 200
    assert response.json()["count"] == 1


def test_run_console_contract(
    repo_root, output_config, sample_inputs, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("REPAVE_ASYNC_GENERATION", "1")
    monkeypatch.setenv("REPAVE_RUNS_DB", str(tmp_path / "runs.sqlite"))
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    submit = client.post(
        "/api/v1/runs",
        json={
            "blueprint": "terraform-module-generic",
            "dry_run": True,
            "inputs": sample_inputs,
        },
    )
    assert submit.status_code == 202
    run_id = submit.json()["run_id"]
    page = client.get(f"/runs/{run_id}")
    assert page.status_code == 200
    body = page.text
    assert "data-run-console" in body
    assert "run-console__gate-table" in body
    assert "run-console-log" in body
    assert 'data-stage="publish"' in body
    assert "run-console__stage-index" in body
    assert "run-console__stepper" in body
    assert "data-run-stepper-fill" in body
    assert "run-console__publish-chip" in body
    assert "Starting apply" in body
    assert 'data-dry-run="true"' in body
    assert "run-console__outcome" in body
    assert "no GitHub repository is created" in body
    assert f"/api/v1/runs/{run_id}/events" not in body
    assert 'data-run-id="' + run_id + '"' in body


def test_command_palette_contract(repo_root, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    body = client.get("/").text
    assert "command-palette" in body
    assert "command-palette-data" in body
    assert '"subtitle"' in body
    assert "Golden paths home" in body
    assert "Resume last run" in body
    assert "terraform-module-generic" in body
    assert '"/platform/finops"' in body
    assert '"/platform/feedback"' in body
    assert "shell__footer-link" in body
    footer = body[body.index("shell__footer") :]
    assert 'href="/platform/finops"' in footer
    assert 'href="/platform/feedback"' in footer
    primary = body.split("shell__nav--primary", 1)[1].split("shell__nav-more", 1)[0]
    assert 'href="/platform/fleet"' in primary
    assert ">Platform<" in primary
    more_start = body.index("shell__nav-more")
    more_end = body.index("</details>", more_start)
    more_section = body[more_start:more_end]
    assert 'href="/platform/finops"' not in more_section
    assert 'href="/platform/feedback"' not in more_section
