"""JSON API helpers for headless generate (Backstage Scaffolder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint, load_blueprint
from repave_engine.gates import GateResult, all_gates_passed
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig


def gate_outcome(gates: list[GateResult]) -> str:
    failed = sum(1 for gate in gates if not gate.passed and not gate.skipped)
    if failed:
        return "failed"
    if gates and all(gate.passed or gate.skipped for gate in gates):
        return "passed"
    return "empty"


def run_generate_api(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    blueprint_name: str,
    inputs: dict[str, Any],
    dry_run: bool,
    github_token: str | None,
) -> dict[str, Any]:
    blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
    values = {str(key): str(value) for key, value in inputs.items()}
    result = generate_from_blueprint(
        blueprint,
        values,
        output_config=output_config,
        dry_run=dry_run,
        require_run=dry_run,
        github_token=github_token,
        repo_root=repo_root,
    )
    return serialize_generation_result(blueprint, result, dry_run=dry_run)


def serialize_generation_result(
    blueprint: Blueprint,
    result: object,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    from repave_engine.pipeline import GenerationResult

    if not isinstance(result, GenerationResult):
        raise TypeError("expected GenerationResult")
    gates = result.gates
    return {
        "blueprint": blueprint.name,
        "blueprint_version": blueprint.version,
        "dry_run": dry_run,
        "gates_outcome": gate_outcome(gates),
        "gates_passed": all_gates_passed(gates),
        "gates": [
            {
                "name": gate.name,
                "passed": gate.passed,
                "skipped": gate.skipped,
                "message": gate.message,
            }
            for gate in gates
        ],
        "rendered_files": len(result.rendered_files),
        "output_dir": str(result.render.output_dir),
    }
