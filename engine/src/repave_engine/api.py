from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from repave_engine import __version__
from repave_engine.blueprint import (
    group_blueprints_by_artifact,
    list_blueprints,
    load_blueprint,
)
from repave_engine.gates import GateResult, all_gates_passed
from repave_engine.module_inventory import inventory_modules_json, inventory_versions_json
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.provider_catalog import get_service_definition, load_provider_catalog
from repave_engine.settings import OutputConfig, load_output_config
from repave_engine.upgrade_plan import UpgradePlanResult, plan_upgrade


def create_app(*, repo_root: Path, output_config: OutputConfig | None = None) -> FastAPI:
    package_dir = Path(__file__).parent
    templates = Jinja2Templates(directory=str(package_dir / "templates"))
    templates.env.cache = None
    resolved_output = output_config or load_output_config(repo_root)

    app = FastAPI(title="repave", version=__version__)
    app.mount(
        "/static",
        StaticFiles(directory=str(package_dir / "static")),
        name="static",
    )

    def page_context(**extra: object) -> dict[str, object]:
        return {
            "app_version": __version__,
            "env_badge": os.environ.get("REPAVE_ENV"),
            **extra,
        }

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

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        blueprints = list_blueprints(repo_root / "blueprints")
        catalog_groups = group_blueprints_by_artifact(blueprints)
        return templates.TemplateResponse(
            request,
            "index.html",
            page_context(
                blueprints=blueprints,
                catalog_groups=catalog_groups,
                nav_active="catalog",
            ),
        )

    @app.get("/blueprints/{blueprint_name}", response_class=HTMLResponse)
    async def blueprint_form(request: Request, blueprint_name: str) -> HTMLResponse:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        return templates.TemplateResponse(
            request,
            "blueprint_form.html",
            page_context(
                blueprint=blueprint,
                provider_catalog=load_provider_catalog(blueprint.path),
                nav_active="catalog",
            ),
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

    @app.post("/generate")
    async def generate(request: Request) -> HTMLResponse:
        form = await request.form()
        blueprint_name = str(form.get("blueprint_name", ""))
        dry_run = str(form.get("dry_run", "true")).lower() != "false"
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
            github_token=github_token,
            repo_root=repo_root,
        )

        return templates.TemplateResponse(
            request,
            "result.html",
            page_context(
                result=result,
                nav_active="catalog",
                gate_summary=gate_summary(result.gates),
                gates_ok=all_gates_passed(result.gates),
            ),
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/update", response_class=HTMLResponse)
    async def update_form(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "update.html",
            page_context(nav_active="update"),
        )

    @app.post("/update", response_class=HTMLResponse)
    async def update_plan(request: Request) -> HTMLResponse:
        form = await request.form()
        target_repo_raw = str(form.get("target_repo", "")).strip()
        blueprint_override = str(form.get("blueprint", "")).strip() or None

        if not target_repo_raw:
            return templates.TemplateResponse(
                request,
                "update.html",
                page_context(
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
                    nav_active="update",
                    error_message=str(exc),
                    target_repo=target_repo_raw,
                    blueprint=blueprint_override or "",
                ),
            )

        branch = _suggested_upgrade_branch(plan)
        cli_apply = (
            f"repave update --no-dry-run --git-branch {branch} --path {target_repo.resolve()}"
        )
        return templates.TemplateResponse(
            request,
            "update_result.html",
            page_context(
                nav_active="update",
                plan=plan,
                target_repo=str(target_repo.resolve()),
                cli_apply_command=cli_apply,
            ),
        )

    return app


def _suggested_upgrade_branch(plan: UpgradePlanResult) -> str:
    safe_name = plan.blueprint_name.replace("/", "-")
    safe_version = plan.blueprint_version.replace("/", "-")
    return f"repave/upgrade/{safe_name}-{safe_version}"
