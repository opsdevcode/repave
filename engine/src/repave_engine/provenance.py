from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from repave_engine import __version__
from repave_engine.blueprint import Blueprint


def load_artifact_schema(repo_root: Path) -> dict[str, Any]:
    schema_path = repo_root / "schemas" / "golden-path-artifact.schema.json"
    return cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))


def build_provenance_document(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    module_name = str(values.get("module_name", blueprint.name))
    provider_services = values.get("provider_services", "")
    if isinstance(provider_services, str):
        services = [item.strip() for item in provider_services.split(",") if item.strip()]
    elif isinstance(provider_services, list):
        services = [str(item) for item in provider_services]
    else:
        services = []

    document: dict[str, Any] = {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": module_name},
        "spec": {
            "blueprint": {
                "name": blueprint.name,
                "version": blueprint.version,
            },
            "standard": {
                "source": blueprint.standard_source,
                "version": blueprint.standard_version,
            },
            "generation": {
                "engine_version": __version__,
                "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
            },
            "module": {
                "module_name": module_name,
                "cloud_provider": str(values.get("cloud_provider", "")),
                "provider_services": services,
            },
        },
    }

    if blueprint.checkov_policies is not None:
        document["spec"]["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }

    return document


def write_provenance_file(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    filename: str,
) -> Path:
    path = output_dir / filename
    document = build_provenance_document(blueprint, values)
    path.write_text(
        yaml.safe_dump(document, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def validate_provenance_file(path: Path, repo_root: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Provenance file missing: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = load_artifact_schema(repo_root)
    jsonschema.validate(instance=data, schema=schema)
