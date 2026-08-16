from __future__ import annotations

import logging
import os
import secrets
import signal
import tempfile
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
from repave_engine.api_deprecation import (
    HTML_PORTAL_DEPRECATION_HEADERS,
    HTML_PORTAL_DISABLED_DETAIL,
    V1_DEPRECATION_HEADERS,
    is_html_portal_path,
)
from repave_engine.api_ops import build_ops_router
from repave_engine.api_v1 import build_api_v1_router
from repave_engine.api_v2 import build_api_v2_router
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
    bundles_dir,
    list_catalog_blueprints,
    load_blueprint,
    policy_kind_label,
)
from repave_engine.bundle import list_bundles, load_bundle
from repave_engine.dashboard_pack import blueprint_supports_dashboard_packs
from repave_engine.developer_lab import is_developer_lab_enabled
from repave_engine.durability_store import load_durability_runtime
from repave_engine.entity_catalog import (
    find_catalog_entity,
    library_family_known,
)
from repave_engine.environment_reclaim import reclaim_expired_environments
from repave_engine.environment_vend import DEFAULT_VEND_BLUEPRINT
from repave_engine.execution_mode import ExecutionMode
from repave_engine.fleet import FleetError
from repave_engine.fleet_operator_actions import patch_upgrade_campaign_paused
from repave_engine.gates import GateResult
from repave_engine.github_auth import resolve_github_access_token
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
from repave_engine.portal_components import (
    component_add_redirect_url,
)
from repave_engine.portal_context import (
    build_portal_catalog_entities,
)
from repave_engine.portal_errors import (
    PORTAL_FORM_POST_PATHS,
    format_portal_error_message,
    portal_back_href,
    portal_login_redirect,
    wants_portal_html_response,
)
from repave_engine.portal_generate import (
    PortalGenerateRedirect,
    console_preview_files_from_record,
    publish_target_for_run,
    run_portal_generate,
)
from repave_engine.portal_generate import (
    dry_run_from_form as _dry_run_from_form,
)
from repave_engine.portal_generate import (
    plan_preview_from_form as _plan_preview_from_form,
)
from repave_engine.portal_platform import (
    build_platform_campaigns_page,
    build_platform_standards_detail,
    find_campaign_in_snapshot,
    platform_admin_visible,
    platform_nav_links,
    register_fleet_entry_from_form,
    require_platform_admin,
    unregister_fleet_entry,
)
from repave_engine.portal_surface_moved import (
    ACTIVITY_MOVED,
    BUNDLE_MOVED,
    BUNDLE_RESULT_MOVED,
    CATALOG_MOVED,
    ESTATE_MOVED,
    HOME_MOVED,
    IMPORT_BATCH_MOVED,
    IMPORT_MOVED,
    LIBRARY_MOVED,
    RESULT_MOVED,
    SERVICES_MOVED,
    TEAMS_MOVED,
    UPGRADE_MOVED,
    VERIFY_MOVED,
    MovedSurface,
    moved_page_context,
    platform_moved,
)
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
    target_blueprints_from_org_scan,
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
    is_environment_reclaim_run,
    is_environment_vend_run,
    is_fleet_drift_confirm_run,
    is_live_plan_run,
    is_org_scan_run,
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
    load_output_config,
    load_portal_config,
    load_service_catalog_config,
    load_tracing_config,
    validate_hosted_service_config,
)
from repave_engine.sql_session_middleware import SqlSessionMiddleware
from repave_engine.tracing import configure_tracing
from repave_engine.workload_profiles import (
    SandboxVendError,
    load_deployment_sets,
    load_workload_profiles,
    resolve_sandbox_vend_payload,
)


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
        service_catalog_config = load_service_catalog_config(repo_root)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    developer_lab_enabled = is_developer_lab_enabled(repo_root)
    sandbox_nav_label = "Developer lab" if developer_lab_enabled else "Sandbox"
    sandbox_href = "/lab" if developer_lab_enabled else "/sandbox"
    sandbox_request_label = "Request developer lab" if developer_lab_enabled else "Request sandbox"
    sandbox_page_title = "Request developer lab" if developer_lab_enabled else "Request a sandbox"
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
    async def deprecation_headers(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        if not portal_config.html and is_html_portal_path(path):
            response: Response = JSONResponse(
                {"detail": HTML_PORTAL_DISABLED_DETAIL},
                status_code=410,
            )
        else:
            response = await call_next(request)
        if path.startswith("/api/v1"):
            for key, value in V1_DEPRECATION_HEADERS.items():
                response.headers[key] = value
        elif is_html_portal_path(path):
            for key, value in HTML_PORTAL_DEPRECATION_HEADERS.items():
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
        admin_visible = platform_admin_visible(auth_config, auth_user)
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
            "portal_logo_url": portal_config.logo_url,
            "portal_accent_color": portal_config.accent_color,
            "presenter_mode": presenter,
            "auth_enabled": auth_config is not None and auth_config.service_enabled,
            "auth_user": auth_user,
            "landing_page": False,
            "platform_admin_visible": admin_visible,
            "platform_nav_links": platform_nav_links() if admin_visible else (),
            "service_catalog_enabled": service_catalog_config is not None,
            "developer_lab_enabled": developer_lab_enabled,
            "sandbox_nav_label": sandbox_nav_label,
            "sandbox_href": sandbox_href,
            "sandbox_request_label": sandbox_request_label,
            "sandbox_page_title": sandbox_page_title,
            "async_generation_enabled": run_queue is not None,
            "async_generation_required": worker_execution_mode and run_queue is not None,
            "worker_execution_mode": worker_execution_mode,
            "command_palette_items": command_palette_items(request),
            **extra,
        }

    def render_moved(request: Request, surface: MovedSurface) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "surface_moved.html",
            page_context(request, **moved_page_context(surface)),
        )

    @app.exception_handler(HTTPException)
    async def portal_http_exception_handler(request: Request, exc: HTTPException) -> Response:
        if not wants_portal_html_response(request):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        if exc.status_code == 401:
            return portal_login_redirect(request)
        message = format_portal_error_message(status_code=exc.status_code, detail=exc.detail)
        return templates.TemplateResponse(
            request,
            "portal_error.html",
            page_context(
                request,
                nav_active="catalog",
                portal_error_message=message,
                portal_error_status=exc.status_code,
                portal_back_href=portal_back_href(request),
            ),
            status_code=exc.status_code,
        )

    def command_palette_items(request: Request | None = None) -> list[dict[str, str]]:
        items: list[dict[str, str]] = [
            {"kind": "nav", "label": "Catalog", "href": "/", "subtitle": "Golden paths home"},
            {
                "kind": "nav",
                "label": "Library",
                "href": "/library",
                "subtitle": "Created repositories",
            },
        ]
        if service_catalog_config is not None:
            items.extend(
                (
                    {
                        "kind": "nav",
                        "label": "My services",
                        "href": "/home",
                        "subtitle": "Services you own",
                    },
                    {
                        "kind": "nav",
                        "label": sandbox_nav_label,
                        "href": sandbox_href,
                        "subtitle": "Request an ephemeral environment",
                    },
                )
            )
        items.extend(
            (
                {
                    "kind": "nav",
                    "label": "Import",
                    "href": "/import",
                    "subtitle": "Adopt an existing repo",
                },
                {
                    "kind": "nav",
                    "label": "Upgrade",
                    "href": "/update",
                    "subtitle": "Plan a standards upgrade",
                },
                {
                    "kind": "nav",
                    "label": "Verify",
                    "href": "/verify",
                    "subtitle": "Run verify against a repo",
                },
                {
                    "kind": "nav",
                    "label": "Repo status",
                    "href": "/estate",
                    "subtitle": "Fleet estate map",
                },
                {
                    "kind": "nav",
                    "label": "Activity",
                    "href": "/activity",
                    "subtitle": "Audit-backed generation history",
                },
                {
                    "kind": "action",
                    "label": "Resume last run",
                    "action": "resume-last-run",
                    "subtitle": "Return to your last blueprint in this browser",
                },
            )
        )
        if run_queue is not None:
            items.insert(
                len(items) - 1,
                {
                    "kind": "nav",
                    "label": "Runs",
                    "href": "/runs",
                    "subtitle": "Async generation jobs and live console",
                },
            )
        auth_user = session_user(request) if request is not None else None
        if platform_admin_visible(auth_config, auth_user):
            items.extend(
                {
                    "kind": "nav",
                    "label": f"Platform {link.label.lower()}",
                    "href": link.href,
                    "subtitle": link.subtitle,
                }
                for link in platform_nav_links()
            )
        for blueprint in list_catalog_blueprints(repo_root):
            items.append(
                {
                    "kind": "blueprint",
                    "label": blueprint.name,
                    "href": f"/blueprints/{blueprint.name}",
                    "subtitle": (
                        f"{blueprint.artifact_type} · v{blueprint.version} · "
                        f"{len(blueprint.gates)} gates"
                    ),
                }
            )
        for bundle in list_bundles(repo_root):
            items.append(
                {
                    "kind": "bundle",
                    "label": bundle.name,
                    "href": f"/bundles/{bundle.name}",
                    "subtitle": f"bundle · v{bundle.version} · {len(bundle.members)} members",
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
            if request.method == "POST" and path in PORTAL_FORM_POST_PATHS:
                if wants_portal_html_response(request):
                    return portal_login_redirect(request)
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
        if (
            auth_config is not None
            and auth_config.service_enabled
            and session_user(request) is None
        ):
            return templates.TemplateResponse(
                request,
                "landing.html",
                page_context(request, nav_active="welcome", landing_page=True),
            )
        return render_moved(request, CATALOG_MOVED)

    @app.get("/signup", response_class=HTMLResponse, response_model=None)
    async def signup_page(request: Request) -> Response:
        if auth_config is None or not auth_config.service_enabled:
            return RedirectResponse("/", status_code=302)
        if session_user(request) is not None:
            return RedirectResponse("/", status_code=302)
        return templates.TemplateResponse(
            request,
            "signup.html",
            page_context(request, nav_active="signup", landing_page=True),
        )

    @app.get("/activity", response_class=HTMLResponse)
    async def activity_page(request: Request) -> HTMLResponse:
        return render_moved(request, ACTIVITY_MOVED)

    @app.get("/fleet", response_class=RedirectResponse)
    async def fleet_redirect() -> RedirectResponse:
        return RedirectResponse(url="/library", status_code=302)

    @app.get("/estate", response_class=HTMLResponse)
    async def estate_map_page(request: Request) -> HTMLResponse:
        return render_moved(request, ESTATE_MOVED)

    @app.get("/library", response_class=HTMLResponse)
    async def library_page(request: Request, owner: str = "") -> HTMLResponse:
        return render_moved(request, LIBRARY_MOVED)

    @app.get("/library/{family}", response_class=HTMLResponse)
    async def library_family_page(request: Request, family: str, owner: str = "") -> HTMLResponse:
        if not library_family_known(family):
            raise HTTPException(status_code=404, detail="Library family not found")
        return render_moved(request, LIBRARY_MOVED)

    @app.get("/services", response_class=RedirectResponse)
    async def services_redirect() -> RedirectResponse:
        return RedirectResponse(url="/library", status_code=302)

    @app.get("/services/{entity_id}", response_class=HTMLResponse)
    async def service_detail_page(request: Request, entity_id: str) -> HTMLResponse:
        return render_moved(request, SERVICES_MOVED)

    @app.get("/home", response_class=HTMLResponse)
    async def developer_home_page(request: Request, owner: str = "") -> HTMLResponse:
        if service_catalog_config is None:
            raise HTTPException(
                status_code=404,
                detail="Service catalog is not enabled (set service_catalog.enabled)",
            )
        return render_moved(request, HOME_MOVED)

    @app.get("/teams/{team_slug}", response_class=HTMLResponse)
    async def team_page(request: Request, team_slug: str) -> HTMLResponse:
        if service_catalog_config is None:
            raise HTTPException(
                status_code=404,
                detail="Service catalog is not enabled (set service_catalog.enabled)",
            )
        return render_moved(request, TEAMS_MOVED)

    @app.get("/sandbox", response_class=HTMLResponse)
    async def sandbox_page(request: Request) -> HTMLResponse:
        return _render_sandbox_page(request)

    @app.get("/lab", response_class=HTMLResponse)
    async def developer_lab_page(request: Request) -> HTMLResponse:
        if not developer_lab_enabled:
            raise HTTPException(status_code=404, detail="Developer lab is not enabled")
        return _render_sandbox_page(request)

    def _render_sandbox_page(request: Request) -> HTMLResponse:
        if service_catalog_config is None:
            raise HTTPException(
                status_code=404,
                detail="Service catalog is not enabled (set service_catalog.enabled)",
            )
        profiles = load_workload_profiles(service_catalog_config.workload_profiles)
        sets = load_deployment_sets(service_catalog_config.deployment_sets)
        vend_cfg = load_environment_vending_config(repo_root)
        auth_user = session_user(request)
        default_owner = (
            auth_user.email
            if auth_user is not None and auth_user.email
            else f"group:{service_catalog_config.default_team}"
        )
        return templates.TemplateResponse(
            request,
            "sandbox.html",
            page_context(
                request,
                nav_active="sandbox",
                workload_profiles=profiles,
                profiles_by_id={profile.id: profile for profile in profiles},
                deployment_sets=sets,
                environment_vend_available=bool(run_queue is not None and vend_cfg is not None),
                environment_vend_cfg=vend_cfg,
                default_sandbox_owner=default_owner,
            ),
        )

    @app.post("/sandbox/request")
    async def sandbox_request(request: Request) -> RedirectResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        if service_catalog_config is None:
            raise HTTPException(
                status_code=404,
                detail="Service catalog is not enabled (set service_catalog.enabled)",
            )
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        form = await request.form()
        set_id = str(form.get("deployment_set", "")).strip()
        stack_name = str(form.get("stack_name", "")).strip()
        owner = str(form.get("owner", "")).strip()
        dry_run = str(form.get("dry_run", "1")).strip().lower() in {
            "1",
            "true",
            "on",
            "yes",
        }
        sets = load_deployment_sets(service_catalog_config.deployment_sets)
        profiles = load_workload_profiles(service_catalog_config.workload_profiles)
        vend_cfg = load_environment_vending_config(repo_root)
        gitops_repo = vend_cfg.gitops_repo if vend_cfg is not None else ""
        try:
            payload = resolve_sandbox_vend_payload(
                sets=sets,
                profiles=profiles,
                deployment_set_id=set_id,
                stack_name=stack_name,
                owner=owner,
                gitops_repo=gitops_repo,
                dry_run=dry_run,
            )
        except SandboxVendError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        acting = user.subject if user else current_acting_user()
        try:
            record = submit_async_run(
                run_queue,
                payload=payload,
                acting_user=acting,
                repo_root=repo_root,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(url=f"/runs/{record.run_id}", status_code=303)

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
    async def blueprint_generate_moved(request: Request, blueprint_name: str) -> HTMLResponse:
        blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
        return templates.TemplateResponse(
            request,
            "generate_moved.html",
            page_context(
                request,
                blueprint=blueprint,
                nav_active="catalog",
            ),
        )

    @app.get("/bundles/{bundle_name}", response_class=HTMLResponse)
    async def bundle_form(request: Request, bundle_name: str) -> HTMLResponse:
        load_bundle(bundles_dir(repo_root) / bundle_name, repo_root=repo_root)
        return render_moved(request, BUNDLE_MOVED)

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
        extra = dict(outcome.context)
        extra.setdefault("nav_active", "catalog")
        return templates.TemplateResponse(
            request,
            outcome.template_name,
            page_context(request, **extra),
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
                    console_preview_files=console_preview_files_from_record(
                        record, repo_root=repo_root
                    ),
                ),
            )
        if is_fleet_drift_confirm_run(record):
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="platform",
                    run_id=run_id,
                    run_record=record,
                    fleet_drift_confirm=True,
                    gate_names=[],
                ),
            )
        if is_org_scan_run(record):
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="import",
                    run_id=run_id,
                    run_record=record,
                    org_scan=True,
                    gate_names=[],
                ),
            )
        if is_environment_reclaim_run(record):
            return templates.TemplateResponse(
                request,
                "run_console.html",
                page_context(
                    request,
                    nav_active="platform",
                    run_id=run_id,
                    run_record=record,
                    environment_reclaim=True,
                    gate_names=[],
                ),
            )
        blueprint = load_blueprint(
            blueprint_dir(repo_root, record.blueprint_name),
            repo_root=repo_root,
        )
        publish_target = publish_target_for_run(
            blueprint=blueprint,
            payload=record.payload,
            output_config=resolved_output,
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
                publish_target=publish_target,
                console_preview_files=console_preview_files_from_record(
                    record, repo_root=repo_root
                ),
            ),
        )

    @app.get("/runs/{run_id}/result", response_class=HTMLResponse)
    async def run_result_view(run_id: str, request: Request) -> Response:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        if run_queue is None:
            raise HTTPException(status_code=503, detail="Async runs are not enabled")
        record = run_queue.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
            # Browse/result links can race ahead of the SUCCEEDED write — send
            # operators back to the live console instead of a dead-end error.
            return RedirectResponse(f"/runs/{run_id}", status_code=303)
        if record.status != RunStatus.SUCCEEDED:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Run ended with status {record.status.value}; open /runs/{run_id} for logs"
                ),
            )
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
        if is_fleet_drift_confirm_run(record):
            summary = record.result if isinstance(record.result, dict) else {}
            return templates.TemplateResponse(
                request,
                "fleet_drift_confirm_result.html",
                page_context(
                    request,
                    nav_active="platform",
                    run_id=run_id,
                    run_record=record,
                    drift_summary=summary,
                ),
            )
        if is_org_scan_run(record):
            summary = record.result if isinstance(record.result, dict) else {}
            return templates.TemplateResponse(
                request,
                "org_scan_result.html",
                page_context(
                    request,
                    nav_active="import",
                    run_id=run_id,
                    run_record=record,
                    org_scan_summary=summary,
                    org_scan_target_blueprints=target_blueprints_from_org_scan(summary),
                ),
            )
        if is_environment_reclaim_run(record):
            summary = record.result if isinstance(record.result, dict) else {}
            return templates.TemplateResponse(
                request,
                "environment_reclaim_result.html",
                page_context(
                    request,
                    nav_active="platform",
                    run_id=run_id,
                    run_record=record,
                    reclaim_summary=summary,
                ),
            )
        if is_bundle_run(record):
            return render_moved(request, BUNDLE_RESULT_MOVED)
        return render_moved(request, RESULT_MOVED)

    @app.get("/update", response_class=HTMLResponse)
    @app.post("/update", response_class=HTMLResponse)
    async def update_moved(request: Request) -> HTMLResponse:
        return render_moved(request, UPGRADE_MOVED)

    @app.get("/import", response_class=HTMLResponse)
    @app.post("/import", response_class=HTMLResponse)
    @app.post("/import/apply", response_class=HTMLResponse)
    async def import_moved(request: Request) -> HTMLResponse:
        return render_moved(request, IMPORT_MOVED)

    @app.get("/import/batch", response_class=HTMLResponse)
    @app.post("/import/batch", response_class=HTMLResponse)
    @app.post("/import/batch/apply", response_class=HTMLResponse)
    async def import_batch_moved(request: Request) -> HTMLResponse:
        return render_moved(request, IMPORT_BATCH_MOVED)

    @app.get("/verify", response_class=HTMLResponse)
    @app.post("/verify", response_class=HTMLResponse)
    async def verify_moved(request: Request) -> HTMLResponse:
        return render_moved(request, VERIFY_MOVED)

    @app.get("/platform/fleet", response_class=HTMLResponse)
    async def platform_fleet_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("fleet"))

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
        return render_moved(request, platform_moved("ops"))

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
        return render_moved(request, platform_moved("standards"))

    @app.get("/platform/standards/{blueprint_name}", response_class=HTMLResponse)
    async def platform_standards_detail_page(
        request: Request,
        blueprint_name: str,
    ) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("standards"))

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
        try:
            record = submit_async_run(
                run_queue,
                payload={"kind": "fleet_drift_confirm", "repo_urls": repo_urls},
                acting_user=acting,
            )
        except RunQueueFullError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except RunQueueShuttingDownError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return RedirectResponse(url=f"/runs/{record.run_id}", status_code=303)

    @app.get("/platform/campaigns", response_class=HTMLResponse)
    async def platform_campaigns_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("campaigns"))

    @app.get("/platform/finops", response_class=HTMLResponse)
    async def platform_finops_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("finops"))

    @app.get("/platform/adoption", response_class=HTMLResponse)
    async def platform_adoption_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("adoption"))

    @app.get("/platform/compliance", response_class=HTMLResponse)
    async def platform_compliance_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("compliance"))

    @app.get("/platform/value-stream", response_class=HTMLResponse)
    async def platform_value_stream_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("value-stream"))

    @app.get("/platform/roadmap", response_class=HTMLResponse)
    async def platform_roadmap_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("roadmap"))

    @app.get("/platform/feedback", response_class=HTMLResponse)
    async def platform_feedback_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("feedback"))

    @app.get("/platform/maturity", response_class=HTMLResponse)
    async def platform_maturity_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("maturity"))

    @app.get("/platform/initiatives", response_class=HTMLResponse)
    async def platform_initiatives_page(request: Request) -> HTMLResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        return render_moved(request, platform_moved("initiatives"))

    def _initiatives_store_path() -> Path:
        if service_catalog_config is None or service_catalog_config.initiatives is None:
            raise HTTPException(
                status_code=404,
                detail="Initiatives store is not configured (service_catalog.initiatives)",
            )
        return service_catalog_config.initiatives

    @app.post("/platform/initiatives")
    async def platform_initiatives_create(request: Request) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        store_path = _initiatives_store_path()
        form = await request.form()
        from repave_engine.initiatives import append_initiative, build_initiative_from_form

        try:
            initiative = build_initiative_from_form({key: str(form.get(key, "")) for key in form})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        append_initiative(store_path, initiative)
        return RedirectResponse(url="/platform/initiatives", status_code=303)

    @app.post("/platform/initiatives/{initiative_id}")
    async def platform_initiatives_update(
        request: Request,
        initiative_id: str,
    ) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        store_path = _initiatives_store_path()
        form = await request.form()
        from repave_engine.initiatives import (
            apply_initiative_patch,
            get_initiative,
            upsert_initiative,
        )

        existing = get_initiative(store_path, initiative_id)
        if existing is None:
            raise HTTPException(status_code=404, detail=f"initiative not found: {initiative_id}")
        try:
            updated = apply_initiative_patch(
                existing,
                {key: str(form.get(key, "")) for key in form},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        upsert_initiative(store_path, updated)
        return RedirectResponse(url="/platform/initiatives", status_code=303)

    @app.post("/platform/initiatives/{initiative_id}/deactivate")
    async def platform_initiatives_deactivate(
        request: Request,
        initiative_id: str,
    ) -> RedirectResponse:
        user = session_user(request)
        require_platform_admin(user, auth_config)
        store_path = _initiatives_store_path()
        from repave_engine.initiatives import deactivate_initiative

        try:
            deactivate_initiative(store_path, initiative_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return RedirectResponse(url="/platform/initiatives", status_code=303)

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
