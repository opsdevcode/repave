from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from repave_engine.api import create_app
from repave_engine.settings import OutputConfig

_LEGACY_TF = {
    "terraform/main.tf": 'resource "aws_s3_bucket" "assets" {}\n',
    "terraform/variables.tf": 'variable "name" { type = string }\n',
    "README.rst": "Legacy assets bucket\n",
    "scripts/deploy.sh": "echo deploy\n",
}


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, body in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


@pytest.fixture
def client(repo_root: Path, output_config: OutputConfig) -> TestClient:
    return TestClient(create_app(repo_root=repo_root, output_config=output_config))


@pytest.fixture
def legacy_repo(tmp_path: Path) -> Path:
    return _write(tmp_path / "tf-legacy-assets", _LEGACY_TF)


def test_import_form_renders_cascading_dropdowns(client: TestClient) -> None:
    body = client.get("/import").text

    assert 'id="import-category"' in body
    assert 'id="import-blueprint"' in body
    assert 'id="import-catalog"' in body
    assert 'name="category"' in body
    assert 'name="blueprint"' in body


def test_import_catalog_json_groups_blueprints_by_family(client: TestClient) -> None:
    body = client.get("/import").text
    match = re.search(
        r'<script id="import-catalog" type="application/json">(.*?)</script>', body, re.S
    )
    assert match is not None
    catalog = json.loads(match.group(1))

    families = {group["family"] for group in catalog}
    assert "terraform" in families
    terraform = next(group for group in catalog if group["family"] == "terraform")
    assert any(bp["name"] == "terraform-module-generic" for bp in terraform["blueprints"])


def test_import_form_preselects_a_deep_linked_blueprint(client: TestClient) -> None:
    body = client.get("/import?repo=https://github.com/acme/x&blueprint=ansible-role-generic").text

    assert 'value="ansible" selected' in body
    assert 'value="terraform" selected' not in body
    assert '"ansible-role-generic"' in body
    assert "https://github.com/acme/x" in body


def test_import_form_ignores_an_unknown_deep_linked_blueprint(client: TestClient) -> None:
    response = client.get("/import?blueprint=does-not-exist")

    assert response.status_code == 200
    assert "selected>" not in response.text
    assert "does-not-exist" not in response.text


def test_import_nav_entry_is_present(client: TestClient) -> None:
    body = client.get("/").text

    assert 'href="/import"' in body
    assert ">Import</a>" in body


def test_import_requires_a_target(client: TestClient) -> None:
    response = client.post("/import", data={"target_repo": ""})

    assert response.status_code == 200
    assert "Repository path or URL is required." in response.text


def test_import_preview_shows_moves_scaffold_and_scorecard(
    client: TestClient, legacy_repo: Path
) -> None:
    response = client.post("/import", data={"target_repo": str(legacy_repo)})
    body = response.text

    assert response.status_code == 200
    assert "Import preview" in body
    assert "terraform-module-generic" in body
    assert "terraform/main.tf" in body
    assert "Moved (content unchanged)" in body
    assert "Added scaffold" in body
    assert "repave.yaml" in body
    assert "Scorecard" in body
    assert "Open pull request" in body


def test_import_preview_surfaces_detection_evidence(client: TestClient, legacy_repo: Path) -> None:
    body = client.post("/import", data={"target_repo": str(legacy_repo)}).text

    assert "Detected automatically" in body
    assert "confidence" in body


def test_import_preview_lists_unmapped_files(client: TestClient, legacy_repo: Path) -> None:
    body = client.post("/import", data={"target_repo": str(legacy_repo)}).text

    assert "Left in place (no rule matched)" in body
    assert "scripts/deploy.sh" in body


def test_import_preview_accepts_path_overrides(client: TestClient, legacy_repo: Path) -> None:
    body = client.post(
        "/import",
        data={
            "target_repo": str(legacy_repo),
            "override__terraform__main.tf": "network/main.tf",
        },
    ).text

    assert "network/main.tf" in body
    assert 'name="override__terraform__main.tf"' in body


def test_import_batch_form_renders(client: TestClient) -> None:
    body = client.get("/import/batch").text

    assert "Batch import" in body
    assert 'name="targets"' in body
    assert 'action="/import/batch"' in body
    assert "Preview batch" in body
    assert "data-import-org-scan" in body
    assert "data-import-org-scan-run" in body
    assert "Scan org" in body
    assert "data-import-search-preset" in body
    assert "Terraform (HCL)" in body
    assert "Map by artifact family" in body


def test_import_batch_preview_plans_multiple_repos(client: TestClient, tmp_path: Path) -> None:
    repo_a = _write(tmp_path / "tf-a", _LEGACY_TF)
    repo_b = _write(tmp_path / "tf-b", _LEGACY_TF)

    response = client.post(
        "/import/batch",
        data={"targets": f"{repo_a}\n{repo_b}"},
    )
    body = response.text

    assert response.status_code == 200
    assert "Batch import preview" in body
    assert "2 planned" in body
    assert str(repo_a) in body
    assert str(repo_b) in body


def test_import_preview_honours_an_explicit_blueprint(
    client: TestClient, legacy_repo: Path
) -> None:
    body = client.post(
        "/import",
        data={"target_repo": str(legacy_repo), "blueprint": "terraform-environment-stack"},
    ).text

    assert "terraform-environment-stack" in body
    assert "Detected automatically" not in body


def test_import_routes_a_governed_repo_to_upgrade(client: TestClient, tmp_path: Path) -> None:
    repo = _write(
        tmp_path / "governed",
        {"main.tf": "", "repave.yaml": "apiVersion: repave.dev/v1beta1\n"},
    )

    body = client.post("/import", data={"target_repo": str(repo)}).text

    assert "already present" in body
    assert "Go to upgrade" in body
    assert 'href="/update"' in body


def test_import_reports_a_missing_target_as_an_error(client: TestClient, tmp_path: Path) -> None:
    body = client.post("/import", data={"target_repo": str(tmp_path / "nope")}).text

    assert "is not a directory" in body


def test_import_preview_flags_conflicts(client: TestClient, tmp_path: Path) -> None:
    repo = _write(
        tmp_path / "tf-conflict",
        {"a/main.tf": 'resource "aws_vpc" "a" {}\n', "b/main.tf": 'resource "aws_vpc" "b" {}\n'},
    )

    body = client.post(
        "/import",
        data={"target_repo": str(repo), "blueprint": "terraform-module-generic"},
    ).text

    assert "both map to" in body
    assert "Open pull request" not in body


def test_import_apply_requires_a_github_token(
    client: TestClient, legacy_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repave_engine.api.resolve_github_access_token", lambda _explicit: "")

    body = client.post(
        "/import/apply",
        data={"target_repo": str(legacy_repo), "blueprint": "terraform-module-generic"},
    ).text

    assert "requires GITHUB_TOKEN" in body


def test_api_v2_advertises_the_import_endpoints(client: TestClient) -> None:
    payload = client.get("/api/v2").json()

    assert "POST /api/v2/imports/plan" in payload["endpoints"]
    assert "POST /api/v2/imports/apply" in payload["endpoints"]
    assert "POST /api/v2/imports/batch/plan" in payload["endpoints"]
    assert "POST /api/v2/imports/batch/apply" in payload["endpoints"]
    assert "POST /api/v2/github/org-scan" in payload["endpoints"]


def test_api_v2_import_plan_returns_the_plan(client: TestClient, legacy_repo: Path) -> None:
    response = client.post(
        "/api/v2/imports/plan",
        json={"target_repo": str(legacy_repo), "with_gates": False},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["blueprint_name"] == "terraform-module-generic"
    assert payload["detected"] is True
    assert payload["ok"] is True
    assert any(move["destination"] == "main.tf" for move in payload["moves"])
    assert payload["scorecard"]["passing_after"] > payload["scorecard"]["passing_before"]


def test_api_v2_import_plan_honours_overrides(client: TestClient, legacy_repo: Path) -> None:
    response = client.post(
        "/api/v2/imports/plan",
        json={
            "target_repo": str(legacy_repo),
            "with_gates": False,
            "overrides": {"terraform/main.tf": "network/main.tf"},
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert any(
        move["source"] == "terraform/main.tf" and move["destination"] == "network/main.tf"
        for move in payload["moves"]
    )
    assert payload["path_overrides"]["terraform/main.tf"] == "network/main.tf"


def test_api_v2_import_plan_requires_a_target(client: TestClient) -> None:
    response = client.post("/api/v2/imports/plan", json={})

    assert response.status_code == 400
    assert "target_repo is required" in response.json()["detail"]


def test_api_v2_import_plan_conflicts_on_a_governed_repo(
    client: TestClient, tmp_path: Path
) -> None:
    repo = _write(
        tmp_path / "governed",
        {"main.tf": "", "repave.yaml": "apiVersion: repave.dev/v1beta1\n"},
    )

    response = client.post(
        "/api/v2/imports/plan",
        json={"target_repo": str(repo), "with_gates": False},
    )

    assert response.status_code == 409


def test_api_v2_import_apply_requires_a_token(
    client: TestClient, legacy_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "repave_engine.api_v2.router.resolve_github_access_token", lambda _explicit: ""
    )

    response = client.post(
        "/api/v2/imports/apply",
        json={"target_repo": str(legacy_repo), "with_gates": False},
    )

    assert response.status_code == 400
    assert "GitHub token is required" in response.json()["detail"]
