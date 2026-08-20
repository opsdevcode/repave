"""Tests for gated assistant artifact drafts (never publish)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.assistant import resolve_intent
from repave_engine.assistant_artifacts import apply_artifact_draft, parse_artifact_files
from repave_engine.assistant_draft import RecordingAssistantDraftModel, StaticAssistantDraftModel
from repave_engine.blueprint import InputField
from repave_engine.v3_foundation import load_v3_foundation_config

_PASSING_README = """# Module

## Usage

Plan with the generated module.

## Provenance

Rendered from repave.yaml.
"""


def test_parse_artifact_rejects_generate_key() -> None:
    with pytest.raises(ValueError, match="must not include generate"):
        parse_artifact_files('{"files":{"README.md":"x"},"generate":true}')


def test_parse_artifact_rejects_path_traversal_before_write() -> None:
    with pytest.raises(ValueError, match="relative"):
        parse_artifact_files('{"files":{"../secret":"x"}}')
    with pytest.raises(ValueError, match="relative"):
        parse_artifact_files('{"files":{"/etc/passwd":"x"}}')


def test_apply_artifact_blocks_failed_gates_without_returning_files(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        gates=("docs-drift",),
        inputs=(InputField(name="module_name", type="string", required=True),),
    )
    resolution = resolve_intent(
        "generate a terraform module named vpc-core",
        blueprints=(blueprint,),
    )
    updated = apply_artifact_draft(
        resolution,
        blueprints=(blueprint,),
        model=StaticAssistantDraftModel('{"files":{"README.md":"nope"}}'),
        model_id="static-test",
        repo_root=tmp_path,
    )
    assert updated.artifact_status == "blocked"
    assert updated.artifact_files == ()
    assert any(
        item["name"] == "docs-drift" and not item["passed"] for item in updated.artifact_gates
    )
    assert "catalog.artifacts" in updated.tools


def test_apply_artifact_returns_files_only_after_gates_pass(tmp_path: Path) -> None:
    blueprint = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        gates=("docs-drift",),
        inputs=(InputField(name="module_name", type="string", required=True),),
    )
    resolution = resolve_intent(
        "generate a terraform module named vpc-core",
        blueprints=(blueprint,),
    )
    payload = json.dumps({"files": {"README.md": _PASSING_README}})
    updated = apply_artifact_draft(
        resolution,
        blueprints=(blueprint,),
        model=StaticAssistantDraftModel(payload),
        model_id="static-test",
        repo_root=tmp_path,
    )
    assert updated.artifact_status == "gated"
    assert len(updated.artifact_files) == 1
    assert updated.artifact_files[0].path == "README.md"


def test_apply_artifact_skips_empty_files(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, name="terraform-module-generic", gates=("docs-drift",))
    resolution = resolve_intent(
        "generate a terraform module named vpc-core",
        blueprints=(blueprint,),
    )
    model = RecordingAssistantDraftModel('{"files":{}}')
    updated = apply_artifact_draft(
        resolution,
        blueprints=(blueprint,),
        model=model,
        model_id="static-test",
        repo_root=tmp_path,
    )
    assert updated.artifact_status == "skipped-empty"
    assert updated.artifact_files == ()


def test_assistant_artifacts_require_draft(tmp_path: Path) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "output:\n  github_org: acme\n  modules_root: ../mods\n"
        "v3:\n  enabled: true\n  assistant:\n    enabled: true\n"
        "    artifacts:\n      enabled: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match=r"v3\.assistant\.artifacts\.enabled"):
        load_v3_foundation_config(tmp_path)
