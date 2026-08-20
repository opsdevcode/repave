from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.blueprint import load_blueprint, resolve_bundle_dir
from repave_engine.gate_registry import GateResult
from repave_engine.generate_api import serialize_generation_result
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult


def test_serialize_generation_result(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )
    render = RenderResult(output_dir=Path("/tmp/out"), values={})
    gates = [GateResult("terraform-fmt", True, False, "ok")]
    result = GenerationResult(
        blueprint=blueprint,
        render=render,
        gates=gates,
        module_repository=None,
        pr_plan=None,
        pr_message="dry-run",
        dry_run=True,
    )
    payload = serialize_generation_result(blueprint, result, dry_run=True)
    assert payload["gates_outcome"] == "passed"
    assert payload["gates_passed"] is True
    assert payload["blueprint"] == blueprint.name
    assert "artifact_root" not in payload

    persisted = serialize_generation_result(blueprint, result, dry_run=True, persist_artifact=True)
    assert persisted["artifact_root"] == "/tmp/out"
    assert persisted["pr_message"] == "dry-run"
    assert persisted["rendered_files"] == []


def test_serialize_generation_result_persists_rendered_file_snapshot(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root=repo_root,
    )
    from repave_engine.render import RenderedFile

    render = RenderResult(output_dir=Path("/tmp/out"), values={})
    gates = [GateResult("terraform-fmt", True, False, "ok")]
    result = GenerationResult(
        blueprint=blueprint,
        render=render,
        gates=gates,
        module_repository=None,
        pr_plan=None,
        pr_message="dry-run",
        rendered_files=(RenderedFile(path="main.tf", content="# stub\n", truncated=False),),
        dry_run=True,
    )
    persisted = serialize_generation_result(blueprint, result, dry_run=True, persist_artifact=True)
    assert persisted["rendered_files"] == [
        {"path": "main.tf", "content": "# stub\n", "truncated": False},
    ]


def test_resolve_bundle_dir_rejects_parent_escape(repo_root: Path) -> None:
    with pytest.raises(ValueError, match="path escapes root"):
        resolve_bundle_dir(repo_root, "../terraform-module-generic")
