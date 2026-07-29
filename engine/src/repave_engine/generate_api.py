"""JSON API helpers for headless generate (Backstage Scaffolder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint, load_blueprint, primary_publish_name, validate_inputs
from repave_engine.gates import GateResult, RunEventCallback, all_gates_passed
from repave_engine.pipeline import GenerationResult, generate_from_blueprint
from repave_engine.render import RenderResult, collect_rendered_files
from repave_engine.run_store import RunRecord
from repave_engine.settings import OutputConfig, load_gate_overrides
from repave_engine.target_repo import resolve_module_repository


def gate_outcome(gates: list[GateResult]) -> str:
    failed = sum(1 for gate in gates if not gate.passed and not gate.skipped)
    if failed:
        return "failed"
    if gates and all(gate.passed or gate.skipped for gate in gates):
        return "passed"
    return "empty"


def _blueprint_path(repo_root: Path, blueprint_name: str) -> Path:
    return repo_root / "blueprints" / blueprint_name


def async_run_artifact_dir(repo_root: Path, run_id: str) -> Path:
    """Persistent staging for async runs so the portal can show results without re-running gates."""
    return repo_root / "data" / "async-run-artifacts" / run_id


def run_generate_api(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    blueprint_name: str,
    inputs: dict[str, Any],
    dry_run: bool,
    github_token: str | None,
    on_event: RunEventCallback | None = None,
    staging_root: Path | None = None,
) -> dict[str, Any]:
    blueprint = load_blueprint(_blueprint_path(repo_root, blueprint_name), repo_root)
    values = {str(key): str(value) for key, value in inputs.items()}
    result = generate_from_blueprint(
        blueprint,
        values,
        output_config=output_config,
        dry_run=dry_run,
        require_run=dry_run,
        github_token=github_token,
        repo_root=repo_root,
        on_event=on_event,
        staging_root=staging_root,
    )
    return serialize_generation_result(
        blueprint,
        result,
        dry_run=dry_run,
        persist_artifact=staging_root is not None,
    )


def serialize_generation_result(
    blueprint: Blueprint,
    result: object,
    *,
    dry_run: bool,
    persist_artifact: bool = False,
) -> dict[str, Any]:
    if not isinstance(result, GenerationResult):
        raise TypeError("expected GenerationResult")
    gates = result.gates
    body: dict[str, Any] = {
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
    if persist_artifact:
        body["artifact_root"] = str(result.render.output_dir)
        body["pr_message"] = result.pr_message
    return body


def _gates_from_stored_payload(rows: list[Any]) -> list[GateResult]:
    gates: list[GateResult] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        gates.append(
            GateResult(
                str(row.get("name", "")),
                bool(row.get("passed")),
                bool(row.get("skipped")),
                str(row.get("message", "")),
            )
        )
    return gates


def generation_result_from_stored_run(
    *,
    record: RunRecord,
    repo_root: Path,
    output_config: OutputConfig,
) -> GenerationResult | None:
    """Rebuild portal GenerationResult from a completed async run (no gate re-run)."""
    stored = record.result
    if stored is None:
        return None
    artifact_raw = stored.get("artifact_root") or stored.get("output_dir")
    if artifact_raw is None:
        return None
    artifact_root = Path(str(artifact_raw))
    if not artifact_root.is_dir():
        return None
    gates_raw = stored.get("gates")
    if not isinstance(gates_raw, list) or not gates_raw:
        return None

    blueprint = load_blueprint(_blueprint_path(repo_root, record.blueprint_name), repo_root)
    inputs_raw = record.payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        inputs_raw = {}
    values = {str(key): str(value) for key, value in inputs_raw.items()}
    gate_overrides = load_gate_overrides(repo_root)
    try:
        normalized = validate_inputs(
            blueprint,
            values,
            repo_root=repo_root,
            gate_overrides=gate_overrides,
        )
    except ValueError:
        normalized = dict(values)

    dry_run = record.dry_run
    module_name = primary_publish_name(blueprint, normalized)
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=normalized,
    )
    rendered_files = (
        collect_rendered_files(artifact_root, artifact_type=blueprint.artifact_type)
        if dry_run
        else ()
    )
    return GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=artifact_root, values=normalized),
        gates=_gates_from_stored_payload(gates_raw),
        module_repository=module_repository,
        pr_plan=None,
        pr_message=str(stored.get("pr_message", "")),
        rendered_files=tuple(rendered_files),
        dry_run=dry_run,
    )
