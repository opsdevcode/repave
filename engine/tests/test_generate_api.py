from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint
from repave_engine.gate_registry import GateResult
from repave_engine.generate_api import serialize_generation_result
from repave_engine.pipeline import GenerationResult
from repave_engine.render import RenderResult


def test_serialize_generation_result(repo_root: Path) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
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
