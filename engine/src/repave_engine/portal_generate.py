"""POST /generate orchestration for the developer portal."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException

from repave_engine.blueprint import blueprint_dir, bundles_dir, load_blueprint
from repave_engine.bundle import load_bundle
from repave_engine.bundle_portal import build_bundle_result_portal_context, bundle_member_previews
from repave_engine.bundle_topology import build_bundle_topology, topology_public
from repave_engine.gates import GateResult, all_gates_passed, gate_summary
from repave_engine.pipeline import (
    BundleGenerationResult,
    GenerationResult,
    generate_from_blueprint,
    generate_from_bundle,
)
from repave_engine.portal_result import build_result_portal_context
from repave_engine.publish_idempotency import publish_message_succeeded
from repave_engine.run_queue import RunQueue, RunQueueFullError, RunQueueShuttingDownError
from repave_engine.settings import OutputConfig


@dataclass(frozen=True)
class PublishTarget:
    name: str
    url: str
    org: str


def publish_target_for_run(
    *,
    blueprint: object,
    payload: dict[str, object],
    output_config: OutputConfig,
) -> PublishTarget | None:
    """Best-effort target repo for run-console copy (plan vs apply expectations)."""
    from repave_engine.blueprint import Blueprint, primary_publish_name
    from repave_engine.target_repo import resolve_module_repository

    if not isinstance(blueprint, Blueprint):
        return None
    inputs_raw = payload.get("inputs")
    if not isinstance(inputs_raw, dict):
        return None
    try:
        normalized = {str(key): value for key, value in inputs_raw.items()}
        module_name = primary_publish_name(blueprint, normalized)
        repository = resolve_module_repository(
            module_name=module_name,
            config=output_config,
            name_template=blueprint.output_repo_name_template,
            template_values={key: str(value) for key, value in normalized.items()},
        )
    except (KeyError, TypeError, ValueError):
        return None
    return PublishTarget(
        name=repository.name,
        url=repository.web_url,
        org=output_config.github_org,
    )


class GateToolchainCallout(Protocol):
    def __call__(self, gates: list[GateResult], *, dry_run: bool) -> str | None: ...


def dry_run_from_form(form: object) -> bool:
    """Parse dry_run from multipart form; last value wins when multiple are sent."""
    getlist = getattr(form, "getlist", None)
    if getlist is None:
        get = getattr(form, "get", lambda _k, _d=None: "true")
        return str(get("dry_run", "true")).lower() != "false"
    raw = [str(item).lower() for item in getlist("dry_run") if str(item).strip()]
    if not raw:
        return True
    return raw[-1] != "false"


def plan_preview_from_form(form: object) -> bool:
    get = getattr(form, "get", lambda _k, _d=None: "")
    return str(get("plan_preview", "")).strip() in ("1", "true", "yes")


def stream_from_form(form: object) -> bool:
    get = getattr(form, "get", lambda _k, _d=None: "")
    return str(get("stream", "")).strip() in ("1", "true", "yes")


def blueprint_values_from_form(form: object, blueprint: object) -> dict[str, str]:
    from repave_engine.blueprint import Blueprint

    if not isinstance(blueprint, Blueprint):
        raise TypeError("blueprint must be Blueprint")
    values: dict[str, str] = {}
    get = getattr(form, "get", lambda _k, _d="": "")
    getlist = getattr(form, "getlist", None)
    for field in blueprint.inputs:
        if field.name == "provider_services":
            selected: list[str] = []
            if getlist is not None:
                selected = [str(item) for item in getlist("provider_services") if str(item).strip()]
            if not selected and getlist is not None:
                selected = [
                    str(item) for item in getlist("provider_service_option") if str(item).strip()
                ]
            values[field.name] = ",".join(selected)
            continue

        if field.name == "provider_service_scope":
            values[field.name] = str(get(field.name, ""))
            continue

        if field.enum and field.multi:
            if getlist is None:
                values[field.name] = str(get(field.name, ""))
            else:
                selected = [str(item) for item in getlist(field.name) if str(item).strip()]
                values[field.name] = ",".join(selected)
            continue

        values[field.name] = str(get(field.name, ""))
    return values


@dataclass(frozen=True)
class PortalGenerateRedirect:
    url: str
    status_code: int


@dataclass(frozen=True)
class PortalGenerateTemplate:
    template_name: str
    context: dict[str, object]


def _bundle_values_from_form(form: object, bundle: object) -> dict[str, str]:
    from repave_engine.bundle import Bundle

    if not isinstance(bundle, Bundle):
        raise TypeError("bundle must be Bundle")
    bundle_values: dict[str, str] = {}
    get = getattr(form, "get", lambda _k, _d="": "")
    getlist = getattr(form, "getlist", None)
    for field in bundle.inputs:
        if field.enum and field.multi:
            if getlist is None:
                bundle_values[field.name] = str(get(field.name, ""))
            else:
                selected = [str(item) for item in getlist(field.name) if str(item).strip()]
                bundle_values[field.name] = ",".join(selected)
        else:
            bundle_values[field.name] = str(get(field.name, ""))
    return bundle_values


def run_portal_generate(
    *,
    form: object,
    repo_root: Path,
    output_config: OutputConfig,
    worker_execution_mode: bool,
    run_queue: RunQueue | None,
    acting_user: str | None,
    github_token: str | None,
    dry_run: bool,
    require_run: bool,
    gate_toolchain_callout: GateToolchainCallout,
    generate_from_blueprint_fn: Callable[..., GenerationResult] = generate_from_blueprint,
    generate_from_bundle_fn: Callable[..., BundleGenerationResult] = generate_from_bundle,
) -> PortalGenerateRedirect | PortalGenerateTemplate:
    get = getattr(form, "get", lambda _k, _d="": "")
    bundle_name = str(get("bundle_name", "")).strip()
    queue_user = acting_user or "portal"

    if bundle_name:
        bundle_dir = bundles_dir(repo_root) / bundle_name
        bundle = load_bundle(bundle_dir, repo_root=repo_root)
        bundle_values = _bundle_values_from_form(form, bundle)
        if worker_execution_mode:
            if run_queue is None:
                raise HTTPException(
                    status_code=503,
                    detail="Async generation is required in worker execution mode",
                )
            try:
                record = run_queue.submit(
                    bundle_name=bundle_name,
                    inputs=bundle_values,
                    dry_run=dry_run,
                    acting_user=queue_user,
                )
            except RunQueueFullError as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
            except RunQueueShuttingDownError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc
            return PortalGenerateRedirect(url=f"/runs/{record.run_id}", status_code=303)
        bundle_result = generate_from_bundle_fn(
            bundle,
            bundle_values,
            repo_root=repo_root,
            output_config=output_config,
            dry_run=dry_run,
            require_run=require_run,
            github_token=github_token,
        )
        combined = bundle_result.combined_gates()
        previews = bundle_member_previews(
            bundle,
            bundle_values,
            repo_root=repo_root,
            output_config=output_config,
        )
        topology_nodes, topology_edges = build_bundle_topology(bundle, previews)
        return PortalGenerateTemplate(
            template_name="bundle_result.html",
            context={
                "bundle_result": bundle_result,
                "gate_summary": gate_summary(combined),
                "gates_ok": bundle_result.all_members_passed(),
                "gate_toolchain_callout": gate_toolchain_callout(
                    combined,
                    dry_run=bundle_result.dry_run,
                ),
                "result_portal": build_bundle_result_portal_context(
                    bundle_result,
                    shared_inputs=bundle_result.shared_inputs,
                ),
                "bundle_topology": topology_public(topology_nodes, topology_edges),
            },
        )

    blueprint_name = str(get("blueprint_name", ""))
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    values = blueprint_values_from_form(form, blueprint)

    use_stream = stream_from_form(form) or worker_execution_mode
    if worker_execution_mode:
        if run_queue is None:
            raise HTTPException(
                status_code=503,
                detail="Async generation is required in worker execution mode",
            )
        try:
            record = run_queue.submit(
                blueprint_name=blueprint_name,
                inputs=values,
                dry_run=dry_run,
                acting_user=queue_user,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return PortalGenerateRedirect(url=f"/runs/{record.run_id}", status_code=303)

    if use_stream and run_queue is not None:
        try:
            record = run_queue.submit(
                blueprint_name=blueprint_name,
                inputs=values,
                dry_run=dry_run,
                acting_user=queue_user,
            )
        except RunQueueFullError:
            pass
        except RunQueueShuttingDownError:
            pass
        else:
            return PortalGenerateRedirect(url=f"/runs/{record.run_id}", status_code=303)

    result = generate_from_blueprint_fn(
        blueprint,
        values,
        output_config=output_config,
        dry_run=dry_run,
        require_run=require_run,
        github_token=github_token,
        repo_root=repo_root,
    )
    return PortalGenerateTemplate(
        template_name="result.html",
        context={
            "result": result,
            "gate_summary": gate_summary(result.gates),
            "gates_ok": all_gates_passed(result.gates),
            "publish_ok": result.dry_run or publish_message_succeeded(result.pr_message),
            "gate_toolchain_callout": gate_toolchain_callout(
                result.gates,
                dry_run=result.dry_run,
            ),
            "result_portal": build_result_portal_context(result, repo_root),
        },
    )
