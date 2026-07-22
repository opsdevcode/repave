from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json

import jsonschema
import yaml


@dataclass(frozen=True)
class InputField:
    name: str
    type: str
    required: bool
    description: str = ""
    default: Any = None


@dataclass(frozen=True)
class Blueprint:
    path: Path
    name: str
    version: str
    description: str
    standard_source: str
    standard_version: str
    inputs: tuple[InputField, ...]
    template_engine: str
    template_path: str
    gates: tuple[str, ...]
    output_type: str
    output_target: str

    @property
    def template_dir(self) -> Path:
        return self.path / self.template_path


def load_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "blueprint.schema.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def load_blueprint(blueprint_path: Path, repo_root: Path | None = None) -> Blueprint:
    blueprint_path = blueprint_path.resolve()
    if blueprint_path.is_dir():
        blueprint_file = blueprint_path / "blueprint.yaml"
    else:
        blueprint_file = blueprint_path

    if not blueprint_file.exists():
        raise FileNotFoundError(f"Blueprint not found: {blueprint_file}")

    data = yaml.safe_load(blueprint_file.read_text(encoding="utf-8"))
    root = repo_root or _find_repo_root(blueprint_file.parent)
    schema = load_schema(root)
    jsonschema.validate(instance=data, schema=schema)

    metadata = data["metadata"]
    spec = data["spec"]
    inputs = tuple(
        InputField(
            name=item["name"],
            type=item["type"],
            required=bool(item["required"]),
            description=item.get("description", ""),
            default=item.get("default"),
        )
        for item in spec["inputs"]
    )

    output = spec["output"]
    return Blueprint(
        path=blueprint_file.parent,
        name=metadata["name"],
        version=metadata["version"],
        description=metadata.get("description", ""),
        standard_source=spec["standard"]["source"],
        standard_version=spec["standard"]["version"],
        inputs=inputs,
        template_engine=spec["template"]["engine"],
        template_path=spec["template"]["path"],
        gates=tuple(spec["gates"]),
        output_type=output["type"],
        output_target=output.get("target", "repo"),
    )


def validate_inputs(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field in blueprint.inputs:
        if field.name in values:
            normalized[field.name] = values[field.name]
        elif field.default is not None:
            normalized[field.name] = field.default
        elif field.required:
            raise ValueError(f"Missing required input: {field.name}")

    unknown = set(values) - {f.name for f in blueprint.inputs}
    if unknown:
        raise ValueError(f"Unknown input fields: {', '.join(sorted(unknown))}")

    return normalized


def list_blueprints(blueprints_dir: Path) -> list[Blueprint]:
    results: list[Blueprint] = []
    if not blueprints_dir.exists():
        return results

    for blueprint_file in sorted(blueprints_dir.glob("*/blueprint.yaml")):
        results.append(load_blueprint(blueprint_file.parent, _find_repo_root(blueprints_dir)))
    return results


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "schemas" / "blueprint.schema.json").exists():
            return candidate
    raise FileNotFoundError("Could not locate repave repo root (schemas/blueprint.schema.json)")
