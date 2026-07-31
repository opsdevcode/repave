"""Composite golden path bundles (multi-blueprint orchestration)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from repave_engine.blueprint import (
    Blueprint,
    InputField,
    _find_repo_root,
    blueprint_dir,
    bundles_dir,
    load_blueprint,
    validate_inputs,
)
from repave_engine.settings import GateOverrides


@dataclass(frozen=True)
class BundleMember:
    member_id: str
    blueprint_name: str
    input_mapping: dict[str, str]


@dataclass(frozen=True)
class Bundle:
    name: str
    version: str
    description: str
    path: Path
    inputs: tuple[InputField, ...]
    members: tuple[BundleMember, ...]


def _bundles_dir(repo_root: Path) -> Path:
    return bundles_dir(repo_root)


def _bundle_schema_path(repo_root: Path) -> Path:
    return repo_root / "schemas" / "bundle.schema.json"


def load_bundle_schema(repo_root: Path) -> dict[str, Any]:
    path = _bundle_schema_path(repo_root)
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def list_bundles(repo_root: Path) -> list[Bundle]:
    bundles_root = _bundles_dir(repo_root)
    if not bundles_root.is_dir():
        return []
    results: list[Bundle] = []
    for bundle_file in sorted(bundles_root.glob("*/bundle.yaml")):
        results.append(load_bundle(bundle_file.parent, repo_root=repo_root))
    return results


def load_bundle(bundle_dir: Path, *, repo_root: Path | None = None) -> Bundle:
    bundle_dir = bundle_dir.resolve()
    bundle_file = bundle_dir / "bundle.yaml"
    if not bundle_file.is_file():
        raise FileNotFoundError(f"bundle manifest not found: {bundle_file}")
    root = repo_root if repo_root is not None else _find_repo_root(bundle_dir)
    raw = yaml.safe_load(bundle_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"invalid bundle YAML: {bundle_file}")
    schema = load_bundle_schema(root)
    jsonschema.validate(raw, schema)

    metadata = raw["metadata"]
    spec = raw["spec"]
    inputs = tuple(
        InputField(
            name=str(field["name"]),
            type=str(field.get("type", "string")),
            required=bool(field.get("required", False)),
            description=str(field.get("description", "")),
            default=field.get("default"),
            enum=tuple(field["enum"]) if field.get("enum") else (),
            multi=bool(field.get("multi", False)),
        )
        for field in spec["inputs"]
    )
    members = tuple(
        BundleMember(
            member_id=str(member["id"]),
            blueprint_name=str(member["blueprint"]),
            input_mapping={str(k): str(v) for k, v in member["input_mapping"].items()},
        )
        for member in spec["members"]
    )
    return Bundle(
        name=str(metadata["name"]),
        version=str(metadata["version"]),
        description=str(metadata.get("description", "")),
        path=bundle_dir,
        inputs=inputs,
        members=members,
    )


def validate_bundle_inputs(bundle: Bundle, values: dict[str, Any]) -> dict[str, str]:
    """Validate shared bundle inputs (same rules as blueprint string fields)."""
    normalized: dict[str, str] = {}
    for field in bundle.inputs:
        raw = values.get(field.name, field.default if field.default is not None else "")
        text = str(raw).strip() if raw is not None else ""
        if field.required and not text:
            raise ValueError(f"{field.name} is required")
        if field.enum and text and text not in field.enum:
            allowed = ", ".join(field.enum)
            raise ValueError(f"Invalid {field.name}: {text!r}. Allowed: {allowed}")
        if not text and field.default is not None:
            text = str(field.default)
        normalized[field.name] = text
    return normalized


def build_bundle_context(
    shared: dict[str, str],
    *,
    github_org: str,
) -> dict[str, str]:
    service_name = shared["service_name"]
    image_repo = shared.get("image_repository", "").strip()
    if not image_repo:
        image_repo = f"ghcr.io/{github_org}/app-{service_name}"
    helm_chart_repo = f"https://github.com/{github_org}/helm-{service_name}"
    context = dict(shared)
    context.update(
        {
            "github_org": github_org,
            "image_repository": image_repo,
            "helm_chart_repo": helm_chart_repo,
            "app_repo_name": f"app-{service_name}",
            "helm_repo_name": f"helm-{service_name}",
        }
    )
    return context


def render_mapping_value(template: str, context: dict[str, str]) -> str:
    result = template
    for key, value in context.items():
        result = result.replace("{" + key + "}", value)
    if "{" in result and "}" in result:
        raise ValueError(f"unresolved template placeholders in mapping value: {result!r}")
    return result


def map_member_inputs(
    member: BundleMember,
    context: dict[str, str],
) -> dict[str, str]:
    return {
        field_name: render_mapping_value(template, context)
        for field_name, template in member.input_mapping.items()
    }


def resolve_member_blueprint(
    repo_root: Path,
    member: BundleMember,
) -> Blueprint:
    path = blueprint_dir(repo_root, member.blueprint_name)
    return load_blueprint(path, repo_root=repo_root)


def prepare_member_values(
    repo_root: Path,
    member: BundleMember,
    context: dict[str, str],
    *,
    gate_overrides: GateOverrides | None = None,
) -> tuple[Blueprint, dict[str, Any]]:
    blueprint = resolve_member_blueprint(repo_root, member)
    mapped = map_member_inputs(member, context)
    normalized = validate_inputs(
        blueprint,
        mapped,
        repo_root=repo_root,
        gate_overrides=gate_overrides,
    )
    return blueprint, normalized
