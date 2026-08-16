from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from portal_moved import assert_surface_moved
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
    assert_surface_moved(client.get("/import"), "import")


def test_import_form_preselects_a_deep_linked_blueprint(client: TestClient) -> None:
    assert_surface_moved(
        client.get("/import?repo=https://github.com/acme/x&blueprint=ansible-role-generic"),
        "import",
    )


def test_import_form_ignores_an_unknown_deep_linked_blueprint(client: TestClient) -> None:
    assert_surface_moved(client.get("/import?blueprint=does-not-exist"), "import")


def test_import_nav_entry_is_present(client: TestClient) -> None:
    body = client.get("/").text

    assert 'href="/import"' in body
    assert ">Import</a>" in body


def test_import_requires_a_target(client: TestClient) -> None:
    assert_surface_moved(client.post("/import", data={"target_repo": ""}), "import")


def test_import_preview_shows_moves_scaffold_and_scorecard(
    client: TestClient, legacy_repo: Path
) -> None:
    assert_surface_moved(client.post("/import", data={"target_repo": str(legacy_repo)}), "import")


def test_import_batch_form_renders(client: TestClient) -> None:
    assert_surface_moved(client.get("/import/batch"), "import-batch")


def test_import_batch_preview_plans_multiple_repos(client: TestClient, tmp_path: Path) -> None:
    repo_a = _write(tmp_path / "tf-a", _LEGACY_TF)
    repo_b = _write(tmp_path / "tf-b", _LEGACY_TF)
    assert_surface_moved(
        client.post("/import/batch", data={"targets": f"{repo_a}\n{repo_b}"}),
        "import-batch",
    )


def test_import_apply_requires_a_github_token(
    client: TestClient, legacy_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repave_engine.api.resolve_github_access_token", lambda _explicit: "")
    assert_surface_moved(
        client.post(
            "/import/apply",
            data={"target_repo": str(legacy_repo), "blueprint": "terraform-module-generic"},
        ),
        "import",
    )


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
