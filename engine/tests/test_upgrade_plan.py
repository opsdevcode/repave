from __future__ import annotations

import json
from pathlib import Path

import pytest

from repave_engine.provenance_inputs import inputs_from_provenance, load_provenance_document
from repave_engine.upgrade_plan import (
    apply_upgrade,
    build_upgrade_pull_request_body,
    build_upgrade_pull_request_title,
    diff_directories,
    open_upgrade_pull_request,
    plan_upgrade,
)


def test_inputs_from_provenance_terraform_minimal() -> None:
    doc = {
        "metadata": {"name": "example"},
        "spec": {
            "artifactType": "terraform-module",
            "terraformModule": {
                "module_name": "example",
                "cloud_provider": "aws",
                "provider_services": ["ec2", "s3"],
            },
        },
    }
    values = inputs_from_provenance(doc)
    assert values["module_name"] == "example"
    assert values["cloud_provider"] == "aws"
    assert values["provider_services"] == "ec2,s3"


def test_diff_directories_detects_additions(tmp_path: Path) -> None:
    left = tmp_path / "left"
    right = tmp_path / "right"
    left.mkdir()
    right.mkdir()
    (left / "keep.txt").write_text("same", encoding="utf-8")
    (right / "keep.txt").write_text("same", encoding="utf-8")
    (right / "new.txt").write_text("added", encoding="utf-8")

    added, modified, removed = diff_directories(left, right)
    assert added == ["new.txt"]
    assert modified == []
    assert removed == []


def test_plan_upgrade_against_operator_fixture(repo_root: Path, tmp_path: Path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    assert fixture.is_dir(), f"missing fixture at {fixture}"

    result = plan_upgrade(fixture, repo_root, staging_root=tmp_path / "staging")
    payload = result.to_json_dict()
    assert payload["blueprint_name"] == "terraform-module-generic"
    assert payload["changed_file_count"] > 0
    assert payload["pin_changes"]
    assert any(row["field"] == "Blueprint version" for row in payload["pin_changes"])
    assert "repave.yaml" in payload["added"] or "repave.yaml" in payload["modified"]


def test_cli_plan_upgrade_json(repo_root, tmp_path, capsys) -> None:
    import argparse

    from repave_engine.cli import cmd_plan_upgrade

    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    if not fixture.is_dir():
        pytest.skip("operator fixture not present")

    args = argparse.Namespace(
        repo_root=str(repo_root),
        target_repo=str(fixture),
        blueprint=None,
        staging_root=str(tmp_path / "staging"),
        format="json",
    )
    code = cmd_plan_upgrade(args)
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["changed_file_count"] >= 1
    assert "summary" in output


def test_apply_upgrade_git_commit(repo_root: Path, tmp_path: Path) -> None:
    import subprocess

    target = tmp_path / "module"
    target.mkdir()
    fixture_yaml = (
        repo_root / "operator" / "testdata" / "modules" / "terraform-minimal" / "repave.yaml"
    )
    (target / "repave.yaml").write_text(fixture_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=target, check=True)
    subprocess.run(["git", "add", "repave.yaml"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=target, check=True, capture_output=True)

    result = apply_upgrade(
        target,
        repo_root,
        staging_root=tmp_path / "staging",
        git_branch="repave/upgrade-test",
        commit_message="apply upgrade",
    )
    assert result.git_branch == "repave/upgrade-test"
    assert len(result.commit_sha) == 40
    assert result.plan.changed_file_count > 0


def test_build_upgrade_pull_request_title_and_body() -> None:
    from repave_engine.upgrade_plan import UpgradePlanResult

    plan = UpgradePlanResult(
        added=("new.tf",),
        modified=("main.tf",),
        removed=(),
        blueprint_name="terraform-minimal",
        blueprint_version="1.2.3",
    )
    assert build_upgrade_pull_request_title("terraform-minimal", "1.2.3") == (
        "chore(repave): upgrade terraform-minimal to 1.2.3"
    )
    body = build_upgrade_pull_request_body(plan)
    assert "terraform-minimal" in body
    assert "`new.tf`" in body
    assert "`main.tf`" in body


def test_open_upgrade_pull_request(repo_root: Path, tmp_path: Path) -> None:
    import subprocess
    from unittest.mock import patch

    target = tmp_path / "module"
    target.mkdir()
    fixture_yaml = (
        repo_root / "operator" / "testdata" / "modules" / "terraform-minimal" / "repave.yaml"
    )
    (target / "repave.yaml").write_text(fixture_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=target, check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example-org/tf-aws-demo.git"],
        cwd=target,
        check=True,
    )
    subprocess.run(["git", "add", "repave.yaml"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=target, check=True, capture_output=True)

    with (
        patch("repave_engine.upgrade_plan.push_git_branch") as push,
        patch("repave_engine.upgrade_plan.create_github_pull_request") as create_pr,
        patch("repave_engine.upgrade_plan.add_pull_request_labels") as add_labels,
    ):
        create_pr.return_value = {
            "html_url": "https://github.com/example-org/tf-aws-demo/pull/42",
            "number": 42,
        }
        result = open_upgrade_pull_request(
            target,
            repo_root,
            github_token="ghp_test",
            staging_root=tmp_path / "staging",
            git_branch="repave/upgrade-test",
            commit_message="apply upgrade",
        )

    push.assert_called_once()
    create_pr.assert_called_once()
    add_labels.assert_called_once()
    assert result.pull_request_number == 42
    assert "pull/42" in result.pull_request_url
    assert result.apply.plan.changed_file_count > 0


def test_apply_upgrade_preserve_local_skips_modified_overwrite(
    repo_root: Path,
    tmp_path: Path,
) -> None:
    import subprocess

    target = tmp_path / "module"
    target.mkdir()
    fixture_yaml = (
        repo_root / "operator" / "testdata" / "modules" / "terraform-minimal" / "repave.yaml"
    )
    (target / "repave.yaml").write_text(fixture_yaml.read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init"], cwd=target, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=target, check=True)
    subprocess.run(["git", "add", "repave.yaml"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=target, check=True, capture_output=True)

    first = apply_upgrade(
        target,
        repo_root,
        staging_root=tmp_path / "staging-a",
        git_branch="repave/upgrade-base",
        commit_message="apply upgrade",
    )
    candidates = [
        path
        for path in (*first.plan.modified, *first.plan.added)
        if path != "repave.yaml" and not path.startswith(".repave/")
    ]
    assert candidates, "expected at least one scaffold file to edit"
    edited_rel = candidates[0]
    edited_path = target / edited_rel
    edited_path.write_text("LOCAL EDIT\n", encoding="utf-8")

    preserved = apply_upgrade(
        target,
        repo_root,
        staging_root=tmp_path / "staging-b",
        git_branch="repave/upgrade-preserve",
        commit_message="apply with preserve",
        preserve_local=True,
    )

    assert edited_rel in preserved.preserved_local
    assert edited_path.read_text(encoding="utf-8") == "LOCAL EDIT\n"
    blueprint_copy = target / ".repave" / "upgrade-staging" / edited_rel
    assert blueprint_copy.is_file()
    assert blueprint_copy.read_text(encoding="utf-8") != "LOCAL EDIT\n"


def test_load_provenance_document(tmp_path: Path) -> None:
    path = tmp_path / "repave.yaml"
    path.write_text("apiVersion: repave.dev/v1beta1\nkind: GoldenPathArtifact\n", encoding="utf-8")
    doc = load_provenance_document(path)
    assert doc["kind"] == "GoldenPathArtifact"
