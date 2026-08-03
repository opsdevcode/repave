"""Portal helpers for multi-component repave add on service detail pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from repave_engine.blueprint import Blueprint, blueprints_dir, list_blueprints
from repave_engine.entity_catalog import CatalogEntity
from repave_engine.provenance_components import (
    blueprint_names_from_provenance,
    list_provenance_components,
)
from repave_engine.provenance_inputs import load_provenance_document


@dataclass(frozen=True)
class ComponentSummary:
    component_id: str
    blueprint_name: str
    blueprint_version: str
    primary: bool


@dataclass(frozen=True)
class ComponentAddContext:
    available: bool
    local_path: Path | None
    git_required_message: str
    components: tuple[ComponentSummary, ...]
    addable_blueprints: tuple[Blueprint, ...]
    flash_status: str
    flash_message: str

    def to_template_dict(self) -> dict[str, Any]:
        return {
            "component_add_available": self.available,
            "component_add_local_path": str(self.local_path) if self.local_path else "",
            "component_add_git_message": self.git_required_message,
            "provenance_components": self.components,
            "addable_blueprints": self.addable_blueprints,
            "component_add_flash_status": self.flash_status,
            "component_add_flash_message": self.flash_message,
        }


def build_component_add_context(
    entity: CatalogEntity,
    repo_root: Path,
    *,
    flash_status: str = "",
    flash_message: str = "",
) -> ComponentAddContext:
    repo_dir = entity.local_path
    if repo_dir is None:
        return ComponentAddContext(
            available=False,
            local_path=None,
            git_required_message="",
            components=(),
            addable_blueprints=(),
            flash_status=flash_status,
            flash_message=flash_message,
        )

    provenance_path = repo_dir / "repave.yaml"
    if not provenance_path.is_file():
        return ComponentAddContext(
            available=False,
            local_path=repo_dir,
            git_required_message="",
            components=(),
            addable_blueprints=(),
            flash_status=flash_status,
            flash_message=flash_message,
        )

    try:
        doc = load_provenance_document(provenance_path)
        components = tuple(
            ComponentSummary(
                component_id=item.id,
                blueprint_name=item.blueprint_name,
                blueprint_version=item.blueprint_version,
                primary=item.primary,
            )
            for item in list_provenance_components(doc)
        )
        existing = blueprint_names_from_provenance(doc)
    except ValueError:
        return ComponentAddContext(
            available=False,
            local_path=repo_dir,
            git_required_message="",
            components=(),
            addable_blueprints=(),
            flash_status=flash_status,
            flash_message=flash_message,
        )

    addable = tuple(
        blueprint
        for blueprint in list_blueprints(blueprints_dir(repo_root))
        if blueprint.name not in existing
    )
    git_message = ""
    if not (repo_dir / ".git").is_dir():
        git_message = "Apply requires a local git checkout; plan preview still works."

    return ComponentAddContext(
        available=bool(addable),
        local_path=repo_dir,
        git_required_message=git_message,
        components=components,
        addable_blueprints=addable,
        flash_status=flash_status,
        flash_message=flash_message,
    )


def component_add_redirect_url(entity_id: str, *, status: str, message: str) -> str:
    params = f"add_status={quote(status)}&add_message={quote(message)}"
    return f"/services/{entity_id}?{params}"
