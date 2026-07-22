from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from repave_engine.blueprint import list_blueprints, load_blueprint
from repave_engine.pipeline import generate_from_blueprint

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def create_app(*, repo_root: Path) -> FastAPI:
    app = FastAPI(title="repave", version="0.1.0")
    output_root = repo_root / ".repave-out"
    output_root.mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        blueprints = list_blueprints(repo_root / "blueprints")
        return TEMPLATES.TemplateResponse(
            "index.html",
            {
                "request": request,
                "blueprints": blueprints,
            },
        )

    @app.get("/blueprints/{blueprint_name}", response_class=HTMLResponse)
    async def blueprint_form(request: Request, blueprint_name: str) -> HTMLResponse:
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        return TEMPLATES.TemplateResponse(
            "blueprint_form.html",
            {
                "request": request,
                "blueprint": blueprint,
            },
        )

    @app.post("/generate")
    async def generate(request: Request) -> HTMLResponse:
        form = await request.form()
        blueprint_name = str(form.get("blueprint_name", ""))
        dry_run = str(form.get("dry_run", "true")).lower() != "false"
        blueprint = load_blueprint(repo_root / "blueprints" / blueprint_name, repo_root)
        values = {field.name: str(form.get(field.name, "")) for field in blueprint.inputs}

        result = generate_from_blueprint(
            blueprint,
            values,
            output_root=output_root,
            dry_run=dry_run,
        )

        return TEMPLATES.TemplateResponse(
            "result.html",
            {
                "request": request,
                "result": result,
            },
        )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
