from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repave_engine.audit import AuditRecord, append_audit_record
from repave_engine.audit_history import initial_artifact_version_for_audit
from repave_engine.auth_context import current_acting_user
from repave_engine.blueprint import (
    Blueprint,
    _find_repo_root,
    load_blueprint,
    primary_publish_name,
    validate_inputs,
)
from repave_engine.bundle import (
    Bundle,
    build_bundle_context,
    load_bundle,
    prepare_member_values,
    validate_bundle_inputs,
)
from repave_engine.cost_estimate import (
    audit_extra_for_cost_estimate,
    cost_estimate_from_gates,
)
from repave_engine.fleet import FleetEntry, FleetError, register_repo
from repave_engine.gates import (
    GateResult,
    RunEventCallback,
    all_gates_passed,
    clean_gate_artifacts,
    gate_outcome,
    run_gates,
)
from repave_engine.github_repo_provision import build_provision_spec
from repave_engine.infracost_policy import effective_gate_names
from repave_engine.metrics import GENERATION_DURATION, GENERATION_TOTAL
from repave_engine.notifications import GenerationNotificationContext, notify_after_generation
from repave_engine.pr import PullRequestPlan, create_pull_request, plan_pull_request
from repave_engine.provenance import require_provenance_for_publish
from repave_engine.publish_idempotency import (
    PublishIdempotencyContext,
    build_publish_key,
    compute_publish_content_hash,
    publish_message_succeeded,
)
from repave_engine.render import (
    RenderedFile,
    RenderResult,
    collect_rendered_files,
    render_blueprint,
)
from repave_engine.settings import (
    OutputConfig,
    load_audit_config,
    load_fleet_config,
    load_gate_overrides,
)
from repave_engine.target_repo import (
    ModuleRepository,
    publish_to_module_repository,
    resolve_module_repository,
)
from repave_engine.tracing import pipeline_span


def _fleet_message_after_github_repo_publish(
    *,
    repo_root: Path | None,
    blueprint: Blueprint,
    repository: ModuleRepository,
) -> str:
    """Best-effort fleet register so fleetsync/manifests can emit GoldenPathRepo."""
    if repo_root is None:
        return "Fleet disabled; run repave register / fleet-manifests to emit GoldenPathRepo"
    fleet_config = load_fleet_config(repo_root)
    if fleet_config is None or not fleet_config.enabled:
        return "Fleet disabled; run repave register / fleet-manifests to emit GoldenPathRepo"
    try:
        register_repo(
            fleet_config.file,
            FleetEntry(
                repo_url=repository.web_url,
                blueprint_name=blueprint.name,
                blueprint_version=blueprint.version,
                standard_source=blueprint.standard_source,
                standard_version=blueprint.standard_version,
            ),
            repo_root=repo_root,
        )
    except (FleetError, OSError) as exc:
        return f"Fleet register failed (provision succeeded): {exc}"
    return f"Fleet registered: {repository.web_url}"


@dataclass(frozen=True)
class GenerationResult:
    blueprint: Blueprint
    render: RenderResult
    gates: list[GateResult]
    module_repository: ModuleRepository | None
    pr_plan: PullRequestPlan | None
    pr_message: str
    rendered_files: tuple[RenderedFile, ...] = ()
    dry_run: bool = True
    member_id: str | None = None


@dataclass(frozen=True)
class BundleMemberResult:
    member_id: str
    result: GenerationResult


@dataclass(frozen=True)
class BundleGenerationResult:
    bundle: Bundle
    members: tuple[BundleMemberResult, ...]
    dry_run: bool = True
    shared_inputs: dict[str, str] = field(default_factory=dict)

    def combined_gates(self) -> list[GateResult]:
        gates: list[GateResult] = []
        for member in self.members:
            gates.extend(member.result.gates)
        return gates

    def all_members_passed(self) -> bool:
        return all(all_gates_passed(member.result.gates) for member in self.members)


def _record_operability(
    config_root: Path,
    *,
    blueprint: Blueprint,
    module_name: str,
    dry_run: bool,
    gates: list[GateResult],
    repository: ModuleRepository | None,
    started_at: float,
) -> None:
    elapsed = time.perf_counter() - started_at
    outcome = gate_outcome(gates)
    GENERATION_DURATION.labels(blueprint=blueprint.name).observe(elapsed)
    GENERATION_TOTAL.labels(outcome=outcome, blueprint=blueprint.name).inc()

    try:
        audit_cfg = load_audit_config(config_root)
    except ValueError:
        audit_cfg = None
    if audit_cfg is None or not audit_cfg.enabled:
        return
    extra: dict[str, Any] = {
        "duration_seconds": round(elapsed, 3),
        "artifact_version": initial_artifact_version_for_audit(),
    }
    extra.update(audit_extra_for_cost_estimate(cost_estimate_from_gates(gates)))
    append_audit_record(
        audit_cfg.file,
        AuditRecord(
            event="generation",
            blueprint_name=blueprint.name,
            blueprint_version=blueprint.version,
            module_name=module_name,
            dry_run=dry_run,
            gates_outcome=outcome,
            repository_url=repository.web_url if repository is not None else None,
            acting_user=current_acting_user(),
            extra=extra,
        ),
        repo_root=config_root,
    )


def _emit_stage(on_event: RunEventCallback | None, stage: str, *, started: bool) -> None:
    if on_event is None:
        return
    kind = "stage_started" if started else "stage_finished"
    on_event(kind, {"stage": stage})


def _publish_error_detail(pr_message: str) -> str:
    lowered = pr_message.lower()
    if "github publish failed" not in lowered and "provisioning failed" not in lowered:
        return ""
    lines = [line.strip() for line in pr_message.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        if "github publish failed" in line.lower() or "provisioning failed" in line.lower():
            return "\n".join(lines[index:])
    return pr_message.strip()


def _summarize_publish_message(
    *,
    dry_run: bool,
    repository: ModuleRepository,
    pr_message: str,
) -> str:
    lowered = pr_message.lower()
    if "github publish failed" in lowered or "provisioning failed" in lowered:
        detail = _publish_error_detail(pr_message)
        error_line = detail.splitlines()[-1] if detail else ""
        if error_line.lower().startswith("error"):
            return f"Publish failed — {error_line}"
        return f"Publish failed for {repository.web_url}"
    if dry_run:
        return f"Plan preview — no GitHub repo created. Target on apply: {repository.web_url}"
    if "created github repository" in lowered:
        return f"Created {repository.web_url}"
    if "pushed initial commit" in lowered:
        return f"Updated {repository.web_url}"
    return f"Published to {repository.web_url}"


def _emit_publish_progress(
    on_event: RunEventCallback | None,
    *,
    dry_run: bool,
    repository: ModuleRepository,
    message: str,
) -> None:
    if on_event is None:
        return
    on_event(
        "publish_progress",
        {
            "dry_run": dry_run,
            "repository_name": repository.name,
            "repository_url": repository.web_url,
            "message": message,
        },
    )


def _emit_publish_finished(
    on_event: RunEventCallback | None,
    *,
    dry_run: bool,
    repository: ModuleRepository,
    pr_message: str,
) -> None:
    if on_event is None:
        return
    detail = _publish_error_detail(pr_message)
    on_event(
        "publish_finished",
        {
            "dry_run": dry_run,
            "repository_name": repository.name,
            "repository_url": repository.web_url,
            "summary": _summarize_publish_message(
                dry_run=dry_run,
                repository=repository,
                pr_message=pr_message,
            ),
            "detail": detail,
            "succeeded": publish_message_succeeded(pr_message),
        },
    )


def _publish_after_gates(
    *,
    blueprint: Blueprint,
    render_result: RenderResult,
    module_repository: ModuleRepository,
    normalized: dict[str, Any],
    dry_run: bool,
    github_token: str | None,
    on_event: RunEventCallback | None,
    publish_idempotency: PublishIdempotencyContext | None,
    repo_root: Path | None = None,
    gate_results: tuple[GateResult, ...] = (),
) -> tuple[str, ModuleRepository | None]:
    content_hash = compute_publish_content_hash(
        render_result.output_dir,
        artifact_type=blueprint.artifact_type,
    )
    publish_key = build_publish_key(module_repository, content_hash)
    cached_message: str | None = None
    store = (
        publish_idempotency.store
        if publish_idempotency is not None and not dry_run and github_token
        else None
    )
    if store is not None:
        receipt = store.get(publish_key)
        if receipt is not None:
            cached_message = receipt.pr_message

    with pipeline_span("repave.publish"):
        _emit_stage(on_event, "publish", started=True)
        _emit_publish_progress(
            on_event,
            dry_run=dry_run,
            repository=module_repository,
            message=(
                f"Planning publish target {module_repository.web_url} (no GitHub write)"
                if dry_run
                else f"Publishing to {module_repository.web_url}…"
            ),
        )
        if cached_message is not None:
            pr_message = cached_message
            published_repository = module_repository
        else:
            if not dry_run:
                require_provenance_for_publish(
                    render_result.output_dir,
                    blueprint,
                    repo_root=repo_root,
                )
            publish_message = publish_to_module_repository(
                render_result.output_dir,
                module_repository,
                dry_run=dry_run,
                artifact_type=blueprint.artifact_type,
            )
            provision = None
            if blueprint.artifact_type == "github-repo":
                provision = build_provision_spec(
                    repository=module_repository,
                    values=normalized,
                )
            pr_plan = plan_pull_request(
                blueprint_name=blueprint.name,
                blueprint_version=blueprint.version,
                standard_version=blueprint.standard_version,
                title_template=blueprint.output_title_template,
                input_fields=tuple(field.name for field in blueprint.inputs),
                files_root=module_repository.local_path,
                repository=module_repository,
                module_values=normalized,
                repo_root=repo_root,
                gate_results=gate_results,
                provision=provision,
            )
            if dry_run:
                pr_body = create_pull_request(
                    pr_plan,
                    github_token=None,
                    fleet_message=(
                        "Fleet: dry-run; apply with fleet enabled to register a "
                        "GoldenPathRepo target"
                    ),
                )
            else:
                pr_body = create_pull_request(pr_plan, github_token=github_token)
            pr_message = f"{publish_message}\n\n{pr_body}"
            published_repository = module_repository
            if not dry_run and publish_message_succeeded(pr_message):
                fleet_line = _fleet_message_after_github_repo_publish(
                    repo_root=repo_root,
                    blueprint=blueprint,
                    repository=module_repository,
                )
                pr_message = f"{pr_message}\n{fleet_line}"
            if (
                store is not None
                and publish_idempotency is not None
                and publish_message_succeeded(pr_message)
            ):
                store.record(
                    publish_key=publish_key,
                    pr_message=pr_message,
                    repository_web_url=module_repository.web_url,
                    content_hash=content_hash,
                    run_id=publish_idempotency.run_id,
                    client_request_id=publish_idempotency.client_request_id,
                )
        _emit_publish_finished(
            on_event,
            dry_run=dry_run,
            repository=module_repository,
            pr_message=pr_message,
        )
        _emit_stage(on_event, "publish", started=False)
    return pr_message, published_repository


def generate_from_blueprint(
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    output_config: OutputConfig,
    dry_run: bool = True,
    require_run: bool | None = None,
    github_token: str | None = None,
    staging_root: Path | None = None,
    repo_root: Path | None = None,
    record_operability: bool = True,
    send_notification: bool = True,
    member_id: str | None = None,
    skip_input_validation: bool = False,
    on_event: RunEventCallback | None = None,
    publish_idempotency: PublishIdempotencyContext | None = None,
) -> GenerationResult:
    started_at = time.perf_counter()
    pack_root = repo_root if repo_root is not None else _find_repo_root(blueprint.path)
    gate_overrides = load_gate_overrides(pack_root)
    catalog_root = _find_repo_root(blueprint.path)
    with pipeline_span("repave.validate"):
        _emit_stage(on_event, "validate", started=True)
        if skip_input_validation:
            normalized = dict(values)
        else:
            normalized = validate_inputs(
                blueprint,
                values,
                repo_root=catalog_root,
                gate_overrides=gate_overrides,
            )
        _emit_stage(on_event, "validate", started=False)
    module_name = primary_publish_name(blueprint, normalized)
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=normalized,
    )

    if staging_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="repave-staging-")
        staging_dir = Path(temp_dir.name)
        owns_staging = True
    else:
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root
        temp_dir = None
        owns_staging = False

    try:
        with pipeline_span("repave.render"):
            _emit_stage(on_event, "render", started=True)
            render_result = render_blueprint(blueprint, normalized, staging_dir)
            _emit_stage(on_event, "render", started=False)
        run_gate_overrides = (
            load_gate_overrides(repo_root) if repo_root is not None else gate_overrides
        )
        with pipeline_span("repave.gates"):
            _emit_stage(on_event, "gates", started=True)
            gate_require_run = dry_run if require_run is None else require_run
            if dry_run:
                gate_require_run = True
            gate_results = run_gates(
                render_result.output_dir,
                effective_gate_names(blueprint, run_gate_overrides),
                blueprint=blueprint,
                gate_overrides=run_gate_overrides,
                require_run=gate_require_run,
                on_event=on_event,
            )
            _emit_stage(on_event, "gates", started=False)
        clean_gate_artifacts(render_result.output_dir, artifact_type=blueprint.artifact_type)

        pr_plan: PullRequestPlan | None = None
        pr_message = "Gates failed; module repository not updated."
        published_repository: ModuleRepository | None = module_repository

        if all_gates_passed(gate_results):
            pr_message, published_repository = _publish_after_gates(
                blueprint=blueprint,
                render_result=render_result,
                module_repository=module_repository,
                normalized=normalized,
                dry_run=dry_run,
                github_token=github_token,
                on_event=on_event,
                publish_idempotency=publish_idempotency,
                repo_root=repo_root,
                gate_results=tuple(gate_results),
            )
            provision = None
            if blueprint.artifact_type == "github-repo":
                provision = build_provision_spec(
                    repository=module_repository,
                    values=normalized,
                )
            pr_plan = plan_pull_request(
                blueprint_name=blueprint.name,
                blueprint_version=blueprint.version,
                standard_version=blueprint.standard_version,
                title_template=blueprint.output_title_template,
                input_fields=tuple(field.name for field in blueprint.inputs),
                files_root=module_repository.local_path,
                repository=module_repository,
                module_values=normalized,
                repo_root=repo_root,
                gate_results=tuple(gate_results),
                provision=provision,
            )
        else:
            published_repository = None
            if dry_run:
                publish_message = publish_to_module_repository(
                    render_result.output_dir,
                    module_repository,
                    dry_run=dry_run,
                    artifact_type=blueprint.artifact_type,
                )
                pr_message = f"{publish_message}\n\nGates failed; fix gate errors before publish."

        result_repository = module_repository if dry_run else published_repository

        rendered_files = (
            collect_rendered_files(
                render_result.output_dir,
                artifact_type=blueprint.artifact_type,
            )
            if dry_run
            else ()
        )
        if dry_run:
            display_output_dir = render_result.output_dir
        elif published_repository is not None:
            display_output_dir = module_repository.local_path
        else:
            display_output_dir = render_result.output_dir
        display_render = RenderResult(output_dir=display_output_dir, values=render_result.values)

        if send_notification:
            notify_after_generation(
                catalog_root,
                context=GenerationNotificationContext(
                    blueprint=blueprint,
                    gates=gate_results,
                    dry_run=dry_run,
                    pr_message=pr_message,
                    repository_web_url=(
                        published_repository.web_url if published_repository is not None else None
                    ),
                    module_name=module_name,
                ),
            )

        if record_operability:
            _record_operability(
                pack_root,
                blueprint=blueprint,
                module_name=module_name,
                dry_run=dry_run,
                gates=gate_results,
                repository=published_repository,
                started_at=started_at,
            )

        return GenerationResult(
            blueprint=blueprint,
            render=display_render,
            gates=gate_results,
            module_repository=result_repository,
            pr_plan=pr_plan,
            pr_message=pr_message,
            rendered_files=rendered_files,
            dry_run=dry_run,
            member_id=member_id,
        )
    finally:
        if owns_staging and temp_dir is not None:
            temp_dir.cleanup()


def generate_from_path(
    blueprint_path: Path,
    values: dict[str, Any],
    *,
    repo_root: Path,
    output_config: OutputConfig,
    dry_run: bool = True,
    github_token: str | None = None,
    staging_root: Path | None = None,
) -> GenerationResult:
    blueprint = load_blueprint(blueprint_path, repo_root=repo_root)
    return generate_from_blueprint(
        blueprint,
        values,
        output_config=output_config,
        dry_run=dry_run,
        github_token=github_token,
        staging_root=staging_root,
        repo_root=repo_root,
    )


def _record_bundle_operability(
    catalog_root: Path,
    *,
    bundle: Bundle,
    dry_run: bool,
    gates: list[GateResult],
    started_at: float,
    shared_inputs: dict[str, str],
    member_results: tuple[BundleMemberResult, ...],
) -> None:
    from repave_engine.bundle_portal import build_bundle_provenance_document

    elapsed = time.perf_counter() - started_at
    outcome = gate_outcome(gates)
    GENERATION_DURATION.labels(blueprint=bundle.name).observe(elapsed)
    GENERATION_TOTAL.labels(outcome=outcome, blueprint=bundle.name).inc()
    try:
        audit_cfg = load_audit_config(catalog_root)
    except ValueError:
        audit_cfg = None
    if audit_cfg is None or not audit_cfg.enabled:
        return
    provenance = build_bundle_provenance_document(bundle, shared_inputs, member_results)
    append_audit_record(
        audit_cfg.file,
        AuditRecord(
            event="bundle_generation",
            blueprint_name=bundle.name,
            blueprint_version=bundle.version,
            module_name=bundle.name,
            dry_run=dry_run,
            gates_outcome=outcome,
            repository_url=None,
            acting_user=current_acting_user(),
            extra={
                "duration_seconds": round(elapsed, 3),
                "member_count": len(member_results),
                "bundle_provenance": provenance,
            },
        ),
        repo_root=catalog_root,
    )


def generate_from_bundle(
    bundle: Bundle,
    values: dict[str, Any],
    *,
    repo_root: Path,
    output_config: OutputConfig,
    dry_run: bool = True,
    require_run: bool | None = None,
    github_token: str | None = None,
    staging_root: Path | None = None,
    record_bundle_operability: bool = True,
) -> BundleGenerationResult:
    started_at = time.perf_counter()
    catalog_root = repo_root
    shared = validate_bundle_inputs(bundle, values)
    context = build_bundle_context(shared, github_org=output_config.github_org)
    gate_overrides = load_gate_overrides(repo_root)

    plan_members: list[tuple[Any, Blueprint, dict[str, Any]]] = []
    for member in bundle.members:
        blueprint, normalized = prepare_member_values(
            repo_root,
            member,
            context,
            gate_overrides=gate_overrides,
        )
        plan_members.append((member, blueprint, normalized))

    def _run_members(*, apply: bool) -> list[BundleMemberResult]:
        results: list[BundleMemberResult] = []
        for member, blueprint, normalized in plan_members:
            member_staging = None
            if staging_root is not None:
                member_staging = staging_root / bundle.name / member.member_id
            result = generate_from_blueprint(
                blueprint,
                normalized,
                output_config=output_config,
                dry_run=not apply,
                require_run=require_run,
                github_token=github_token if apply else None,
                staging_root=member_staging,
                repo_root=repo_root,
                record_operability=False,
                send_notification=False,
                member_id=member.member_id,
                skip_input_validation=True,
            )
            results.append(BundleMemberResult(member_id=member.member_id, result=result))
        return results

    member_results = _run_members(apply=False)
    if not dry_run and all(all_gates_passed(item.result.gates) for item in member_results):
        member_results = _run_members(apply=True)

    combined = []
    for item in member_results:
        combined.extend(item.result.gates)

    notify_after_generation(
        catalog_root,
        context=GenerationNotificationContext(
            blueprint=plan_members[0][1],
            gates=combined,
            dry_run=dry_run,
            pr_message=f"Bundle {bundle.name} ({len(member_results)} members)",
            repository_web_url=None,
            module_name=bundle.name,
        ),
    )

    if record_bundle_operability:
        _record_bundle_operability(
            catalog_root,
            bundle=bundle,
            dry_run=dry_run,
            gates=combined,
            started_at=started_at,
            shared_inputs=shared,
            member_results=tuple(member_results),
        )

    return BundleGenerationResult(
        bundle=bundle,
        members=tuple(member_results),
        dry_run=dry_run,
        shared_inputs=dict(shared),
    )


def generate_bundle_from_path(
    bundle_path: Path,
    values: dict[str, Any],
    *,
    repo_root: Path,
    output_config: OutputConfig,
    dry_run: bool = True,
    require_run: bool | None = None,
    github_token: str | None = None,
    staging_root: Path | None = None,
) -> BundleGenerationResult:
    bundle = load_bundle(bundle_path, repo_root=repo_root)
    return generate_from_bundle(
        bundle,
        values,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=dry_run,
        require_run=require_run,
        github_token=github_token,
        staging_root=staging_root,
    )
