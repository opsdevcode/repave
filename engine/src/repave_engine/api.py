from __future__ import annotations

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
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
from repave_engine.audit_history import AuditHistoryEntry, read_recent_audit_entries
from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    build_login_redirect,
    clear_session,
    complete_oidc_callback,
    fetch_oidc_discovery,
    is_public_path,
    require_role,
    session_user,
)
from repave_engine.auth_context import current_acting_user, reset_acting_user, set_acting_user
from repave_engine.blueprint import (
    artifact_family,
    group_blueprints_by_artifact,
    list_blueprints,
    load_blueprint,
    policy_kind_label,
)
from repave_engine.dashboard_pack import blueprint_supports_dashboard_packs
from repave_engine.fleet import (
    FleetEntry,
    FleetError,
    normalize_repo_url,
    pins_from_repave_file,
    read_fleet,
    register_repo,
    unregister_repo,
)
from repave_engine.gates import GateResult, all_gates_passed
from repave_engine.generate_api import run_generate_api
from repave_engine.module_inventory import inventory_modules_json, inventory_versions_json
from repave_engine.monitor_pack import blueprint_supports_monitor_packs
from repave_engine.observability_catalog import catalog_for_api as observability_catalog_for_api
from repave_engine.observability_catalog import (
    catalog_has_field_options,
    load_observability_catalog,
)
from repave_engine.observability_selection import (
    blueprint_supports_observability_field_catalog,
    blueprint_supports_observability_notifications,
    observability_input_defaults,
)
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.policy_catalog import (
    catalog_for_api,
    enabled_rule_ids_for_profile,
    load_policy_catalog,
)
from repave_engine.policy_selection import (
    blueprint_supports_optional_policy,
    blueprint_supports_policy_customization,
    policy_input_defaults,
)
from repave_engine.portal_result import build_result_portal_context
from repave_engine.provider_catalog import get_service_definition, load_provider_catalog
from repave_engine.service_inventory import (
    load_merged_observability_catalog,
    services_inventory_json,
)
from repave_engine.settings import (
    OutputConfig,
    load_audit_config,
    load_auth_config,
    load_fleet_config,
    load_output_config,
    load_portal_config,
)
from repave_engine.standards_diff import standards_diff_for_pin
from repave_engine.upgrade_plan import UpgradePlanResult, plan_upgrade
from repave_engine.verify import VerifyError, verify_target


def _dry_run_from_form(form: object) -> bool:
    """Parse dry_run from multipart form; last value wins when multiple are sent."""
    getlist = getattr(form, "getlist", None)
    if getlist is None:
        get = getattr(form, "get", lambda _k, _d=None: "true")
        return str(get("dry_run", "true")).lower() != "false"
    raw = [str(item).lower() for item in getlist("dry_run") if str(item).strip()]
    if not raw:
        return True
    return raw[-1] != "false"


def _plan_preview_from_form(form: object) -> bool:
    get = getattr(form, "get", lambda _k, _d=None: "")
    return str(get("plan_preview", "")).strip() in ("1", "true", "yes")


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

    app = FastAPI(title="repave", version=__version__)
    session_secret = os.environ.get("REPAVE_SESSION_SECRET", "").strip()
    if auth_config is not None and auth_config.service_enabled:
        session_secret = auth_config.session_secret
    elif not session_secret:
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
            **extra,
        }

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
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        same_site="lax",
        https_only=False,
    )

    def portal_recent_activity(*, limit: int = 8) -> tuple[AuditHistoryEntry, ...]:
        try:
            audit_cfg = load_audit_config(repo_root)
        except ValueError:
            return ()
        if audit_cfg is None or not audit_cfg.enabled:
            return ()
        return read_recent_audit_entries(audit_cfg.file, limit=limit)

    def audit_portal_enabled() -> bool:
        try:
            audit_cfg = load_audit_config(repo_root)
        except ValueError:
            return False
        return audit_cfg is not None and audit_cfg.enabled

    def gate_summary(gates: list[GateResult]) -> dict[str, int | str]:
        passed = sum(1 for gate in gates if gate.passed and not gate.skipped)
        failed = sum(1 for gate in gates if not gate.passed and not gate.skipped)
        skipped = sum(1 for gate in gates if gate.skipped)
        if failed:
            outcome = "failed"
        elif gates and all(gate.passed or gate.skipped for gate in gates):
            outcome = "passed"
        else:
            outcome = "empty"
        return {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "outcome": outcome,
        }

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
        blueprints = list_blueprints(repo_root / "blueprints")
        catalog_groups = group_blueprints_by_artifact(blueprints)
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(
                request,
                blueprints=blueprints,
                catalog_groups=catalog_groups,
                nav_active="catalog",
                recent_activity=portal_recent_activity(),
            ),
        )

    @app.get("/activity", response_class=HTMLResponse)
    async def activity_page(request: Request) -> HTMLResponse:
        activity_limit = 50
        return templates.TemplateResponse(
            request,
            "activity.html",
            page_context(
                request,
                nav_active="activity",
                recent_activity=portal_recent_activity(limit=activity_limit),
                audit_enabled=audit_portal_enabled(),
                activity_limit=activity_limit,
            ),
        )

    @app.get("/fleet", response_class=HTMLResponse)
    async def fleet_page(request: Request) -> HTMLResponse:
        try:
            fleet_cfg = load_fleet_config(repo_root)
        except ValueError:
            fleet_cfg = None
        enabled = fleet_cfg is not None and fleet_cfg.enabled
        entries = read_fleet(fleet_cfg.file) if enabled and fleet_cfg else ()
        return templates.TemplateResponse(
            request,
            "fleet.html",
            page_context(
                request,
                nav_active="fleet",
                fleet_enabled=enabled,
                fleet_repos=[entry.to_dict() for entry in entries],
            ),
        )

    @app.get("/blueprints/{blueprint_name}", response_class=HTMLResponse)
    async def blueprint_form(request: Request, blueprint_name: str) -> HTMLResponse:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        policy_catalog: dict[str, object] | None = None
        policy_defaults: dict[str, str] = {}
        policy_enabled_rule_ids: set[str] = set()
        if blueprint_supports_policy_customization(blueprint) or blueprint_supports_optional_policy(
            blueprint
        ):
            policy_defaults = policy_input_defaults(blueprint)
            catalog = load_policy_catalog(repo_root)
            policy_catalog = catalog_for_api(
                catalog,
                blueprint.artifact_type,
                defaults=policy_defaults,
            )
            profile = policy_defaults.get("policy_profile", "estate-default")
            policy_enabled_rule_ids = enabled_rule_ids_for_profile(
                catalog,
                profile=profile,
                artifact_type=blueprint.artifact_type,
            )
        observability_catalog: dict[str, object] | None = None
        observability_defaults: dict[str, str] = {}
        observability_field_catalog = False
        obs_catalog_form = (
            blueprint_supports_observability_notifications(blueprint)
            or blueprint_supports_dashboard_packs(blueprint)
            or blueprint_supports_observability_field_catalog(blueprint)
        )
        if obs_catalog_form:
            observability_defaults = observability_input_defaults(blueprint, repo_root)
            for field in blueprint.inputs:
                if field.name == "backend" and field.default not in (None, ""):
                    observability_defaults.setdefault("backend", str(field.default))
            obs_cat, obs_catalog_service_ids = load_merged_observability_catalog(
                repo_root,
                resolved_output.modules_root,
            )
            observability_field_catalog = blueprint_supports_observability_field_catalog(
                blueprint
            ) and catalog_has_field_options(obs_cat)
            observability_catalog = observability_catalog_for_api(
                obs_cat,
                defaults=observability_defaults,
                backend=observability_defaults.get("backend", "grafana"),
                blueprint_name=blueprint.name,
                catalog_service_ids=obs_catalog_service_ids,
            )
        ansible_catalog: dict[str, object] | None = None
        ansible_role_patterns = blueprint_supports_role_patterns(blueprint)
        ansible_playbook_patterns = blueprint_supports_playbook_patterns(blueprint)
        ansible_collection_sample_patterns = blueprint_supports_collection_sample_patterns(
            blueprint
        )
        if ansible_role_patterns or ansible_playbook_patterns or ansible_collection_sample_patterns:
            ansible_cat = load_ansible_catalog(repo_root)
            ansible_catalog = ansible_catalog_for_api(
                ansible_cat,
                defaults=dict(ansible_cat.defaults),
                support_linux=True,
                support_windows=False,
                blueprint_name=blueprint.name,
            )
        provider_catalog = load_provider_catalog(blueprint.path)
        # Golden-path forms use a single scrollable page (no Back/Next stepper).
        form_stepper = None
        return templates.TemplateResponse(
            request,
            "blueprint_form.html",
            page_context(
                request,
                blueprint=blueprint,
                provider_catalog=provider_catalog,
                form_stepper=form_stepper,
                standards_diff=standards_diff_for_pin(
                    repo_root,
                    standard_source=blueprint.standard_source,
                    pinned_version=blueprint.standard_version,
                ),
                recent_activity=portal_recent_activity(),
                policy_customization=blueprint_supports_policy_customization(blueprint),
                policy_customization_optional=blueprint_supports_optional_policy(blueprint),
                policy_defaults=policy_defaults,
                policy_catalog=policy_catalog,
                policy_enabled_rule_ids=policy_enabled_rule_ids,
                observability_notifications=blueprint_supports_observability_notifications(
                    blueprint
                ),
                observability_dashboard_packs=blueprint_supports_dashboard_packs(blueprint),
                observability_monitor_packs=blueprint_supports_monitor_packs(blueprint),
                observability_field_catalog=observability_field_catalog,
                observability_defaults=observability_defaults,
                observability_catalog=observability_catalog,
                ansible_role_patterns=ansible_role_patterns,
                ansible_playbook_patterns=ansible_playbook_patterns,
                ansible_collection_sample_patterns=ansible_collection_sample_patterns,
                ansible_catalog=ansible_catalog,
                nav_active="catalog",
            ),
        )

    @app.get("/blueprints/{blueprint_name}/ansible-catalog")
    async def ansible_catalog_endpoint(
        blueprint_name: str,
        support_linux: str = "true",
        support_windows: str = "false",
    ) -> dict[str, object]:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        catalog = load_provider_catalog(blueprint.path)
        definition = get_service_definition(catalog, cloud_provider, service)
        if definition is None:
            return {"resources": [], "basic": []}
        return definition

    @app.get("/blueprints/{blueprint_name}/policy-catalog")
    async def policy_catalog(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        if blueprint.artifact_type != "terraform-environment-stack":
            return {"repo_name": repo_name, "versions": []}
        token = os.environ.get("GITHUB_TOKEN")
        return inventory_versions_json(
            resolved_output.modules_root,
            repo_name,
            github_org=resolved_output.github_org,
            github_token=token,
        )

    @app.get("/blueprints/{blueprint_name}/role-inventory")
    async def role_inventory(blueprint_name: str) -> dict[str, object]:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
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
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        if blueprint.artifact_type != "ansible-playbook-project":
            return {"repo_name": repo_name, "versions": []}
        token = os.environ.get("GITHUB_TOKEN")
        return inventory_role_versions_json(
            resolved_output.modules_root,
            repo_name,
            github_org=resolved_output.github_org,
            github_token=token,
        )

    @app.post("/generate")
    async def generate(request: Request) -> HTMLResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        form = await request.form()
        blueprint_name = str(form.get("blueprint_name", ""))
        dry_run = _dry_run_from_form(form)
        require_run = dry_run or _plan_preview_from_form(form)
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        values: dict[str, str] = {}
        for field in blueprint.inputs:
            if field.name == "provider_services":
                selected = [
                    str(item) for item in form.getlist("provider_services") if str(item).strip()
                ]
                if not selected:
                    selected = [
                        str(item)
                        for item in form.getlist("provider_service_option")
                        if str(item).strip()
                    ]
                values[field.name] = ",".join(selected)
                continue

            if field.name == "provider_service_scope":
                values[field.name] = str(form.get(field.name, ""))
                continue

            if field.enum and field.multi:
                selected = [str(item) for item in form.getlist(field.name) if str(item).strip()]
                values[field.name] = ",".join(selected)
                continue

            values[field.name] = str(form.get(field.name, ""))

        github_token = None
        if not dry_run:
            github_token = os.environ.get("GITHUB_TOKEN")

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

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/readyz")
    async def readyz() -> dict[str, object]:
        token_ok = bool(os.environ.get("GITHUB_TOKEN", "").strip())
        payload: dict[str, object] = {
            "status": "ready",
            "config_loaded": True,
            "github_token_configured": token_ok,
        }
        if os.environ.get("REPAVE_ENV") == "local":
            from repave_engine.gate_toolchain import gate_tool_status, portal_runtime_info

            payload["gate_tools"] = gate_tool_status()
            payload["runtime"] = portal_runtime_info()
        return payload

    @app.get("/auth/login")
    async def auth_login(request: Request) -> RedirectResponse:
        if auth_config is None or not auth_config.service_enabled:
            return RedirectResponse("/", status_code=302)
        discovery = await fetch_oidc_discovery(auth_config.oidc_issuer)
        return build_login_redirect(request, auth_config, discovery)

    @app.get("/auth/callback")
    async def auth_callback(
        request: Request,
        code: str = "",
        state: str = "",
    ) -> RedirectResponse:
        if auth_config is None or not auth_config.service_enabled:
            raise HTTPException(status_code=404, detail="Auth not enabled")
        if not code or not state:
            raise HTTPException(status_code=400, detail="Missing code or state")
        return await complete_oidc_callback(request, auth_config, code=code, state=state)

    @app.post("/auth/logout")
    async def auth_logout(request: Request) -> RedirectResponse:
        return clear_session(request)

    @app.post("/api/v1/generate")
    async def api_generate(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_GENERATOR, ROLE_ADMIN)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")
        blueprint_name = str(payload.get("blueprint", "")).strip()
        if not blueprint_name:
            raise HTTPException(status_code=400, detail="blueprint is required")
        dry_run = bool(payload.get("dry_run", True))
        inputs_raw = payload.get("inputs", {})
        if not isinstance(inputs_raw, dict):
            raise HTTPException(status_code=400, detail="inputs must be an object")
        github_token = None if dry_run else os.environ.get("GITHUB_TOKEN")
        try:
            body = run_generate_api(
                repo_root=repo_root,
                output_config=resolved_output,
                blueprint_name=blueprint_name,
                inputs=inputs_raw,
                dry_run=dry_run,
                github_token=github_token,
            )
        except (ValueError, FileNotFoundError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse(body)

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

    @app.post("/api/v1/verify")
    async def api_verify(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="JSON body required") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="JSON object required")

        path_raw = str(body.get("path") or body.get("repo_url") or "").strip()
        if not path_raw:
            raise HTTPException(status_code=400, detail="path or repo_url is required")

        blueprint_override = str(body.get("blueprint", "")).strip() or None
        require_run = bool(body.get("require_run", False))
        ref = str(body.get("ref", "")).strip() or None
        try:
            outcome = verify_target(
                path_raw,
                repo_root,
                blueprint_name=blueprint_override,
                require_run=require_run,
                ref=ref,
            )
        except VerifyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        payload = outcome.to_json_dict()
        status = 200 if outcome.ok else 422
        return JSONResponse(payload, status_code=status)

    def fleet_registry_path() -> Path:
        try:
            fleet_cfg = load_fleet_config(repo_root)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if fleet_cfg is None or not fleet_cfg.enabled:
            raise HTTPException(
                status_code=404,
                detail="Fleet registry is not configured (set fleet.file or REPAVE_FLEET_FILE)",
            )
        return fleet_cfg.file

    @app.get("/api/v1/fleet")
    async def api_fleet_list(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        entries = read_fleet(fleet_registry_path())
        return JSONResponse(
            {"count": len(entries), "repos": [entry.to_dict() for entry in entries]}
        )

    @app.post("/api/v1/fleet")
    async def api_fleet_register(request: Request) -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_ADMIN)
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Expected JSON object")

        repo_url = str(payload.get("repo_url", "")).strip()
        if not repo_url:
            raise HTTPException(status_code=400, detail="repo_url is required")

        pins = {
            "blueprint_name": str(payload.get("blueprint_name", "")).strip(),
            "blueprint_version": str(payload.get("blueprint_version", "")).strip(),
            "standard_source": str(payload.get("standard_source", "")).strip(),
            "standard_version": str(payload.get("standard_version", "")).strip(),
        }
        local_path = str(payload.get("path", "")).strip()
        try:
            if local_path:
                pins.update(pins_from_repave_file(Path(local_path).expanduser().resolve()))
            if not pins["blueprint_name"]:
                raise FleetError("blueprint_name is required when path is not supplied")
            entry = register_repo(
                fleet_registry_path(),
                FleetEntry(
                    repo_url=repo_url,
                    blueprint_name=pins["blueprint_name"],
                    blueprint_version=pins["blueprint_version"],
                    standard_source=pins["standard_source"],
                    standard_version=pins["standard_version"],
                    owner=str(payload.get("owner", "")).strip(),
                    registered_by=current_acting_user(),
                ),
            )
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return JSONResponse({"registered": entry.to_dict()}, status_code=201)

    @app.delete("/api/v1/fleet")
    async def api_fleet_unregister(request: Request, repo_url: str = "") -> JSONResponse:
        user = session_user(request)
        if auth_config and auth_config.service_enabled:
            require_role(user, ROLE_ADMIN)
        if not repo_url.strip():
            raise HTTPException(status_code=400, detail="repo_url query parameter is required")
        try:
            removed = unregister_repo(fleet_registry_path(), repo_url)
        except FleetError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if not removed:
            raise HTTPException(status_code=404, detail=f"{repo_url} is not registered")
        return JSONResponse({"unregistered": normalize_repo_url(repo_url)})

    return app


def create_app_for_serve() -> FastAPI:
    """Factory entrypoint for `repave serve --reload` (local Docker / dev)."""
    repo_root = Path(os.environ.get("REPAVE_SERVE_REPO_ROOT", ".")).resolve()
    return create_app(repo_root=repo_root, output_config=load_output_config(repo_root))


def _suggested_upgrade_branch(plan: UpgradePlanResult) -> str:
    safe_name = plan.blueprint_name.replace("/", "-")
    safe_version = plan.blueprint_version.replace("/", "-")
    return f"repave/upgrade/{safe_name}-{safe_version}"
