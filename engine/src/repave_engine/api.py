from __future__ import annotations

import logging
import os
import secrets
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

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
    bundle_member_previews,
)
from repave_engine.bundle_topology import build_bundle_topology, topology_public
from repave_engine.dashboard_pack import blueprint_supports_dashboard_packs
from repave_engine.durability_store import load_durability_runtime
from repave_engine.entity_catalog import (
    find_catalog_entity,
    observability_embed_url,
    read_entity_docs,
)
from repave_engine.estate_map import build_estate_tiles
from repave_engine.execution_mode import ExecutionMode
from repave_engine.fleet import FleetEntry, read_fleet
from repave_engine.fleet_operator_status import FleetOperatorStatus, load_operator_status_file
from repave_engine.fleet_view import build_fleet_rows
from repave_engine.gates import GateResult, all_gates_passed, gate_summary
from repave_engine.generate_api import generation_result_from_stored_run
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.governance_preflight import build_bundle_preflight
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
from repave_engine.portal_context import (
    audit_file_or_http404,
    audit_portal_enabled,
    build_portal_catalog_entities,
    portal_fleet_context,
    portal_recent_activity,
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
from repave_engine.portal_result import build_result_portal_context
from repave_engine.provider_catalog import get_service_definition, load_provider_catalog
from repave_engine.run_queue import (
    RunQueue,
    RunQueueConfig,
    build_run_queue,
)
from repave_engine.run_store import RunStatus
from repave_engine.service_inventory import (
    load_merged_observability_catalog,
    services_inventory_json,
)
from repave_engine.session_store import load_session_store
from repave_engine.settings import (
    OutputConfig,
    load_auth_config,
    load_durability_config,
    load_fleet_config,
    load_output_config,
    load_portal_config,
    load_tracing_config,
)
from repave_engine.sql_session_middleware import SqlSessionMiddleware
from repave_engine.tracing import configure_tracing
from repave_engine.upgrade_plan import UpgradePlanResult, plan_upgrade
from repave_engine.verify import VerifyError, verify_target


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
        return {
            "app_version": __version__,
            "env_badge": os.environ.get("REPAVE_ENV"),
            "local_toolchain_warning": local_portal_toolchain_warning(),
            "portal_runtime": portal_runtime_info(),
            "portal_density": portal_config.density,
            "auth_enabled": auth_config is not None and auth_config.service_enabled,
            "auth_user": auth_user,
            "async_generation_enabled": run_queue is not None,
            "async_generation_required": worker_execution_mode and run_queue is not None,
            "worker_execution_mode": worker_execution_mode,
            "command_palette_items": command_palette_items(),
            **extra,
        }

    def command_palette_items() -> list[dict[str, str]]:
        items: list[dict[str, str]] = [
            {"kind": "nav", "label": "Catalog", "href": "/"},
            {"kind": "nav", "label": "Upgrade repo", "href": "/update"},
            {"kind": "nav", "label": "Verify repo", "href": "/verify"},
            {"kind": "nav", "label": "Fleet", "href": "/fleet"},
            {"kind": "nav", "label": "Services", "href": "/services"},
            {"kind": "nav", "label": "Estate map", "href": "/estate"},
            {"kind": "nav", "label": "Activity", "href": "/activity"},
            {"kind": "action", "label": "Resume last run", "action": "resume-last-run"},
        ]
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
        user = session_user(request)
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
    if session_store is not None:
        app.add_middleware(
            SqlSessionMiddleware,
            secret_key=session_secret,
            session_store=session_store,
            same_site="lax",
            https_only=False,
        )
    else:
        app.add_middleware(
            SessionMiddleware,
            secret_key=session_secret,
            same_site="lax",
            https_only=False,
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

    @app.get("/fleet", response_class=HTMLResponse)
    async def fleet_page(request: Request) -> HTMLResponse:
        try:
            fleet_cfg = load_fleet_config(repo_root)
        except ValueError:
            fleet_cfg = None
        enabled = fleet_cfg is not None and fleet_cfg.enabled
        entries: tuple[FleetEntry, ...] = ()
        operator_by: dict[str, FleetOperatorStatus] = {}
        gitops_namespace = "default"
        if enabled and fleet_cfg is not None:
            entries = read_fleet(fleet_cfg.file, repo_root=repo_root)
            gitops_namespace = fleet_cfg.gitops_namespace
            if fleet_cfg.operator_status_file is not None:
                operator_by = load_operator_status_file(fleet_cfg.operator_status_file)
        fleet_repos = build_fleet_rows(
            entries,
            operator_by_url=operator_by,
            namespace=gitops_namespace,
        )
        return templates.TemplateResponse(
            request,
            "fleet.html",
            page_context(
                request,
                nav_active="fleet",
                fleet_enabled=enabled,
                fleet_repos=fleet_repos,
                fleet_operator_status_enabled=bool(operator_by),
                fleet_gitops_namespace=gitops_namespace,
            ),
        )

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

    @app.get("/services", response_class=HTMLResponse)
    async def services_page(request: Request) -> HTMLResponse:
        entities = build_portal_catalog_entities(repo_root, resolved_output)
        return templates.TemplateResponse(
            request,
            "services.html",
            page_context(
                request,
                nav_active="services",
                catalog_entities=entities,
                observability_configured=bool(portal_config.observability_dashboard_url),
            ),
        )

    @app.get("/services/{entity_id}", response_class=HTMLResponse)
    async def service_detail_page(request: Request, entity_id: str) -> HTMLResponse:
        entities = build_portal_catalog_entities(repo_root, resolved_output)
        entity = find_catalog_entity(entities, entity_id)
        if entity is None:
            raise HTTPException(status_code=404, detail="Entity not found")
        docs: dict[str, str] = {}
        readme_html = ""
        runbook_html = ""
        runbook_label = ""
        if entity.local_path is not None:
            docs = read_entity_docs(entity.local_path)
            if docs.get("readme"):
                readme_html = render_portal_markdown(docs["readme"])
            if docs.get("runbook"):
                runbook_html = render_portal_markdown(docs["runbook"])
                runbook_label = docs.get("runbook_label", "Runbook")
        elif entity.readme_preview:
            readme_html = render_portal_markdown(entity.readme_preview)
        obs_url = observability_embed_url(portal_config.observability_dashboard_url, entity)
        return templates.TemplateResponse(
            request,
            "service_detail.html",
            page_context(
                request,
                nav_active="services",
                entity=entity,
                readme_html=readme_html,
                runbook_html=runbook_html,
                runbook_label=runbook_label,
                observability_url=obs_url,
            ),
        )

    @app.get("/catalog/entities", response_class=RedirectResponse)
    async def catalog_entities_redirect() -> RedirectResponse:
        return RedirectResponse(url="/services", status_code=302)

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
        return templates.TemplateResponse(
            request,
            "update.html",
            page_context(
                request,
                nav_active="update",
                demo_module_path=str(demo_path.resolve()) if demo_path.is_dir() else "",
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

    return app


def create_app_for_serve() -> FastAPI:
    """Factory entrypoint for `repave serve --reload` (local Docker / dev)."""
    repo_root = Path(os.environ.get("REPAVE_SERVE_REPO_ROOT", ".")).resolve()
    return create_app(repo_root=repo_root, output_config=load_output_config(repo_root))


def _suggested_upgrade_branch(plan: UpgradePlanResult) -> str:
    safe_name = plan.blueprint_name.replace("/", "-")
    safe_version = plan.blueprint_version.replace("/", "-")
    return f"repave/upgrade/{safe_name}-{safe_version}"
