from __future__ import annotations

import logging
import os
import secrets
import signal
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from repave_engine import __version__
from repave_engine.ansible_catalog import catalog_for_api as ansible_catalog_for_api
from repave_engine.ansible_catalog import load_ansible_catalog
from repave_engine.ansible_pattern import (
    blueprint_supports_collection_sample_patterns,
    blueprint_supports_playbook_patterns,
    blueprint_supports_role_patterns,
)
from repave_engine.ansible_platforms import parse_support_flag
from repave_engine.ansible_role_inventory import (
    inventory_role_versions_json,
    inventory_roles_json,
)
from repave_engine.api_auth import build_auth_router
from repave_engine.api_deprecation import V1_DEPRECATION_HEADERS
from repave_engine.api_ops import build_ops_router
from repave_engine.api_v1 import build_api_v1_router
from repave_engine.api_v2 import build_api_v2_router
from repave_engine.audit_history import (
    AuditHistoryEntry,
    AuditQueryFilters,
    audit_filters_from_mapping,
    query_audit_entries,
)
from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    AuthConfig,
    authenticated_user,
    is_public_path,
    require_role,
    session_user,
)
from repave_engine.auth_context import current_acting_user, reset_acting_user, set_acting_user
from repave_engine.blueprint import (
    artifact_family,
    blueprint_dir,
    blueprints_dir,
    bundles_dir,
    group_blueprints_by_artifact,
    list_blueprints,
    load_blueprint,
    policy_kind_label,
)
from repave_engine.bundle import list_bundles, load_bundle
from repave_engine.bundle_portal import (
    build_bundle_result_portal_context,
    bundle_member_previews,
)
from repave_engine.bundle_topology import build_bundle_topology, topology_public
from repave_engine.catalog_cost import enrich_catalog_entities_with_cost, enrich_entity_cost
from repave_engine.catalog_deployment import (
    deployment_scorecard_for_entity,
    enrich_catalog_entities_with_deployment,
)
from repave_engine.cost_actuals import cost_reader_configured
from repave_engine.dashboard_pack import blueprint_supports_dashboard_packs
from repave_engine.diff_view import diff_view_models_from_files
from repave_engine.durability_store import load_durability_runtime
from repave_engine.entity_catalog import (
    filter_entities_by_owner,
    find_catalog_entity,
    group_catalog_entities,
    observability_embed_url,
    rollup_fleet_scorecard,
)
from repave_engine.environment_reclaim import reclaim_expired_environments
from repave_engine.environment_vend import DEFAULT_VEND_BLUEPRINT
from repave_engine.estate_map import build_estate_tiles
from repave_engine.execution_mode import ExecutionMode
from repave_engine.fleet import FleetError
from repave_engine.fleet_operator_actions import patch_upgrade_campaign_paused
from repave_engine.gates import GateResult, all_gates_passed, gate_summary
from repave_engine.generate_api import (
    bundle_result_from_stored_run,
    generation_result_from_stored_run,
)
from repave_engine.github_auth import github_credentials_configured, resolve_github_access_token
from repave_engine.github_client import GitHubError
from repave_engine.governance_preflight import build_bundle_preflight
from repave_engine.import_rules import parse_path_overrides
from repave_engine.module_inventory import inventory_modules_json, inventory_versions_json
from repave_engine.monitor_pack import blueprint_supports_monitor_packs
from repave_engine.observability_catalog import catalog_for_api as observability_catalog_for_api
from repave_engine.observability_catalog import (
    load_observability_catalog,
)
from repave_engine.observability_selection import (
    blueprint_supports_observability_field_catalog,
    blueprint_supports_observability_notifications,
    observability_input_defaults,
)
from repave_engine.observability_slo import fetch_entity_slo_summary
from repave_engine.pipeline import generate_from_blueprint, generate_from_bundle
from repave_engine.policy_catalog import (
    catalog_for_api,
    load_policy_catalog,
)
from repave_engine.policy_selection import (
    blueprint_supports_optional_policy,
    blueprint_supports_policy_customization,
    policy_input_defaults,
)
from repave_engine.portal_blueprint_view import build_blueprint_form_extras
from repave_engine.portal_components import (
    build_component_add_context,
    component_add_redirect_url,
)
from repave_engine.portal_context import (
    audit_file_or_http404,
    audit_portal_enabled,
    build_portal_catalog_entities,
    portal_fleet_context,
    portal_recent_activity,
    resolve_entity_docs,
)
from repave_engine.portal_generate import (
    PortalGenerateRedirect,
    run_portal_generate,
)
from repave_engine.portal_generate import (
    dry_run_from_form as _dry_run_from_form,
)
from repave_engine.portal_generate import (
    plan_preview_from_form as _plan_preview_from_form,
)
from repave_engine.portal_markdown import render_portal_markdown
from repave_engine.portal_platform import (
    build_platform_adoption_page,
    build_platform_campaigns_page,
    build_platform_fleet_page,
    build_platform_ops_page,
    build_platform_standards_detail,
    build_platform_standards_page,
    find_campaign_in_snapshot,
    platform_admin_visible,
    register_fleet_entry_from_form,
    require_platform_admin,
    unregister_fleet_entry,
)
from repave_engine.portal_result import build_result_portal_context
from repave_engine.pr_conventions import add_pull_request_title, load_pull_request_conventions
from repave_engine.provider_catalog import get_service_definition, load_provider_catalog
from repave_engine.repo_add import (
    NotGovernedError,
    RepoAddError,
    apply_add,
    plan_add,
    record_add_from_env,
    suggested_add_branch,
)
from repave_engine.repo_import import (
    AlreadyGovernedError,
    ImportPlan,
    RepoImportError,
    import_repository,
    import_repository_batch,
    plan_import,
    plan_import_batch,
    record_import,
    suggested_import_branch,
)
from repave_engine.run_queue import (
    RunQueue,
    RunQueueConfig,
    RunQueueFullError,
    RunQueueShuttingDownError,
    build_run_queue,
)
from repave_engine.run_store import RunStatus
from repave_engine.run_submit import (
    is_bundle_run,
    is_environment_vend_run,
    is_live_plan_run,
    submit_async_run,
)
from repave_engine.service_inventory import (
    load_merged_observability_catalog,
    services_inventory_json,
)
from repave_engine.session_store import load_session_store
from repave_engine.settings import (
    OutputConfig,
    load_auth_config,
    load_durability_config,
    load_environment_vending_config,
    load_live_plan_config,
    load_output_config,
    load_portal_config,
    load_tracing_config,
    validate_hosted_service_config,
)
from repave_engine.sql_session_middleware import SqlSessionMiddleware
from repave_engine.tracing import configure_tracing
from repave_engine.upgrade_plan import UpgradePlanResult, plan_upgrade
from repave_engine.verify import VerifyError, verify_target


def _default_environment_stack_name(entity_id: str, display_name: str) -> str:
    slug = entity_id.rsplit("/", 1)[-1].strip() if entity_id else ""
    if not slug:
        slug = "".join(
            ch if ch.isalnum() or ch == "-" else "-" for ch in display_name.lower()
        ).strip("-")
    return (slug or "stack")[:63]


def create_app(*, repo_root: Path, output_config: OutputConfig | None = None) -> FastAPI:
    package_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(package_dir / "templates"))
    templates.env.cache = None
    templates.env.globals["artifact_family"] = artifact_family
    templates.env.globals["policy_kind_label"] = policy_kind_label
    resolved_output = output_config or load_output_config(repo_root)
    portal_config = load_portal_config(repo_root)
    try:
        auth_config = load_auth_config(repo_root)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    try:
        validate_hosted_service_config(repo_root, auth_config=auth_config)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc

    durability_config = load_durability_config(repo_root)
    durability_runtime = load_durability_runtime(repo_root)
    worker_execution_mode = durability_runtime.execution_mode == ExecutionMode.WORKER
    run_queue: RunQueue | None = None
    if durability_config is not None:
        run_queue = build_run_queue(
            repo_root,
            resolved_output,
            RunQueueConfig(
                max_concurrent_runs=durability_config.max_concurrent_runs,
                queue_max_depth=durability_config.queue_max_depth,
                db_path=durability_config.runs_db,
                max_attempts=durability_config.max_run_attempts,
                stale_run_seconds=durability_config.run_stale_seconds,
                retry_base_seconds=durability_config.run_retry_base_seconds,
            ),
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.shutting_down = False
        logger = logging.getLogger(__name__)

        def on_sigterm(signum: int, _frame: object) -> None:
            app.state.shutting_down = True
            queue = getattr(app.state, "run_queue", None)
            if queue is not None:
                queue.stop_accepting()

        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, on_sigterm)

        yield

        app.state.shutting_down = True
        queue = getattr(app.state, "run_queue", None)
        if queue is not None:
            queue.stop_accepting()
            drain_raw = os.environ.get("REPAVE_SHUTDOWN_DRAIN_SECONDS", "105").strip()
            try:
                drain_seconds = float(drain_raw)
            except ValueError:
                drain_seconds = 105.0
            if drain_seconds > 0:
                drained = queue.drain(drain_seconds)
                if not drained:
                    logger.warning(
                        "run queue still has %s in-flight jobs after %.0fs drain",
                        queue.queue_depth(),
                        drain_seconds,
                    )
            queue.close(wait=True)

    app = FastAPI(title="repave", version=__version__, lifespan=lifespan)
    app.state.run_queue = run_queue
    app.state.shutting_down = False

    @app.middleware("http")
    async def v1_deprecation_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        response = await call_next(request)
        if request.url.path.startswith("/api/v1"):
            for key, value in V1_DEPRECATION_HEADERS.items():
                response.headers[key] = value
        return response

    configure_tracing(load_tracing_config(repo_root))

    session_secret = os.environ.get("REPAVE_SESSION_SECRET", "").strip()
    if auth_config is not None and auth_config.service_enabled:
        session_secret = auth_config.session_secret
    elif not session_secret:
        if durability_config is not None and durability_config.require_session_secret:
            raise RuntimeError(
                "REPAVE_SESSION_SECRET is required when durability.require_session_secret "
                "is enabled"
            )
        session_secret = secrets.token_hex(32)
    app.mount(
        "/static",
        StaticFiles(directory=str(package_dir / "static")),
        name="static",
    )

    def page_context(request: Request | None = None, **extra: object) -> dict[str, object]:
        from repave_engine.gate_toolchain import portal_runtime_info

        auth_user = session_user(request) if request is not None else None
        presenter = False
        if request is not None:
            presenter = request.query_params.get("presenter", "").strip().lower() in (
                "1",
                "true",
                "yes",
            )
        return {
            "app_version": __version__,
            "env_badge": os.environ.get("REPAVE_ENV"),
            "local_toolchain_warning": local_portal_toolchain_warning(),
            "portal_runtime": portal_runtime_info(),
            "portal_density": portal_config.density,
            "presenter_mode": presenter,
            "auth_enabled": auth_config is not None and auth_config.service_enabled,
            "auth_user": auth_user,
            "platform_admin_visible": platform_admin_visible(auth_config, auth_user),
            "async_generation_enabled": run_queue is not None,
            "async_generation_required": worker_execution_mode and run_queue is not None,
            "worker_execution_mode": worker_execution_mode,
            "command_palette_items": command_palette_items(request),
            **extra,
        }

    def command_palette_items(request: Request | None = None) -> list[dict[str, str]]:
        items: list[dict[str, str]] = [
            {"kind": "nav", "label": "Catalog", "href": "/"},
            {"kind": "nav", "label": "Library", "href": "/library"},
            {"kind": "nav", "label": "Import repo", "href": "/import"},
            {"kind": "nav", "label": "Upgrade repo", "href": "/update"},
            {"kind": "nav", "label": "Verify repo", "href": "/verify"},
            {"kind": "nav", "label": "Estate map", "href": "/estate"},
            {"kind": "nav", "label": "Activity", "href": "/activity"},
            {"kind": "action", "label": "Resume last run", "action": "resume-last-run"},
        ]
        if run_queue is not None:
            items.insert(
                len(items) - 1,
                {"kind": "nav", "label": "Async runs", "href": "/runs"},
            )
        auth_user = session_user(request) if request is not None else None
        if platform_admin_visible(auth_config, auth_user):
            items.extend(
                [
                    {"kind": "nav", "label": "Platform fleet", "href": "/platform/fleet"},
                    {"kind": "nav", "label": "Platform ops", "href": "/platform/ops"},
                    {"kind": "nav", "label": "Platform standards", "href": "/platform/standards"},
                    {"kind": "nav", "label": "Platform campaigns", "href": "/platform/campaigns"},
                ]
            )
        for blueprint in list_blueprints(blueprints_dir(repo_root)):
            items.append(
                {
                    "kind": "blueprint",
                    "label": blueprint.name,
                    "href": f"/blueprints/{blueprint.name}",
                }
            )
        for bundle in list_bundles(repo_root):
            items.append(
                {
                    "kind": "bundle",
                    "label": bundle.name,
                    "href": f"/bundles/{bundle.name}",
                }
            )
        return items

    session_store = load_session_store(repo_root)
    app.state.session_store = session_store

    @app.middleware("http")
    async def enforce_service_auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        if auth_config is None or not auth_config.service_enabled:
            return await call_next(request)
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)
        user = authenticated_user(request, auth_config)
        if user is None:
            if request.method == "POST" and path in {
                "/generate",
                "/update",
                "/verify",
                "/api/v1/generate",
                "/api/v1/verify",
                "/api/v2/generate",
            }:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Authentication required"},
                )
            if path.startswith("/api/"):
                return JSONResponse(status_code=401, content={"detail": "Authentication required"})
            login = f"/auth/login?next={path}"
            return RedirectResponse(login, status_code=302)
        token = set_acting_user(user.email or user.subject)
        try:
            return await call_next(request)
        finally:
            reset_acting_user(token)

    # Registered last so it wraps enforce_service_auth: Starlette runs the most recently
    # added middleware outermost, and enforce_service_auth reads request.session.
    session_https_only = bool(auth_config.session_https_only) if auth_config is not None else False
    if session_store is not None:
        app.add_middleware(
            SqlSessionMiddleware,
            secret_key=session_secret,
            session_store=session_store,
            same_site="lax",
            https_only=session_https_only,
        )
    else:
        app.add_middleware(
            SessionMiddleware,
            secret_key=session_secret,
            same_site="lax",
            https_only=session_https_only,
        )

    def gate_toolchain_callout(gates: list[GateResult], *, dry_run: bool) -> str | None:
        if not dry_run or not gates:
            return None
        markers = (
            "not available",
            "not installed",
            "Dry-run preview runs all blueprint gates",
            "plan JSON could not be produced",
        )
        for gate in gates:
            if any(marker in gate.message for marker in markers):
                return (
                    "Plan mode runs the full gate toolchain on this server. Missing CLIs show as "
                    "skipped or failed rows above. For a complete local demo, use "
                    "deploy/local Docker Compose (see deploy/local/README.md) or install the same "
                    "tools as CI via deploy/local/install-gate-toolchain.sh."
                )
        return None

    def local_portal_toolchain_warning() -> str | None:
        if os.environ.get("REPAVE_ENV") != "local":
            return None
        from repave_engine.gate_toolchain import gate_tool_status, portal_runtime_info

        runtime = portal_runtime_info()
        if runtime.get("in_container"):
            return None
        status = gate_tool_status()
        missing = [name for name, ok in status.items() if not ok]
        if not missing:
            return (
                "This portal is running on the host (not Docker). For the full gate toolchain on "
                "macOS, Linux, or Windows, use deploy/local Docker Compose at "
                "http://localhost:8088 — no local Terraform/Checkov install required."
            )
        tools = ", ".join(missing)
        return (
            "Host server is missing gate tools "
            f"({tools}). You do not need to install them locally: "
            "run deploy/local Docker Compose and open http://localhost:8088 "
            "(works on Windows with Docker Desktop). Optional native dev: "
            "deploy/local/install-gate-toolchain.sh inside Linux or WSL only. "
            f"Engine v{__version__}."
        )

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        blueprints = list_blueprints(blueprints_dir(repo_root))
        catalog_groups = group_blueprints_by_artifact(blueprints)
        catalog_bundles = list_bundles(repo_root)
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(
                request,
                blueprints=blueprints,
                catalog_groups=catalog_groups,
                catalog_bundles=catalog_bundles,
                nav_active="catalog",
                recent_activity=portal_recent_activity(repo_root),
            ),
        )

    @app.get("/activity", response_class=HTMLResponse)
    async def activity_page(request: Request) -> HTMLResponse:
        activity_limit = 50
        raw_filters = {key: str(value) for key, value in request.query_params.items()}
        activity_filters = audit_filters_from_mapping(raw_filters)
        activity_filters = AuditQueryFilters(
            blueprint_name=activity_filters.blueprint_name,
            module_name=activity_filters.module_name,
            repository_url=activity_filters.repository_url,
            acting_user=activity_filters.acting_user,
            gates_outcome=activity_filters.gates_outcome,
            since=activity_filters.since,
            until=activity_filters.until,
            limit=activity_limit,
            offset=activity_filters.offset,
        )
        query_result = None
        recent: tuple[AuditHistoryEntry, ...] = ()
        enabled = audit_portal_enabled(repo_root)
        if enabled:
            audit_path = audit_file_or_http404(repo_root)
            query_result = query_audit_entries(
                audit_path,
                activity_filters,
                repo_root=repo_root,
            )
            recent = query_result.entries
        return templates.TemplateResponse(
            request,
            "activity.html",
            page_context(
                request,
                nav_active="activity",
                recent_activity=recent,
                audit_enabled=enabled,
                activity_limit=activity_limit,
                activity_filters=activity_filters,
                activity_total=query_result.total if query_result is not None else 0,
            ),
        )

    @app.get("/fleet", response_class=RedirectResponse)
    async def fleet_redirect() -> RedirectResponse:
        return RedirectResponse(url="/library", status_code=302)

    @app.get("/estate", response_class=HTMLResponse)
    async def estate_map_page(request: Request) -> HTMLResponse:
        enabled, fleet_repos, _namespace = portal_fleet_context(repo_root)
        audit_entries: tuple[AuditHistoryEntry, ...] = ()
        if audit_portal_enabled(repo_root):
            audit_entries = portal_recent_activity(repo_root, limit=80)
        tiles = build_estate_tiles(fleet_repos, audit_entries=audit_entries) if enabled else []
        return templates.TemplateResponse(
            request,
            "estate_map.html",
            page_context(
                request,
                nav_active="estate",
                estate_enabled=enabled,
                estate_tiles=tiles,
                audit_sparklines_enabled=audit_portal_enabled(repo_root),
            ),
        )

    @app.get("/library", response_class=HTMLResponse)
    async def library_page(request: Request, owner: str = "") -> HTMLResponse:
        cost_configured = cost_reader_configured(
            cost_reader=portal_config.cost_reader,
            cost_actuals_url=portal_config.cost_actuals_url,
        )
        entities = build_portal_catalog_entities(
            repo_root,
            resolved_output,
            cost_actuals_configured=cost_configured,
        )
        if owner.strip():
            entities = filter_entities_by_owner(entities, owner)
        entities = list(enrich_catalog_entities_with_cost(entities, portal_config))
        entities = list(enrich_catalog_entities_with_deployment(entities, portal_config))
        blueprint_types = {
            blueprint.name: blueprint.artifact_type
            for blueprint in list_blueprints(blueprints_dir(repo_root))
        }
        library_groups = group_catalog_entities(
            entities,
            blueprint_artifact_types=blueprint_types,
        )
        fleet_rollup = rollup_fleet_scorecard(entities)
        return templates.TemplateResponse(
            request,
            "library.html",
            page_context(
                request,
                nav_active="library",
                library_groups=library_groups,
                library_entity_count=len(entities),
                fleet_scorecard_rollup=fleet_rollup,
                library_owner_filter=owner.strip(),
                observability_configured=bool(portal_config.observability_dashboard_url),
            ),
        )

    @app.get("/services", response_class=RedirectResponse)
    async def services_redirect() -> RedirectResponse:
        return RedirectResponse(url="/library", status_code=302)

    @app.get("/services/{entity_id}", response_class=HTMLResponse)
    async def service_detail_page(request: Request, entity_id: str) -> HTMLResponse:
        cost_configured = cost_reader_configured(
            cost_reader=portal_config.cost_reader,
            cost_actuals_url=portal_config.cost_actuals_url,
        )
        entities = build_portal_catalog_entities(
            repo_root,
            resolved_output,
            cost_actuals_configured=cost_configured,
        )
        entity = find_catalog_entity(entities, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        entity, cost_actuals, cost_estimate = enrich_entity_cost(entity, portal_config)
        entity, deployment_status = deployment_scorecard_for_entity(entity, portal_config)
        token = resolve_github_access_token()
        docs = resolve_entity_docs(entity, github_token=token)
        readme_html = render_portal_markdown(docs["readme"]) if docs.get("readme") else ""
        runbook_html = render_portal_markdown(docs["runbook"]) if docs.get("runbook") else ""
        runbook_label = docs.get("runbook_label", "Runbook")
        upgrade_html = render_portal_markdown(docs["upgrade"]) if docs.get("upgrade") else ""
        upgrade_label = docs.get("upgrade_label", "Upgrade notes")
        provenance_html = ""
        if docs.get("provenance"):
            provenance_html = render_portal_markdown(f"```yaml\n{docs['provenance'].strip()}\n```")
        obs_url = observability_embed_url(portal_config.observability_dashboard_url, entity)
        slo_summary = fetch_entity_slo_summary(portal_config.observability_slo_url, entity)
        live_plan_cfg = load_live_plan_config(repo_root)
        live_plan_env = (
            live_plan_cfg.environment_for(entity.entity_id) if live_plan_cfg is not None else None
        )
        live_plan_available = bool(run_queue is not None and live_plan_env is not None)
        vend_cfg = load_environment_vending_config(repo_root)
        environment_vend_available = bool(run_queue is not None and vend_cfg is not None)
        default_stack_name = _default_environment_stack_name(entity.entity_id, entity.display_name)
        default_vend_path = ""
        if vend_cfg is not None:
            prefix = vend_cfg.path_prefix.strip().strip("/")
            default_vend_path = f"{prefix}/{default_stack_name}" if prefix else default_stack_name
        add_status = str(request.query_params.get("add_status", "")).strip()
        add_message = str(request.query_params.get("add_message", "")).strip()
        component_add = build_component_add_context(
            entity,
            repo_root,
            flash_status=add_status,
            flash_message=add_message,
        )
        return templates.TemplateResponse(
            request,
            "service_detail.html",
            page_context(
                request,
                nav_active="library",
                entity=entity,
                readme_html=readme_html,
                runbook_html=runbook_html,
                runbook_label=runbook_label,
                upgrade_html=upgrade_html,
                upgrade_label=upgrade_label,
                provenance_html=provenance_html,
                observability_url=obs_url,
                slo_summary=slo_summary,
                cost_actuals=cost_actuals,
                cost_estimate=cost_estimate,
                deployment_status=deployment_status,
                live_plan_available=live_plan_available,
                live_plan_env=live_plan_env,
                live_plan_policies_dir=(
                    live_plan_env.policies_dir
                    if live_plan_env is not None
                    else (live_plan_cfg.policies_dir if live_plan_cfg else "")
                ),
                environment_vend_available=environment_vend_available,
                environment_vend_cfg=vend_cfg,
                environment_vend_blueprint=DEFAULT_VEND_BLUEPRINT,
                default_stack_name=default_stack_name,
                default_vend_path=default_vend_path,
                **component_add.to_template_dict(),
            ),
        )

    @app.post("/services/{entity_id}/live-plan")
    async def service_live_plan(request: Request, entity_id: str) -> RedirectResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        acting = user.subject if user else current_acting_user()
        try:
            record = submit_async_run(
                run_queue,
                payload={"kind": "live_plan", "entity_id": entity_id},
                acting_user=acting,
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/runs/{record.run_id}", status_code=303)

    @app.post("/services/{entity_id}/request-environment")
    async def service_request_environment(request: Request, entity_id: str) -> RedirectResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        form = await request.form()
        action = str(form.get("action", "")).strip()
        dry_run = action == "preview"
        stack_name = str(form.get("stack_name", "")).strip()
        description = str(form.get("description", "")).strip()
        cloud_provider = str(form.get("cloud_provider", "aws")).strip() or "aws"
        environment = str(form.get("environment", "dev")).strip() or "dev"
        owner = str(form.get("owner", "")).strip()
        env_class = str(form.get("class", "sandbox")).strip() or "sandbox"
        if not description:
            entities = build_portal_catalog_entities(
                repo_root,
                resolved_output,
                cost_actuals_configured=False,
            )
            entity = find_catalog_entity(entities, entity_id)
            description = (
                f"Environment stack for {entity.display_name}"
                if entity is not None
                else f"Environment stack for {entity_id}"
            )
        acting = user.subject if user else current_acting_user()
        try:
            record = submit_async_run(
                run_queue,
                payload={
                    "kind": "environment_vend",
                    "dry_run": dry_run,
                    "entity_id": entity_id,
                    "owner": owner,
                    "class": env_class,
                    "inputs": {
                        "stack_name": stack_name,
                        "description": description,
                        "cloud_provider": cloud_provider,
                        "environment": environment,
                    },
                },
                acting_user=acting,
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/runs/{record.run_id}", status_code=303)

    @app.post("/services/{entity_id}/add-component")
    async def service_add_component(request: Request, entity_id: str) -> RedirectResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        entities = build_portal_catalog_entities(
            repo_root,
            resolved_output,
            cost_actuals_configured=False,
        )
        entity = find_catalog_entity(entities, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        if entity.local_path is None:
            raise HTTPException(
                status_code=400,
                detail="add component requires a local modules_root checkout for this entity",
            )
        form = await request.form()
        blueprint_name = str(form.get("blueprint", "")).strip()
        action = str(form.get("action", "plan")).strip()
        force = str(form.get("force", "")).strip().lower() in {"1", "true", "on", "yes"}
        if not blueprint_name:
            return RedirectResponse(
                component_add_redirect_url(entity_id, status="error", message="Select a blueprint"),
                status_code=303,
            )
        target = str(entity.local_path)
        try:
            plan = plan_add(
                target,
                repo_root,
                blueprint_name=blueprint_name,
                force=force,
            )
        except NotGovernedError as exc:
            return RedirectResponse(
                component_add_redirect_url(entity_id, status="error", message=str(exc)),
                status_code=303,
            )
        except RepoAddError as exc:
            return RedirectResponse(
                component_add_redirect_url(entity_id, status="error", message=str(exc)),
                status_code=303,
            )

        if action != "apply":
            status = "ok" if plan.ok else "blocked"
            message = plan.summary
            if plan.conflicts:
                message = f"{plan.summary}: {'; '.join(plan.conflicts[:3])}"
            return RedirectResponse(
                component_add_redirect_url(entity_id, status=status, message=message),
                status_code=303,
            )

        if not plan.ok:
            return RedirectResponse(
                component_add_redirect_url(
                    entity_id,
                    status="blocked",
                    message=plan.summary or "Unresolved conflicts",
                ),
                status_code=303,
            )
        if not (entity.local_path / ".git").is_dir():
            return RedirectResponse(
                component_add_redirect_url(
                    entity_id,
                    status="error",
                    message="Apply requires a git repository in the local checkout",
                ),
                status_code=303,
            )

        conventions = load_pull_request_conventions(repo_root)
        git_branch = suggested_add_branch(plan, conventions_prefix=conventions.branch_prefix_add)
        commit_message = add_pull_request_title(plan.blueprint_name, plan.component_id)
        try:
            with tempfile.TemporaryDirectory(prefix="repave-add-portal-") as temp_name:
                result = apply_add(
                    entity.local_path,
                    repo_root,
                    plan,
                    staging_dir=Path(temp_name),
                    git_branch=git_branch,
                    commit_message=commit_message,
                )
        except RepoAddError as exc:
            return RedirectResponse(
                component_add_redirect_url(entity_id, status="error", message=str(exc)),
                status_code=303,
            )
        record_add_from_env(repo_root, result)
        applied_message = (
            f"Added {plan.blueprint_name} on {result.git_branch} ({len(plan.files_added)} files)"
        )
        return RedirectResponse(
            component_add_redirect_url(
                entity_id,
                status="applied",
                message=applied_message,
            ),
            status_code=303,
        )

    @app.get("/catalog/entities", response_class=RedirectResponse)
    async def catalog_entities_redirect() -> RedirectResponse:
        return RedirectResponse(url="/library", status_code=302)

    @app.get("/catalog/entities/{entity_id}", response_class=RedirectResponse)
    async def catalog_entity_redirect(entity_id: str) -> RedirectResponse:
        return RedirectResponse(url=f"/services/{entity_id}", status_code=302)

    @app.get("/blueprints/{blueprint_name}", response_class=HTMLResponse)
    async def blueprint_form(request: Request, blueprint_name: str) -> HTMLResponse:
        extras = build_blueprint_form_extras(
            repo_root=repo_root,
            blueprint_name=blueprint_name,
            modules_root=resolved_output.modules_root,
            output_config=resolved_output,
        )
        return templates.TemplateResponse(
            request,
            "blueprint_form.html",
            page_context(
                request,
                **extras,
                nav_active="catalog",
            ),
        )

    @app.get("/bundles/{bundle_name}", response_class=HTMLResponse)
    async def bundle_form(request: Request, bundle_name: str) -> HTMLResponse:
        bundle_dir = bundles_dir(repo_root) / bundle_name
        bundle = load_bundle(bundle_dir, repo_root=repo_root)
        preview_inputs: dict[str, str] = {
            "service_name": "example-service",
            "description": "Example service for repository preview",
            "owner": "group:platform",
            "organization": "platform",
            "team": "payments",
            "port": "8080",
            "runtime": "python",
            "catalog_lifecycle": "experimental",
        }
        for field in bundle.inputs:
            if field.default not in (None, "") and field.name not in preview_inputs:
                preview_inputs[field.name] = str(field.default)
        previews = bundle_member_previews(
            bundle,
            preview_inputs,
            repo_root=repo_root,
            output_config=resolved_output,
        )
        member_gates: list[str] = []
        for member in bundle.members:
            member_blueprint = load_blueprint(
                blueprint_dir(repo_root, member.blueprint_name),
                repo_root=repo_root,
            )
            member_gates.extend(member_blueprint.gates)
        unique_gates = tuple(dict.fromkeys(member_gates))
        topology_nodes, topology_edges = build_bundle_topology(bundle, previews)
        return templates.TemplateResponse(
            request,
            "bundle_form.html",
            page_context(
                request,
                bundle=bundle,
                member_previews=previews,
                github_org=resolved_output.github_org,
                governance_preflight=build_bundle_preflight(
                    bundle,
                    gate_names=unique_gates,
                    total_gate_runs=len(member_gates),
                ),
                bundle_topology=topology_public(topology_nodes, topology_edges),
                nav_active="catalog",
            ),
        )

    @app.get("/blueprints/{blueprint_name}/ansible-catalog")
    async def ansible_catalog_endpoint(
        blueprint_name: str,
        support_linux: str = "true",
        support_windows: str = "false",
    ) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        supports_catalog = (
            blueprint_supports_role_patterns(blueprint)
            or blueprint_supports_playbook_patterns(blueprint)
            or blueprint_supports_collection_sample_patterns(blueprint)
        )
        if not supports_catalog:
            return {
                "version": "0",
                "role_patterns": [],
                "playbook_patterns": [],
                "collection_sample_patterns": [],
                "defaults": {},
            }
        catalog = load_ansible_catalog(repo_root)
        linux = parse_support_flag(support_linux, default=True)
        windows = parse_support_flag(support_windows, default=False)
        return ansible_catalog_for_api(
            catalog,
            defaults=dict(catalog.defaults),
            support_linux=linux,
            support_windows=windows,
            blueprint_name=blueprint.name,
        )

    @app.get("/blueprints/{blueprint_name}/provider-services/{cloud_provider}/{service}")
    async def provider_service_detail(
        blueprint_name: str, cloud_provider: str, service: str
    ) -> dict[str, list[str]]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        catalog = load_provider_catalog(blueprint.path)
        definition = get_service_definition(catalog, cloud_provider, service)
        if definition is None:
            return {"resources": [], "basic": []}
        return definition

    @app.get("/blueprints/{blueprint_name}/policy-catalog")
    async def policy_catalog(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if not blueprint_supports_policy_customization(
            blueprint
        ) and not blueprint_supports_optional_policy(blueprint):
            return {"version": "0", "profiles": {}, "pack_sources": [], "rules": []}
        catalog = load_policy_catalog(repo_root)
        return catalog_for_api(
            catalog,
            blueprint.artifact_type,
            defaults=policy_input_defaults(blueprint),
        )

    @app.get("/blueprints/{blueprint_name}/observability-catalog")
    async def observability_catalog(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        obs_catalog_api = (
            blueprint_supports_observability_notifications(blueprint)
            or blueprint_supports_dashboard_packs(blueprint)
            or blueprint_supports_monitor_packs(blueprint)
            or blueprint_supports_observability_field_catalog(blueprint)
        )
        if not obs_catalog_api:
            return {
                "version": "0",
                "notification_sources": [],
                "dashboard_packs": [],
                "monitor_packs": [],
                "defaults": {},
            }
        obs_cat, obs_catalog_service_ids = load_merged_observability_catalog(
            repo_root,
            resolved_output.modules_root,
        )
        defaults = observability_input_defaults(blueprint, repo_root)
        backend = defaults.get("backend", "grafana")
        return observability_catalog_for_api(
            obs_cat,
            defaults=defaults,
            backend=backend,
            blueprint_name=blueprint.name,
            catalog_service_ids=obs_catalog_service_ids,
        )

    @app.get("/blueprints/{blueprint_name}/service-inventory")
    async def service_inventory(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if blueprint.artifact_type != "observability":
            return {"services": [], "discovered_count": 0}
        catalog = load_observability_catalog(repo_root)
        return services_inventory_json(
            resolved_output.modules_root,
            catalog,
            merge=True,
        )

    @app.get("/blueprints/{blueprint_name}/module-inventory")
    async def module_inventory(
        blueprint_name: str,
        cloud_provider: str = "",
    ) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if blueprint.artifact_type != "terraform-environment-stack":
            return {"modules": []}
        return inventory_modules_json(
            resolved_output.modules_root,
            github_org=resolved_output.github_org,
            cloud_provider=cloud_provider or None,
        )

    @app.get("/blueprints/{blueprint_name}/module-inventory/{repo_name}/versions")
    async def module_inventory_versions(
        blueprint_name: str,
        repo_name: str,
    ) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if blueprint.artifact_type != "terraform-environment-stack":
            return {"repo_name": repo_name, "versions": []}
        token = resolve_github_access_token()
        return inventory_versions_json(
            resolved_output.modules_root,
            repo_name,
            github_org=resolved_output.github_org,
            github_token=token,
        )

    @app.get("/blueprints/{blueprint_name}/role-inventory")
    async def role_inventory(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if blueprint.artifact_type != "ansible-playbook-project":
            return {"roles": []}
        return inventory_roles_json(
            resolved_output.modules_root,
            github_org=resolved_output.github_org,
        )

    @app.get("/blueprints/{blueprint_name}/role-inventory/{repo_name}/versions")
    async def role_inventory_versions(
        blueprint_name: str,
        repo_name: str,
    ) -> dict[str, object]:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        if blueprint.artifact_type != "ansible-playbook-project":
            return {"repo_name": repo_name, "versions": []}
        token = resolve_github_access_token()
        return inventory_role_versions_json(
            resolved_output.modules_root,
            repo_name,
            github_org=resolved_output.github_org,
            github_token=token,
        )

    @app.post("/generate")
    async def generate(request: Request) -> Response:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        dry_run = _dry_run_from_form(form)
        require_run = dry_run or _plan_preview_from_form(form)
        github_token = None
        if not dry_run:
            github_token = resolve_github_access_token()
        acting = user.subject if user else current_acting_user()
        outcome = run_portal_generate(
            form=form,
            repo_root=repo_root,
            output_config=resolved_output,
            worker_execution_mode=worker_execution_mode,
            run_queue=run_queue,
            acting_user=acting,
            github_token=github_token,
            dry_run=dry_run,
            require_run=require_run,
            gate_toolchain_callout=gate_toolchain_callout,
            generate_from_blueprint_fn=generate_from_blueprint,
            generate_from_bundle_fn=generate_from_bundle,
        )
        if isinstance(outcome, PortalGenerateRedirect):
            return RedirectResponse(outcome.url, status_code=outcome.status_code)
        return templates.TemplateResponse(
            request,
            outcome.template_name,
            page_context(
                request,
                nav_active="catalog",
                **outcome.context,
            ),
        )

    def _user_can_replay_runs(request: Request) -> bool:
        if auth_config is None or not auth_config.service_enabled:
            return True
        user = session_user(request)
        return user is not None and user.role == ROLE_ADMIN

    @app.get("/runs", response_class=HTMLResponse)
    async def runs_index(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        status_raw = request.query_params.get("status", "").strip().lower()
        status_filter: RunStatus | None = None
        if status_raw:
            try:
                status_filter = RunStatus(status_raw)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid status filter: {status_raw}",
                ) from exc
        runs = run_queue.list_runs(status=status_filter, limit=50)
        return templates.TemplateResponse(
            request,
            "runs_index.html",
            page_context(
                request,
                nav_active="runs",
                runs=runs,
                status_filter=status_raw,
                can_replay_runs=_user_can_replay_runs(request),
            ),
        )

    @app.post("/runs/{run_id}/replay")
    async def runs_replay(run_id: str, request: Request) -> RedirectResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        try:
            run_queue.replay(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_console(run_id: str, request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        record = run_queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if is_live_plan_run(record):
            inputs = record.payload.get("inputs", {})
            entity_id = ""
            if isinstance(inputs, dict):
                entity_id = str(inputs.get("entity_id", "")).strip()
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="library",
                    run_id=run_id,
                    run_record=record,
                    live_plan=True,
                    live_plan_entity_id=entity_id,
                ),
            )
        if is_environment_vend_run(record):
            entity_id = str(record.payload.get("entity_id", "")).strip()
            vend_blueprint_name = (
                str(record.payload.get("blueprint", DEFAULT_VEND_BLUEPRINT)).strip()
                or DEFAULT_VEND_BLUEPRINT
            )
            vend_blueprint = load_blueprint(
                blueprint_dir(repo_root, vend_blueprint_name),
                repo_root=repo_root,
            )
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="library",
                    run_id=run_id,
                    run_record=record,
                    environment_vend=True,
                    environment_vend_entity_id=entity_id,
                    gate_names=vend_blueprint.gates,
                ),
            )
        if is_bundle_run(record):
            bundle_name = str(record.payload.get("bundle", "")).strip()
            bundle = load_bundle(bundles_dir(repo_root) / bundle_name, repo_root=repo_root)
            gate_names: list[str] = []
            seen_gates: set[str] = set()
            for member in bundle.members:
                member_blueprint = load_blueprint(
                    blueprint_dir(repo_root, member.blueprint_name),
                    repo_root=repo_root,
                )
                for gate in member_blueprint.gates:
                    if gate not in seen_gates:
                        seen_gates.add(gate)
                        gate_names.append(gate)
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="catalog",
                    run_id=run_id,
                    run_record=record,
                    bundle=bundle,
                    gate_names=gate_names,
                ),
            )
        blueprint = load_blueprint(
            blueprint_dir(repo_root, record.blueprint_name),
            repo_root=repo_root,
        )
        return templates.TemplateResponse(
            request,
            "run_console.html",
            page_context(
                request,
                nav_active="catalog",
                run_id=run_id,
                run_record=record,
                blueprint=blueprint,
                gate_names=blueprint.gates,
            ),
        )

    @app.get("/runs/{run_id}/result", response_class=HTMLResponse)
    async def run_result_view(run_id: str, request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        record = run_queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if record.status != RunStatus.SUCCEEDED:
            raise HTTPException(status_code=400, detail="Run is not complete")
        if is_live_plan_run(record):
            summary = record.result if isinstance(record.result, dict) else {}
            return templates.TemplateResponse(
                request,
                "live_plan_result.html",
                page_context(
                    request,
                    nav_active="library",
                    run_id=run_id,
                    run_record=record,
                    live_plan_summary=summary,
                ),
            )
        if is_environment_vend_run(record):
            summary = record.result if isinstance(record.result, dict) else {}
            entity_id = str(record.payload.get("entity_id", "")).strip()
            if entity_id and not summary.get("entity_id"):
                summary = {**summary, "entity_id": entity_id}
            return templates.TemplateResponse(
                request,
                "environment_vend_result.html",
                page_context(
                    request,
                    nav_active="library",
                    run_id=run_id,
                    run_record=record,
                    environment_vend_summary=summary,
                ),
            )
        if is_bundle_run(record):
            bundle_name = str(record.payload.get("bundle", "")).strip()
            bundle = load_bundle(bundles_dir(repo_root) / bundle_name, repo_root=repo_root)
            bundle_result = bundle_result_from_stored_run(
                record=record,
                repo_root=repo_root,
                output_config=resolved_output,
            )
            if bundle_result is None:
                inputs_raw = record.payload.get("inputs", {})
                if not isinstance(inputs_raw, dict):
                    inputs_raw = {}
                bundle_values = {str(k): str(v) for k, v in inputs_raw.items()}
                require_run = record.dry_run
                github_token = None if record.dry_run else resolve_github_access_token()
                bundle_result = generate_from_bundle(
                    bundle,
                    bundle_values,
                    repo_root=repo_root,
                    output_config=resolved_output,
                    dry_run=record.dry_run,
                    require_run=require_run,
                    github_token=github_token,
                )
            combined = bundle_result.combined_gates()
            previews = bundle_member_previews(
                bundle,
                bundle_result.shared_inputs,
                repo_root=repo_root,
                output_config=resolved_output,
            )
            topology_nodes, topology_edges = build_bundle_topology(bundle, previews)
            return templates.TemplateResponse(
                request,
                "bundle_result.html",
                page_context(
                    request,
                    bundle_result=bundle_result,
                    nav_active="catalog",
                    gate_summary=gate_summary(combined),
                    gates_ok=bundle_result.all_members_passed(),
                    gate_toolchain_callout=gate_toolchain_callout(
                        combined,
                        dry_run=bundle_result.dry_run,
                    ),
                    result_portal=build_bundle_result_portal_context(
                        bundle_result,
                        shared_inputs=bundle_result.shared_inputs,
                    ),
                    bundle_topology=topology_public(topology_nodes, topology_edges),
                ),
            )
        blueprint_name = record.blueprint_name
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        dry_run = record.dry_run
        result = generation_result_from_stored_run(
            record=record,
            repo_root=repo_root,
            output_config=resolved_output,
        )
        if result is None:
            inputs_raw = record.payload.get("inputs", {})
            if not isinstance(inputs_raw, dict):
                inputs_raw = {}
            values = {str(k): str(v) for k, v in inputs_raw.items()}
            require_run = dry_run
            github_token = None if dry_run else resolve_github_access_token()
            result = generate_from_blueprint(
                blueprint,
                values,
                output_config=resolved_output,
                dry_run=dry_run,
                require_run=require_run,
                github_token=github_token,
                repo_root=repo_root,
            )
        return templates.TemplateResponse(
            request,
            "result.html",
            page_context(
                request,
                result=result,
                nav_active="catalog",
                gate_summary=gate_summary(result.gates),
                gates_ok=all_gates_passed(result.gates),
                gate_toolchain_callout=gate_toolchain_callout(
                    result.gates,
                    dry_run=result.dry_run,
                ),
                result_portal=build_result_portal_context(result, repo_root),
            ),
        )

    @app.get("/update", response_class=HTMLResponse)
    async def update_form(request: Request) -> HTMLResponse:
        demo_path = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
        repo_prefill = request.query_params.get("repo_url", "").strip()
        if not repo_prefill:
            repo_prefill = request.query_params.get("target_repo", "").strip()
        return templates.TemplateResponse(
            request,
            "update.html",
            page_context(
                request,
                nav_active="update",
                demo_module_path=str(demo_path.resolve()) if demo_path.is_dir() else "",
                target_repo=repo_prefill,
            ),
        )

    @app.post("/update", response_class=HTMLResponse)
    async def update_plan(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        target_repo_raw = str(form.get("target_repo", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None

        if not target_repo_raw:
            return templates.TemplateResponse(
                request,
                "update.html",
                page_context(
                    request,
                    nav_active="update",
                    error_message="Repository path is required.",
                    target_repo=target_repo_raw,
                    blueprint=blueprint_override or "",
                ),
            )

        target_repo = Path(target_repo_raw).expanduser()
        try:
            plan = plan_upgrade(
                target_repo,
                repo_root,
                blueprint_name=blueprint_override,
            )
        except (FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            return templates.TemplateResponse(
                request,
                "update.html",
                page_context(
                    request,
                    nav_active="update",
                    error_message=str(exc),
                    target_repo=target_repo_raw,
                    blueprint=blueprint_override or "",
                ),
            )

        branch = _suggested_upgrade_branch(plan)
        resolved = str(target_repo.resolve())
        cli_apply = f"repave update --no-dry-run --git-branch {branch} --path {resolved}"
        cli_open_pr = f"{cli_apply} --open-pr"
        return templates.TemplateResponse(
            request,
            "update_result.html",
            page_context(
                request,
                nav_active="update",
                plan=plan,
                target_repo=resolved,
                cli_apply_command=cli_apply,
                cli_open_pr_command=cli_open_pr,
                upgrade_diff_views=diff_view_models_from_files(plan.file_diffs),
            ),
        )

    def import_catalog_json() -> list[dict[str, object]]:
        groups = group_blueprints_by_artifact(list_blueprints(blueprints_dir(repo_root)))
        return [
            {
                "family": group.family,
                "title": group.title,
                "blueprints": [
                    {
                        "name": blueprint.name,
                        "label": f"{blueprint.name} ({blueprint.artifact_type})",
                    }
                    for blueprint in group.blueprints
                ],
            }
            for group in groups
        ]

    def import_form_context(request: Request, **extra: object) -> dict[str, object]:
        groups = group_blueprints_by_artifact(list_blueprints(blueprints_dir(repo_root)))
        return page_context(
            request,
            nav_active="import",
            catalog_groups=groups,
            catalog_json=import_catalog_json(),
            **extra,
        )

    def import_scorecard_rows(plan: ImportPlan) -> list[dict[str, str]]:
        after_by_key = {dim.key: dim for dim in plan.scorecard.after}
        rows: list[dict[str, str]] = []
        for before in plan.scorecard.before:
            after = after_by_key.get(before.key, before)
            rows.append(
                {
                    "label": before.label,
                    "before_level": before.level,
                    "before_detail": before.detail,
                    "after_level": after.level,
                    "after_detail": after.detail,
                }
            )
        return rows

    def import_form_path_overrides(form: Any) -> dict[str, str]:
        import json

        raw_json = str(form.get("path_overrides_json", "")).strip()
        try:
            overrides = parse_path_overrides(json.loads(raw_json)) if raw_json else {}
        except json.JSONDecodeError:
            overrides = {}
        prefix = "override__"
        for key in form:
            name = str(key)
            if not name.startswith(prefix):
                continue
            source = name[len(prefix) :].replace("__", "/")
            text = str(form.get(name, "")).strip()
            if source and text:
                overrides[source] = text
        return overrides

    def import_result_context(request: Request, plan: ImportPlan) -> dict[str, object]:
        branch = suggested_import_branch(plan)
        top = plan.candidates[0] if plan.candidates else None
        cli_plan = f"repave import {plan.target}"
        return page_context(
            request,
            nav_active="import",
            plan=plan,
            suggested_branch=branch,
            scorecard_rows=import_scorecard_rows(plan),
            gate_summary=gate_summary(list(plan.gates)),
            detection_evidence=list(top.evidence[:4]) if top and plan.detected else [],
            detection_confidence=top.percent if top else 0,
            cli_plan_command=cli_plan,
            cli_open_pr_command=(
                f"{cli_plan} --blueprint {plan.blueprint_name} --git-branch {branch} --open-pr"
            ),
        )

    @app.get("/import", response_class=HTMLResponse)
    async def import_form(request: Request) -> HTMLResponse:
        requested_blueprint = str(request.query_params.get("blueprint", "")).strip()
        family = ""
        if requested_blueprint:
            path = blueprint_dir(repo_root, requested_blueprint)
            if path.is_dir():
                family = artifact_family(load_blueprint(path, repo_root=repo_root).artifact_type)
            else:
                requested_blueprint = ""
        return templates.TemplateResponse(
            request,
            "import.html",
            import_form_context(
                request,
                target_repo=str(request.query_params.get("repo", "")).strip(),
                selected_blueprint=requested_blueprint,
                selected_family=family,
            ),
        )

    @app.post("/import", response_class=HTMLResponse)
    async def import_plan_preview(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        target_repo_raw = str(form.get("target_repo", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None
        family = str(form.get("category", "")).strip()

        def form_error(message: str, *, governed: bool = False) -> HTMLResponse:
            return templates.TemplateResponse(
                request,
                "import.html",
                import_form_context(
                    request,
                    error_message="" if governed else message,
                    governed_message=message if governed else "",
                    target_repo=target_repo_raw,
                    selected_blueprint=blueprint_override or "",
                    selected_family=family,
                ),
            )

        if not target_repo_raw:
            return form_error("Repository path or URL is required.")

        try:
            plan = plan_import(
                target_repo_raw,
                repo_root,
                blueprint_name=blueprint_override,
                path_overrides=import_form_path_overrides(form),
                force_clone=str(form.get("force_clone", "")).lower() in {"1", "true", "on", "yes"},
            )
        except AlreadyGovernedError as exc:
            return form_error(str(exc), governed=True)
        except (RepoImportError, FileNotFoundError, OSError, RuntimeError, ValueError) as exc:
            return form_error(str(exc))

        return templates.TemplateResponse(
            request,
            "import_result.html",
            import_result_context(request, plan),
        )

    @app.post("/import/apply", response_class=HTMLResponse)
    async def import_apply(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        target_repo_raw = str(form.get("target_repo", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None
        branch = str(form.get("git_branch", "")).strip()

        token = resolve_github_access_token(None)
        if not token:
            return templates.TemplateResponse(
                request,
                "import.html",
                import_form_context(
                    request,
                    error_message=(
                        "Opening an import pull request requires GITHUB_TOKEN or GitHub App "
                        "credentials on the server."
                    ),
                    target_repo=target_repo_raw,
                    selected_blueprint=blueprint_override or "",
                ),
            )

        try:
            result = import_repository(
                target_repo_raw,
                repo_root,
                github_token=token,
                blueprint_name=blueprint_override,
                path_overrides=import_form_path_overrides(form),
                git_branch=branch,
            )
        except (RepoImportError, GitHubError, OSError, RuntimeError, ValueError) as exc:
            return templates.TemplateResponse(
                request,
                "import.html",
                import_form_context(
                    request,
                    error_message=str(exc),
                    target_repo=target_repo_raw,
                    selected_blueprint=blueprint_override or "",
                ),
            )

        registered = record_import(repo_root, result, acting_user=current_acting_user())
        return templates.TemplateResponse(
            request,
            "import_published.html",
            page_context(
                request,
                nav_active="import",
                result=result,
                registered=registered,
            ),
        )

    @app.get("/import/batch", response_class=HTMLResponse)
    async def import_batch_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "import_batch.html",
            import_form_context(request),
        )

    @app.post("/import/batch", response_class=HTMLResponse)
    async def import_batch_preview(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        targets_raw = str(form.get("targets", "")).strip()
        org = str(form.get("org", "")).strip()
        topic = str(form.get("topic", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None
        targets = [line.strip() for line in targets_raw.splitlines() if line.strip()]

        def batch_error(message: str) -> HTMLResponse:
            return templates.TemplateResponse(
                request,
                "import_batch.html",
                import_form_context(
                    request,
                    error_message=message,
                    targets=targets_raw,
                    org=org,
                    topic=topic,
                    selected_blueprint=blueprint_override or "",
                ),
            )

        if not targets and not org and not topic:
            return batch_error("Paste at least one repository URL or provide an org/topic query.")

        try:
            batch = plan_import_batch(
                targets,
                repo_root,
                blueprint_name=blueprint_override,
                org=org,
                topic=topic,
                git_token=resolve_github_access_token(None),
            )
        except RepoImportError as exc:
            return batch_error(str(exc))

        return templates.TemplateResponse(
            request,
            "import_batch_result.html",
            page_context(
                request,
                nav_active="import",
                batch=batch,
                targets=targets_raw,
                org=org,
                topic=topic,
                selected_blueprint=blueprint_override or "",
            ),
        )

    @app.post("/import/batch/apply", response_class=HTMLResponse)
    async def import_batch_apply(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        targets_raw = str(form.get("targets", "")).strip()
        org = str(form.get("org", "")).strip()
        topic = str(form.get("topic", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None
        targets = [line.strip() for line in targets_raw.splitlines() if line.strip()]

        token = resolve_github_access_token(None)
        if not token:
            return templates.TemplateResponse(
                request,
                "import_batch.html",
                import_form_context(
                    request,
                    error_message=(
                        "Batch import requires GITHUB_TOKEN or GitHub App credentials "
                        "on the server."
                    ),
                    targets=targets_raw,
                    org=org,
                    topic=topic,
                ),
            )

        try:
            batch_result = import_repository_batch(
                targets,
                repo_root,
                github_token=token,
                blueprint_name=blueprint_override,
                org=org,
                topic=topic,
            )
        except RepoImportError as exc:
            return templates.TemplateResponse(
                request,
                "import_batch.html",
                import_form_context(request, error_message=str(exc), targets=targets_raw),
            )

        for item in batch_result.items:
            record_import(repo_root, item, acting_user=current_acting_user())

        return templates.TemplateResponse(
            request,
            "import_batch_published.html",
            page_context(
                request,
                nav_active="import",
                batch_result=batch_result,
            ),
        )

    @app.get("/verify", response_class=HTMLResponse)
    async def verify_form(request: Request) -> HTMLResponse:
        demo_path = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
        return templates.TemplateResponse(
            request,
            "verify.html",
            page_context(
                request,
                nav_active="verify",
                demo_module_path=str(demo_path.resolve()) if demo_path.is_dir() else "",
            ),
        )

    @app.post("/verify", response_class=HTMLResponse)
    async def verify_run(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        target_repo_raw = str(form.get("target_repo", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None
        require_run = str(form.get("require_run", "")).lower() in {"1", "true", "on", "yes"}

        if not target_repo_raw:
            return templates.TemplateResponse(
                request,
                "verify.html",
                page_context(
                    request,
                    nav_active="verify",
                    error_message="Repository path or URL is required.",
                    target_repo=target_repo_raw,
                    blueprint=blueprint_override or "",
                ),
            )

        try:
            outcome = verify_target(
                target_repo_raw,
                repo_root,
                blueprint_name=blueprint_override,
                require_run=require_run,
            )
        except VerifyError as exc:
            return templates.TemplateResponse(
                request,
                "verify.html",
                page_context(
                    request,
                    nav_active="verify",
                    error_message=str(exc),
                    target_repo=target_repo_raw,
                    blueprint=blueprint_override or "",
                ),
            )

        gates = list(outcome.gates)
        return templates.TemplateResponse(
            request,
            "verify_result.html",
            page_context(
                request,
                nav_active="verify",
                verify=outcome,
                target_repo=outcome.target,
                gate_summary=gate_summary(gates),
                gates_ok=outcome.gates_passed,
            ),
        )

    @app.get("/platform/fleet", response_class=HTMLResponse)
    async def platform_fleet_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        page = build_platform_fleet_page(repo_root)
        return templates.TemplateResponse(
            request,
            "fleet.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="fleet",
                fleet_enabled=page.fleet_enabled,
                fleet_repos=page.fleet_repos,
                fleet_gitops_namespace=page.gitops_namespace,
                fleet_operator_status_enabled=page.operator_status_enabled,
                fleet_blueprints=page.blueprints,
            ),
        )

    @app.post("/platform/fleet/register")
    async def platform_fleet_register(request: Request) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        form = await request.form()
        acting = user.email if user else current_acting_user()
        try:
            register_fleet_entry_from_form(
                repo_root,
                repo_url=str(form.get("repo_url", "")),
                blueprint_name=str(form.get("blueprint_name", "")),
                blueprint_version=str(form.get("blueprint_version", "")),
                standard_source="",
                standard_version=str(form.get("standard_version", "")),
                owner=str(form.get("owner", "")),
                local_path=str(form.get("local_path", "")),
                acting_user=acting,
            )
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(url="/platform/fleet", status_code=303)

    @app.post("/platform/fleet/unregister")
    async def platform_fleet_unregister(request: Request) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        form = await request.form()
        repo_url = str(form.get("repo_url", "")).strip()
        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required")
        try:
            removed = unregister_fleet_entry(repo_root, repo_url)
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail=f"{repo_url} is not registered")
        return RedirectResponse(url="/platform/fleet", status_code=303)

    @app.get("/platform/ops", response_class=HTMLResponse)
    async def platform_ops_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        probe_token = resolve_github_access_token() if github_credentials_configured() else None
        session_store = getattr(app.state, "session_store", None)
        ops_page = build_platform_ops_page(
            repo_root,
            run_queue=run_queue,
            modules_root=resolved_output.modules_root,
            runs_db=durability_config.runs_db if durability_config is not None else None,
            shutting_down=bool(getattr(app.state, "shutting_down", False)),
            auth_service_enabled=auth_config is not None and auth_config.service_enabled,
            require_session_secret=(
                durability_config.require_session_secret if durability_config else False
            ),
            github_token_configured=github_credentials_configured(),
            github_probe_token=probe_token,
            sql_session_store_ok=session_store.ping() if session_store is not None else None,
        )
        return templates.TemplateResponse(
            request,
            "platform_ops.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="ops",
                ops_page=ops_page,
            ),
        )

    @app.post("/platform/ops/reclaim")
    async def platform_ops_reclaim(request: Request) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        form = await request.form()
        dry_run = str(form.get("dry_run", "1")).strip().lower() in {"1", "true", "on", "yes"}
        vend_cfg = load_environment_vending_config(repo_root)
        if vend_cfg is None:
            raise HTTPException(status_code=503, detail="environment_vending is not enabled")
        acting = user.email if user else current_acting_user()
        if not dry_run and run_queue is not None:
            record = submit_async_run(
                run_queue,
                payload={"kind": "environment_reclaim", "dry_run": False},
                acting_user=acting,
                repo_root=repo_root,
            )
            return RedirectResponse(url=f"/runs/{record.run_id}", status_code=303)
        github_token = None if dry_run else resolve_github_access_token()
        if not dry_run and not github_token:
            raise HTTPException(
                status_code=503,
                detail="GITHUB_TOKEN is required unless dry_run is true",
            )
        reclaim_expired_environments(
            repo_root=repo_root,
            config=vend_cfg,
            github_token=github_token,
            dry_run=dry_run,
        )
        return RedirectResponse(url="/platform/ops", status_code=303)

    @app.get("/platform/standards", response_class=HTMLResponse)
    async def platform_standards_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        standards_page = build_platform_standards_page(repo_root)
        return templates.TemplateResponse(
            request,
            "platform_standards.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="standards",
                standards_page=standards_page,
            ),
        )

    @app.get("/platform/standards/{blueprint_name}", response_class=HTMLResponse)
    async def platform_standards_detail_page(
        request: Request,
        blueprint_name: str,
    ) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        summary = build_platform_standards_detail(repo_root, blueprint_name)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Blueprint {blueprint_name} not found")
        return templates.TemplateResponse(
            request,
            "platform_standards_detail.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="standards",
                summary=summary,
            ),
        )

    @app.post("/platform/standards/{blueprint_name}/confirm-drift")
    async def platform_standards_confirm_drift(
        request: Request,
        blueprint_name: str,
    ) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        form = await request.form()
        repo_urls = [
            str(value).strip() for value in form.getlist("repo_urls") if str(value).strip()
        ]
        if not repo_urls:
            summary = build_platform_standards_detail(repo_root, blueprint_name)
            if summary is not None:
                repo_urls = [row.repo_url for row in summary.behind_repos]
        if not repo_urls:
            raise HTTPException(
                status_code=400, detail="No repositories selected for drift confirm"
            )
        acting = user.email if user else current_acting_user()
        record = submit_async_run(
            run_queue,
            payload={"kind": "fleet_drift_confirm", "repo_urls": repo_urls},
            acting_user=acting,
        )
        return RedirectResponse(url=f"/runs/{record.run_id}", status_code=303)

    @app.get("/platform/campaigns", response_class=HTMLResponse)
    async def platform_campaigns_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        campaigns_page = build_platform_campaigns_page(repo_root)
        return templates.TemplateResponse(
            request,
            "platform_campaigns.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="campaigns",
                campaigns_page=campaigns_page,
            ),
        )

    @app.get("/platform/adoption", response_class=HTMLResponse)
    async def platform_adoption_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        probe_token = resolve_github_access_token() if github_credentials_configured() else None
        adoption_page = build_platform_adoption_page(
            repo_root,
            github_token=probe_token,
            persist=False,
        )
        return templates.TemplateResponse(
            request,
            "platform_adoption.html",
            page_context(
                request,
                nav_active="platform",
                platform_nav="adoption",
                adoption_page=adoption_page,
            ),
        )

    @app.post("/platform/campaigns/{namespace}/{name}/paused")
    async def platform_campaign_set_paused(
        request: Request,
        namespace: str,
        name: str,
    ) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        campaigns_page = build_platform_campaigns_page(repo_root)
        campaign = find_campaign_in_snapshot(
            campaigns_page.snapshot,
            namespace=namespace,
            name=name,
        )
        if campaign is None:
            raise HTTPException(
                status_code=404, detail=f"Campaign {namespace}/{name} not in snapshot"
            )
        form = await request.form()
        paused = str(form.get("paused", "1")).strip().lower() in {"1", "true", "on", "yes"}
        try:
            patch_upgrade_campaign_paused(
                campaign.name,
                campaign.namespace,
                paused=paused,
            )
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return RedirectResponse(url="/platform/campaigns", status_code=303)

    app.include_router(
        build_ops_router(
            output_config=resolved_output,
            auth_config=auth_config,
            durability_config=durability_config,
            session_store=session_store,
        )
    )
    app.include_router(build_auth_router(auth_config=auth_config))
    app.include_router(
        build_api_v1_router(
            repo_root=repo_root,
            output_config=resolved_output,
            auth_config=auth_config,
        )
    )
    app.include_router(
        build_api_v2_router(
            repo_root=repo_root,
            output_config=resolved_output,
            auth_config=auth_config,
        )
    )
    _mount_state_router(app, repo_root=repo_root, auth_config=auth_config)

    return app


def _mount_state_router(app: FastAPI, *, repo_root: Path, auth_config: AuthConfig | None) -> None:
    """Mount `/api/state/v1` only when a state store is configured (ADR 004).

    Off by default: an unconfigured store leaves the app byte-identical to v2.24.
    A misconfigured one must not take the portal down with it, so failures are logged
    and the routes are simply absent.
    """
    from repave_engine.statestore.settings import load_state_store_config

    log = logging.getLogger(__name__)
    try:
        config = load_state_store_config(repo_root)
    except ValueError as exc:
        log.error("state store configuration is invalid; routes not mounted: %s", exc)
        return
    if config is None:
        return

    from repave_engine.api_state import build_state_router

    try:
        app.include_router(
            build_state_router(
                repo_root=repo_root,
                config=config,
                auth_config=auth_config,
            )
        )
    except (OSError, RuntimeError) as exc:
        log.error("state store unavailable; routes not mounted: %s", exc)
        return
    if config.requires_postgres_warning:
        log.warning(
            "state store is using %s; PostgreSQL 14+ is required for shared deployments",
            config.database.dialect,
        )


def create_app_for_serve() -> FastAPI:
    """Factory entrypoint for `repave serve --reload` (local Docker / dev)."""
    repo_root = Path(os.environ.get("REPAVE_SERVE_REPO_ROOT", ".")).resolve()
    return create_app(repo_root=repo_root, output_config=load_output_config(repo_root))


def _suggested_upgrade_branch(plan: UpgradePlanResult) -> str:
    safe_name = plan.blueprint_name.replace("/", "-")
    safe_version = plan.blueprint_version.replace("/", "-")
    return f"repave/upgrade/{safe_name}-{safe_version}"
