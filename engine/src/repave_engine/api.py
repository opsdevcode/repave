from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from repave_engine import __version__
from repave_engine.blueprint import list_blueprints, load_blueprint, load_provider_catalog
from repave_engine.pipeline import generate_from_blueprint
from repave_engine.settings import OutputConfig, load_output_config


def create_app(*, repo_root: Path, output_config: OutputConfig | None = None) -> FastAPI:
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
    templates.env.cache = None
    resolved_output = output_config or load_output_config(repo_root)

    app = FastAPI(title="repave", version=__version__)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        blueprints = list_blueprints(repo_root / "blueprints")
        return templates.TemplateResponse(
            request,
            "index.html",
            {"blueprints": blueprints},
        )

    @app.get("/blueprints/{blueprint_name}", response_class=HTMLResponse)
    async def blueprint_form(request: Request, blueprint_name: str) -> HTMLResponse:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        return templates.TemplateResponse(
            request,
            "blueprint_form.html",
            {
                "blueprint": blueprint,
                "provider_catalog": load_provider_catalog(blueprint),
            },
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
        )

        return templates.TemplateResponse(
            request,
            "result.html",
            {"result": result},
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
