from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint
from repave_engine.provenance_inputs import load_provenance_document
from repave_engine.standards_diff import (
    catalog_path_diff_for_pin,
    catalog_pin_diffs_for_blueprint,
    diff_observed_vs_catalog_pins,
    standards_diff_for_pin,
)


def test_standards_diff_for_pin_on_repo(repo_root: Path) -> None:
    result = standards_diff_for_pin(
        repo_root,
        standard_source="standards/terraform-standards",
        pinned_version="1.1.0",
    )
    assert result.standard_source == "standards/terraform-standards"
    assert result.pinned_version == "1.1.0"
    if result.available:
        assert result.baseline_ref
    else:
        assert result.reason


def test_standards_diff_missing_path(repo_root: Path) -> None:
    result = standards_diff_for_pin(
        repo_root,
        standard_source="standards/does-not-exist",
        pinned_version="1.0.0",
    )
    assert not result.available
    assert "not found" in result.reason.lower()


def test_diff_observed_vs_catalog_for_terraform_minimal_fixture(repo_root: Path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    doc = load_provenance_document(fixture / "repave.yaml")
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )
    changes = diff_observed_vs_catalog_pins(doc, blueprint)
    fields = {row.field for row in changes}
    assert "Blueprint version" in fields
    version_row = next(row for row in changes if row.field == "Blueprint version")
    assert version_row.before == "0.9.0"
    assert version_row.after == blueprint.version


def test_catalog_path_diff_for_pin_with_policy_tag(tmp_path: Path) -> None:
    from repave_engine.subprocess_run import run_subprocess
    from repave_engine.target_repo import _git_executable

    repo = tmp_path / "catalog"
    pack = repo / "policy" / "checkov" / "policies"
    pack.mkdir(parents=True)
    rule = pack / "rule.yaml"
    rule.write_text("Version: 1.0.0\nrule: old\n", encoding="utf-8")

    def git(*args: str) -> None:
        run_subprocess(
            [_git_executable(), *args],
            cwd=repo,
            check=True,
            git=True,
        )

    git("init")
    git("add", ".")
    git("-c", "user.name=repave-test", "-c", "user.email=repave@example.com", "commit", "-m", "pin")
    git("tag", "policy-v1.0.0")
    rule.write_text("Version: 1.0.0\nrule: new\n", encoding="utf-8")
    git("add", ".")
    git(
        "-c", "user.name=repave-test", "-c", "user.email=repave@example.com", "commit", "-m", "head"
    )

    result = catalog_path_diff_for_pin(
        repo,
        rel_path="policy/checkov/policies",
        pinned_version="1.0.0",
        path_kind="Checkov pack",
    )
    assert result.available
    assert result.has_changes
    assert any("rule.yaml" in item.path for item in result.files)


def test_catalog_pin_diffs_for_terraform_blueprint(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )
    diffs = catalog_pin_diffs_for_blueprint(repo_root, blueprint)
    kinds = {item.kind for item in diffs}
    assert kinds == {"standard", "checkov", "opa"}
    checkov = next(item for item in diffs if item.kind == "checkov")
    assert blueprint.checkov_policies is not None
    assert checkov.result.standard_source.endswith("checkov/policies")
    assert checkov.result.pinned_version == blueprint.checkov_policies.policy_version
    ansible = load_blueprint(
        repo_root / "blueprints" / "ansible-role-generic",
        repo_root=repo_root,
    )
    ansible_kinds = {item.kind for item in catalog_pin_diffs_for_blueprint(repo_root, ansible)}
    assert "ansible-lint" in ansible_kinds
