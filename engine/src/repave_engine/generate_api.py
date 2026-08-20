"""JSON API helpers for headless generate (Backstage Scaffolder)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.artifact_store import resolve_artifact_store
from repave_engine.blueprint import (
    Blueprint,
    blueprint_dir,
    load_blueprint,
    primary_publish_name,
    resolve_bundle_dir,
    validate_inputs,
)
from repave_engine.bundle import Bundle, load_bundle
from repave_engine.gates import GateResult, RunEventCallback, all_gates_passed, gate_outcome
from repave_engine.pipeline import (
    BundleGenerationResult,
    BundleMemberResult,
    GenerationResult,
    generate_from_blueprint,
    generate_from_bundle,
)
from repave_engine.publish_idempotency import PublishIdempotencyContext
from repave_engine.render import RenderedFile, RenderResult, collect_rendered_files
from repave_engine.run_store import RunRecord
from repave_engine.settings import OutputConfig, load_gate_overrides
from repave_engine.target_repo import resolve_module_repository


def async_run_artifact_dir(repo_root: Path, run_id: str) -> Path:
    """Persistent staging for async runs so the portal can show results without re-running gates."""
    return resolve_artifact_store(repo_root).local_staging_dir(repo_root, run_id)


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
    publish_idempotency: PublishIdempotencyContext | None = None,
) -> dict[str, Any]:
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
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
        publish_idempotency=publish_idempotency,
        record_operability=staging_root is None,
        # Async workers must not block SUCCEEDED on outbound webhooks.
        send_notification=staging_root is None,
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
        "output_dir": str(result.render.output_dir),
    }
    if persist_artifact:
        body["artifact_root"] = str(result.render.output_dir)
        body["pr_message"] = result.pr_message
        if result.module_repository is not None:
            body["module_name"] = result.module_repository.name
            body["repository_url"] = result.module_repository.web_url
        body["rendered_files"] = [
            {
                "path": rendered.path,
                "content": rendered.content,
                "truncated": rendered.truncated,
            }
            for rendered in result.rendered_files
        ]
    else:
        body["rendered_files"] = len(result.rendered_files)
    return body


def run_bundle_api(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    bundle_name: str,
    inputs: dict[str, Any],
    dry_run: bool,
    github_token: str | None,
    on_event: RunEventCallback | None = None,
    staging_root: Path | None = None,
) -> dict[str, Any]:
    bundle = load_bundle(resolve_bundle_dir(repo_root, bundle_name), repo_root=repo_root)
    values = {str(key): str(value) for key, value in inputs.items()}
    if on_event is not None:
        on_event("bundle_started", {"bundle": bundle.name, "member_count": len(bundle.members)})
    result = generate_from_bundle(
        bundle,
        values,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=dry_run,
        require_run=dry_run,
        github_token=github_token,
        staging_root=staging_root,
        record_bundle_operability=staging_root is None,
        send_notification=staging_root is None,
    )
    if on_event is not None:
        on_event(
            "bundle_finished",
            {
                "bundle": bundle.name,
                "gates_outcome": gate_outcome(result.combined_gates()),
            },
        )
    return serialize_bundle_result(
        bundle,
        result,
        dry_run=dry_run,
        persist_artifact=staging_root is not None,
    )


def serialize_bundle_result(
    bundle: Bundle,
    result: BundleGenerationResult,
    *,
    dry_run: bool,
    persist_artifact: bool = False,
) -> dict[str, Any]:
    combined = result.combined_gates()
    body: dict[str, Any] = {
        "kind": "bundle",
        "bundle": bundle.name,
        "bundle_version": bundle.version,
        "dry_run": dry_run,
        "gates_outcome": gate_outcome(combined),
        "gates_passed": all_gates_passed(combined),
        "gates": [
            {
                "name": gate.name,
                "passed": gate.passed,
                "skipped": gate.skipped,
                "message": gate.message,
            }
            for gate in combined
        ],
        "shared_inputs": dict(result.shared_inputs),
        "members": [],
    }
    for member in result.members:
        member_body: dict[str, Any] = {
            "member_id": member.member_id,
            "blueprint": member.result.blueprint.name,
            "blueprint_version": member.result.blueprint.version,
            "dry_run": member.result.dry_run,
            "gates_outcome": gate_outcome(member.result.gates),
            "gates_passed": all_gates_passed(member.result.gates),
            "gates": [
                {
                    "name": gate.name,
                    "passed": gate.passed,
                    "skipped": gate.skipped,
                    "message": gate.message,
                }
                for gate in member.result.gates
            ],
            "output_dir": str(member.result.render.output_dir),
        }
        if persist_artifact:
            member_body["rendered_files"] = [
                {
                    "path": rendered.path,
                    "content": rendered.content,
                    "truncated": rendered.truncated,
                }
                for rendered in member.result.rendered_files
            ]
        else:
            member_body["rendered_files"] = len(member.result.rendered_files)
        body["members"].append(member_body)
    return body


def _rendered_files_from_snapshot(raw: object) -> tuple[RenderedFile, ...] | None:
    """Parse a persisted preview snapshot; return None when `raw` is a legacy count."""
    if isinstance(raw, int):
        return None
    if not isinstance(raw, list):
        return None
    files: list[RenderedFile] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        content = row.get("content")
        if not isinstance(path, str) or not isinstance(content, str):
            continue
        files.append(
            RenderedFile(
                path=path,
                content=content,
                truncated=bool(row.get("truncated", False)),
            )
        )
    return tuple(files)


def _collect_from_artifacts(
    *,
    stored: dict[str, object],
    repo_root: Path,
    blueprint: Blueprint,
) -> tuple[RenderedFile, ...] | None:
    artifact_store = resolve_artifact_store(repo_root)
    artifact_root = artifact_store.materialize_run_artifacts(stored)
    if artifact_root is None:
        return None
    return collect_rendered_files(artifact_root, artifact_type=blueprint.artifact_type)


def _resolve_stored_rendered_files(
    *,
    stored: dict[str, object],
    repo_root: Path,
    blueprint: Blueprint,
    dry_run: bool,
) -> tuple[RenderedFile, ...] | None:
    if not dry_run:
        return ()
    raw = stored.get("rendered_files")
    snapshot = _rendered_files_from_snapshot(raw)
    if isinstance(raw, list) and snapshot:
        return snapshot
    # Empty/malformed list or legacy count → rebuild from on-disk/object artifacts.
    from_artifacts = _collect_from_artifacts(
        stored=stored,
        repo_root=repo_root,
        blueprint=blueprint,
    )
    if from_artifacts is not None:
        return from_artifacts
    # Empty/malformed snapshot with unreachable artifacts → None so /result can
    # regenerate instead of rendering a blank "Generated files" section.
    return None


def preview_file_dicts_from_stored(
    *,
    stored: dict[str, object],
    repo_root: Path,
    blueprint_name: str,
    dry_run: bool,
) -> tuple[dict[str, object], ...]:
    """Resolve dry-run preview files from snapshot and/or on-disk artifacts."""
    if not dry_run or not blueprint_name.strip():
        return ()
    try:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    except (OSError, ValueError):
        return ()
    resolved = _resolve_stored_rendered_files(
        stored=stored,
        repo_root=repo_root,
        blueprint=blueprint,
        dry_run=True,
    )
    if not resolved:
        return ()
    return tuple(
        {
            "path": item.path,
            "content": item.content,
            "truncated": item.truncated,
        }
        for item in resolved
    )


def _stored_output_dir(stored: dict[str, object]) -> Path:
    for key in ("output_dir", "artifact_root"):
        raw = stored.get(key)
        if raw is not None:
            return Path(str(raw))
    return Path(".")


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


def _member_generation_from_stored(
    *,
    repo_root: Path,
    output_config: OutputConfig,
    member_row: dict[str, Any],
    dry_run: bool,
    template_values: dict[str, str],
) -> GenerationResult | None:
    blueprint_name = str(member_row.get("blueprint", "")).strip()
    if not blueprint_name:
        return None
    gates_raw = member_row.get("gates")
    if not isinstance(gates_raw, list) or not gates_raw:
        return None
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    output_dir = Path(str(member_row.get("output_dir", ".")))
    rendered_files = _rendered_files_from_snapshot(member_row.get("rendered_files"))
    if not rendered_files and dry_run and output_dir.is_dir():
        rendered_files = collect_rendered_files(
            output_dir,
            artifact_type=blueprint.artifact_type,
        )
    if isinstance(member_row.get("rendered_files"), list) and rendered_files is None:
        return None
    if rendered_files is None:
        rendered_files = ()
    module_name = primary_publish_name(blueprint, template_values)
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=template_values,
    )
    return GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=output_dir, values={}),
        gates=_gates_from_stored_payload(gates_raw),
        module_repository=module_repository,
        pr_plan=None,
        pr_message="",
        rendered_files=tuple(rendered_files),
        dry_run=dry_run,
        member_id=str(member_row.get("member_id", "")).strip() or None,
    )


def bundle_result_from_stored_run(
    *,
    record: RunRecord,
    repo_root: Path,
    output_config: OutputConfig,
) -> BundleGenerationResult | None:
    stored = record.result
    if stored is None or stored.get("kind") != "bundle":
        return None
    bundle_name = str(stored.get("bundle") or record.payload.get("bundle") or "").strip()
    if not bundle_name:
        return None
    bundle = load_bundle(resolve_bundle_dir(repo_root, bundle_name), repo_root=repo_root)
    members_raw = stored.get("members")
    if not isinstance(members_raw, list):
        return None
    shared_raw = stored.get("shared_inputs", record.payload.get("inputs", {}))
    shared_inputs = (
        {str(key): str(value) for key, value in shared_raw.items()}
        if isinstance(shared_raw, dict)
        else {}
    )
    members: list[BundleMemberResult] = []
    for row in members_raw:
        if not isinstance(row, dict):
            continue
        generation = _member_generation_from_stored(
            repo_root=repo_root,
            output_config=output_config,
            member_row=row,
            dry_run=record.dry_run,
            template_values=shared_inputs,
        )
        if generation is None:
            return None
        members.append(
            BundleMemberResult(
                member_id=str(row.get("member_id", "")).strip() or generation.member_id or "",
                result=generation,
            )
        )
    return BundleGenerationResult(
        bundle=bundle,
        members=tuple(members),
        dry_run=record.dry_run,
        shared_inputs=shared_inputs,
    )


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
    if stored.get("kind") == "bundle":
        return None
    gates_raw = stored.get("gates")
    if not isinstance(gates_raw, list) or not gates_raw:
        return None

    blueprint = load_blueprint(blueprint_dir(repo_root, record.blueprint_name), repo_root=repo_root)
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
    rendered_files = _resolve_stored_rendered_files(
        stored=stored,
        repo_root=repo_root,
        blueprint=blueprint,
        dry_run=dry_run,
    )
    if rendered_files is None:
        return None
    output_dir = _stored_output_dir(stored)
    module_name = primary_publish_name(blueprint, normalized)
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=normalized,
    )
    return GenerationResult(
        blueprint=blueprint,
        render=RenderResult(output_dir=output_dir, values=normalized),
        gates=_gates_from_stored_payload(gates_raw),
        module_repository=module_repository,
        pr_plan=None,
        pr_message=str(stored.get("pr_message", "")),
        rendered_files=tuple(rendered_files),
        dry_run=dry_run,
    )
