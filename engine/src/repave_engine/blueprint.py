from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml


@dataclass(frozen=True)
class InputField:
    name: str
    type: str
    required: bool
    description: str = ""
    default: Any = None
    enum: tuple[str, ...] = ()


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
    output_repo_name_template: str
    output_title_template: str

    @property
    def template_dir(self) -> Path:
        return self.path / self.template_path


def load_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "blueprint.schema.json"
    return cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))


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
            enum=tuple(item.get("enum", [])),
        )
        for item in spec["inputs"]
    )

    output = spec["output"]
    repository = output.get("repository", {})
    repo_name_template = repository.get("name_template", "tf-{module_name}")
    title_template = repository.get("title_template", "Bootstrap {module_name}")
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
        output_repo_name_template=str(repo_name_template),
        output_title_template=str(title_template),
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

    for field in blueprint.inputs:
        if field.name not in normalized or field.enum == ():
            continue
        value = str(normalized[field.name])
        if value not in field.enum:
            allowed = ", ".join(field.enum)
            raise ValueError(
                f"Invalid value for {field.name}: {value!r}. Allowed values: {allowed}"
            )

    _validate_provider_services(blueprint, normalized)

    return normalized


def _validate_provider_services(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    catalog = load_provider_catalog(blueprint)
    if not catalog:
        return

    if "cloud_provider" not in normalized or "provider_services" not in normalized:
        return

    provider = str(normalized["cloud_provider"])
    if provider not in catalog:
        allowed = ", ".join(sorted(catalog))
        raise ValueError(
            f"Invalid value for cloud_provider: {provider!r}. Allowed values: {allowed}"
        )

    raw_services = str(normalized["provider_services"]).split(",")
    services = [item.strip() for item in raw_services if item.strip()]
    if not services:
        raise ValueError("provider_services must include at least one service")

    allowed_services = set(catalog[provider])
    invalid = sorted({service for service in services if service not in allowed_services})
    if invalid:
        raise ValueError(
            f"Invalid provider_services for {provider}: {', '.join(invalid)}. "
            f"Choose from the {len(allowed_services)} services in provider-catalog.json."
        )

    normalized["provider_services"] = ",".join(sorted(services))


def load_provider_catalog(blueprint: Blueprint) -> dict[str, list[str]]:
    catalog_path = blueprint.path / "provider-catalog.json"
    if not catalog_path.exists():
        return {}

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {catalog_path}")

    catalog: dict[str, list[str]] = {}
    for provider, services in data.items():
        if not isinstance(services, list) or not all(isinstance(item, str) for item in services):
            raise ValueError(f"Expected string list for provider {provider!r} in {catalog_path}")
        catalog[str(provider)] = services
    return catalog


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
