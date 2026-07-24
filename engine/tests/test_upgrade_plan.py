from __future__ import annotations

import json
from pathlib import Path

import pytest

from repave_engine.provenance_inputs import inputs_from_provenance, load_provenance_document
from repave_engine.upgrade_plan import diff_directories, plan_upgrade


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


def test_load_provenance_document(tmp_path: Path) -> None:
    path = tmp_path / "repave.yaml"
    path.write_text("apiVersion: repave.dev/v1beta1\nkind: GoldenPathArtifact\n", encoding="utf-8")
    doc = load_provenance_document(path)
    assert doc["kind"] == "GoldenPathArtifact"
