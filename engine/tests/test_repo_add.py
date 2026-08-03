from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.provenance import validate_provenance_file, write_provenance_file
from repave_engine.provenance_components import list_provenance_components
from repave_engine.render import render_blueprint
from repave_engine.repo_add import (
    NotGovernedError,
    RepoAddError,
    apply_add,
    build_add_plan,
    plan_add,
)
from repave_engine.verify import verify_repository


def _init_git(repo: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _generate_app_service(repo_root: Path, dest: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "app-service-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "service_name": "checkout-api",
            "description": "Checkout HTTP API",
            "owner": "team:payments",
            "port": "8080",
            "runtime": "python",
            "include_helm_reference": "false",
        },
        repo_root=repo_root,
    )
    render_blueprint(blueprint, values, dest)
    write_provenance_file(dest, blueprint, values, filename="repave.yaml")


def test_plan_add_rejects_ungoverned_repo(repo_root: Path, tmp_path: Path) -> None:
    repo = tmp_path / "bare"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n", encoding="utf-8")

    with pytest.raises(NotGovernedError, match="repave import"):
        plan_add(str(repo), repo_root, blueprint_name="helm-chart-generic")


def test_plan_add_helm_to_app_service(repo_root: Path, tmp_path: Path) -> None:
    repo = tmp_path / "checkout-api"
    repo.mkdir()
    _generate_app_service(repo_root, repo)
    _init_git(repo)

    plan = plan_add(str(repo), repo_root, blueprint_name="helm-chart-generic")

    assert plan.ok is True
    assert plan.blueprint_name == "helm-chart-generic"
    assert plan.component_id == "helm"
    assert "Chart.yaml" in plan.files_added
    assert "templates/deployment.yaml" in plan.files_added
    assert not plan.conflicts


def test_plan_add_reports_conflict_without_force(repo_root: Path, tmp_path: Path) -> None:
    repo = tmp_path / "checkout-api"
    repo.mkdir()
    _generate_app_service(repo_root, repo)
    (repo / "Chart.yaml").write_text("existing\n", encoding="utf-8")
    _init_git(repo)

    plan = plan_add(str(repo), repo_root, blueprint_name="helm-chart-generic")

    assert plan.ok is False
    assert any("Chart.yaml" in line for line in plan.conflicts)


def test_apply_add_updates_provenance_and_verify_components(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    repo = tmp_path / "checkout-api"
    repo.mkdir()
    _generate_app_service(repo_root, repo)
    _init_git(repo)

    plan = build_add_plan(
        repo,
        repo_root,
        target=str(repo),
        blueprint_name="helm-chart-generic",
    )
    assert plan.ok

    staging = tmp_path / "staging"
    staging.mkdir()
    result = apply_add(
        repo,
        repo_root,
        plan,
        staging_dir=staging,
        git_branch="repave/add/helm-test",
        commit_message="feat(repave): add helm-chart-generic component (helm)",
    )
    assert result.commit_sha

    doc = yaml.safe_load((repo / "repave.yaml").read_text(encoding="utf-8"))
    validate_provenance_file(repo / "repave.yaml", repo_root)
    components = list_provenance_components(doc)
    assert len(components) == 2
    assert components[1].blueprint_name == "helm-chart-generic"
    assert (repo / "Chart.yaml").is_file()

    verify = verify_repository(repo, repo_root)
    assert len(verify.components) == 1
    assert verify.components[0].component_id == "helm"
    assert verify.components[0].catalog_blueprint_name == "helm-chart-generic"


def test_plan_add_rejects_duplicate_blueprint(repo_root: Path, tmp_path: Path) -> None:
    repo = tmp_path / "checkout-api"
    repo.mkdir()
    _generate_app_service(repo_root, repo)
    _init_git(repo)

    first = plan_add(str(repo), repo_root, blueprint_name="helm-chart-generic")
    staging = tmp_path / "staging"
    staging.mkdir()
    apply_add(
        repo,
        repo_root,
        first,
        staging_dir=staging,
        git_branch="repave/add/helm-test",
        commit_message="add helm",
    )

    with pytest.raises(RepoAddError, match="already recorded"):
        plan_add(str(repo), repo_root, blueprint_name="helm-chart-generic")
