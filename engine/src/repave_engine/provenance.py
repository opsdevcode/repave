from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from repave_engine import __version__
from repave_engine.blueprint import Blueprint
from repave_engine.ci_workflow import build_ci_provenance_block
from repave_engine.governance import governance_provenance_block
from repave_engine.policy_selection import PolicySelection, policy_provenance_block


def _opa_provenance_block(blueprint: Blueprint) -> dict[str, str] | None:
    if blueprint.opa_policies is None:
        return None
    return {
        "policies_source": blueprint.opa_policies.policies_source,
        "policy_version": blueprint.opa_policies.policy_version,
    }


def _azure_policy_provenance_block(blueprint: Blueprint) -> dict[str, str] | None:
    if blueprint.azure_policy_pack is None:
        return None
    return {
        "definitions_source": blueprint.azure_policy_pack.definitions_source,
        "policy_version": blueprint.azure_policy_pack.policy_version,
    }


def load_artifact_schema(repo_root: Path | None = None) -> dict[str, Any]:
    if repo_root is not None:
        schema_path = repo_root / "schemas" / "golden-path-artifact.schema.json"
    else:
        schema_path = Path(__file__).resolve().parent / "data" / "golden-path-artifact.schema.json"
    return cast(dict[str, Any], json.loads(schema_path.read_text(encoding="utf-8")))


def _parse_provider_services(values: dict[str, Any]) -> list[str]:
    provider_services = values.get("provider_services", "")
    if isinstance(provider_services, str):
        return [item.strip() for item in provider_services.split(",") if item.strip()]
    if isinstance(provider_services, list):
        return [str(item) for item in provider_services]
    return []


def _build_terraform_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    module_name = str(values.get("module_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "terraform-module",
        "terraformModule": {
            "module_name": module_name,
            "cloud_provider": str(values.get("cloud_provider", "")),
            "provider_services": _parse_provider_services(values),
        },
    }
    if blueprint.terraform_layout == "single-resource":
        spec["terraformModule"]["provider_service"] = str(
            values.get("provider_service", "")
        ).strip()
        spec["terraformModule"]["provider_resource"] = str(
            values.get("provider_resource", "")
        ).strip()
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    opa = _opa_provenance_block(blueprint)
    if opa is not None:
        spec["opa"] = opa
    return spec, module_name


def _build_environment_stack_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    stack_name = str(values.get("stack_name", blueprint.name))
    pinned_raw = values.get("pinned_modules")
    pinned_list: list[dict[str, Any]] = []
    if isinstance(pinned_raw, list):
        for item in pinned_raw:
            if not isinstance(item, dict):
                continue
            entry: dict[str, Any] = {
                "name": str(item.get("name", "")).strip(),
                "source": str(item.get("source", "")).strip(),
            }
            version = str(item.get("version", "")).strip()
            if version:
                entry["version"] = version
            repo_name = str(item.get("repo_name", "")).strip()
            if repo_name:
                entry["repo_name"] = repo_name
            if entry["name"] and entry["source"]:
                pinned_list.append(entry)
    spec: dict[str, Any] = {
        "artifactType": "terraform-environment-stack",
        "terraformEnvironmentStack": {
            "stack_name": stack_name,
            "cloud_provider": str(values.get("cloud_provider", "")),
            "environment": str(values.get("environment", "dev")),
            "pinned_modules": pinned_list,
        },
    }
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    opa = _opa_provenance_block(blueprint)
    if opa is not None:
        spec["opa"] = opa
    return spec, stack_name


def _build_ansible_playbook_project_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    project_name = str(values.get("project_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "ansible-playbook-project",
        "ansiblePlaybookProject": {
            "project_name": project_name,
            "environment": str(values.get("environment", "dev")),
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansiblePlaybookProject"]["min_ansible_version"] = str(min_version)
    pinned = values.get("pinned_roles")
    if isinstance(pinned, list) and pinned:
        spec["ansiblePlaybookProject"]["pinned_roles"] = [
            {
                "galaxy_name": str(item.get("galaxy_name", "")),
                "version": str(item.get("version", "")),
                "src": str(item.get("src", "")),
                **({"repo_name": str(item["repo_name"]).strip()} if item.get("repo_name") else {}),
            }
            for item in pinned
            if isinstance(item, dict)
        ]
    pattern = str(values.get("playbook_pattern_source", "")).strip()
    if pattern:
        spec["ansiblePlaybookProject"]["playbook_pattern_source"] = pattern
    collections = values.get("_playbook_pattern_requires_collections")
    if isinstance(collections, list):
        names = sorted({str(item).strip() for item in collections if str(item).strip()})
        if names:
            spec["ansiblePlaybookProject"]["required_collections"] = names
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    return spec, project_name


def _build_ansible_spec(blueprint: Blueprint, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
    role_name = str(values.get("role_name", blueprint.name))
    namespace = str(values.get("namespace", ""))
    spec: dict[str, Any] = {
        "artifactType": "ansible-role",
        "ansibleRole": {
            "role_name": role_name,
            "namespace": namespace,
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansibleRole"]["min_ansible_version"] = str(min_version)
    platforms = values.get("target_platforms")
    if isinstance(platforms, str) and platforms.strip():
        spec["ansibleRole"]["target_platforms"] = platforms.strip()
    elif isinstance(platforms, list) and platforms:
        spec["ansibleRole"]["target_platforms"] = ",".join(
            sorted(str(item).strip() for item in platforms if str(item).strip())
        )
    pattern = str(values.get("role_pattern_source", "")).strip()
    if pattern:
        spec["ansibleRole"]["role_pattern_source"] = pattern
    collections = values.get("_role_pattern_requires_collections")
    if isinstance(collections, list):
        cleaned = sorted({str(item).strip() for item in collections if str(item).strip()})
        if cleaned:
            spec["ansibleRole"]["required_collections"] = cleaned
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    metadata_name = f"{namespace}.{role_name}" if namespace else role_name
    return spec, metadata_name


def _build_ansible_collection_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    namespace = str(values.get("namespace", ""))
    collection_name = str(values.get("collection_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "ansible-collection",
        "ansibleCollection": {
            "namespace": namespace,
            "collection_name": collection_name,
        },
    }
    min_version = values.get("min_ansible_version")
    if min_version not in (None, ""):
        spec["ansibleCollection"]["min_ansible_version"] = str(min_version)
    sample_role = str(values.get("sample_role_name", "sample")).strip()
    if sample_role:
        spec["ansibleCollection"]["sample_role_name"] = sample_role
    pattern = str(values.get("sample_role_pattern_source", "")).strip()
    if pattern:
        spec["ansibleCollection"]["sample_role_pattern_source"] = pattern
    collections = values.get("_collection_sample_requires_collections")
    if isinstance(collections, list):
        names = sorted({str(item).strip() for item in collections if str(item).strip()})
        if names:
            spec["ansibleCollection"]["required_collections"] = names
    if blueprint.ansible_lint_pack is not None:
        spec["ansibleLint"] = {
            "pack_source": blueprint.ansible_lint_pack.pack_source,
            "pack_version": blueprint.ansible_lint_pack.pack_version,
        }
    metadata_name = f"{namespace}.{collection_name}" if namespace else collection_name
    return spec, metadata_name


def _build_observability_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    service_name = str(values.get("service_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "observability",
        "observability": {
            "service_name": service_name,
            "organization": str(values.get("organization", "")).strip(),
            "team": str(values.get("team", "")).strip(),
            "backend": str(values.get("backend", "prometheus")).strip(),
            "output_mode": str(values.get("output_mode", "native")).strip(),
            "environment": str(values.get("environment", "")).strip(),
            "notification_source": str(values.get("notification_source", "")).strip(),
            "notification_target": str(values.get("notification_target", "")).strip(),
        },
    }
    runbook = str(values.get("runbook_url", "")).strip()
    if runbook:
        spec["observability"]["runbook_url"] = runbook
    slo = str(values.get("slo_target_percent", "")).strip()
    if slo:
        spec["observability"]["slo_target_percent"] = slo
    focus = str(values.get("observability_focus", "")).strip()
    if focus:
        spec["observability"]["focus"] = focus
    datasource_uid = str(values.get("datasource_uid", "")).strip()
    if datasource_uid:
        spec["observability"]["datasource_uid"] = datasource_uid
    pack_source = str(values.get("dashboard_pack_source", "")).strip()
    if pack_source:
        spec["observability"]["dashboard_pack_source"] = pack_source
    monitor_pack = str(values.get("monitor_pack_source", "")).strip()
    if monitor_pack:
        spec["observability"]["monitor_pack_source"] = monitor_pack
    config_mode = str(values.get("configuration_mode", "")).strip()
    if config_mode:
        spec["observability"]["configuration_mode"] = config_mode
    return spec, service_name


def _build_opa_policy_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    policy_name = str(values.get("policy_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "opa-policy",
        "opaPolicy": {
            "policy_name": policy_name,
            "organization": str(values.get("organization", "")).strip(),
        },
    }
    opa = _opa_provenance_block(blueprint)
    if opa is not None:
        spec["opa"] = opa
    return spec, policy_name


def _build_azure_policy_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    policy_name = str(values.get("policy_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "azure-policy",
        "azurePolicy": {
            "policy_name": policy_name,
            "organization": str(values.get("organization", "")).strip(),
        },
    }
    azure = _azure_policy_provenance_block(blueprint)
    if azure is not None:
        spec["azurePolicyDefinitions"] = azure
    return spec, policy_name


def _build_checkov_policy_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    policy_name = str(values.get("policy_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "checkov-policy",
        "checkovPolicy": {
            "policy_name": policy_name,
            "organization": str(values.get("organization", "")).strip(),
        },
    }
    if blueprint.checkov_policies is not None:
        spec["checkov"] = {
            "policies_source": blueprint.checkov_policies.policies_source,
            "policy_version": blueprint.checkov_policies.policy_version,
        }
    return spec, policy_name


def _build_helm_chart_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    chart_name = str(values.get("chart_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "helm-chart",
        "helmChart": {
            "chart_name": chart_name,
            "app_name": str(values.get("app_name", "")).strip(),
            "image_repository": str(values.get("image_repository", "")).strip(),
            "image_tag": str(values.get("image_tag", "")).strip(),
            "service_type": str(values.get("service_type", "ClusterIP")).strip(),
            "enable_ingress": str(values.get("enable_ingress", "false")).strip(),
        },
    }
    host = str(values.get("ingress_host", "")).strip()
    if host:
        spec["helmChart"]["ingress_host"] = host
    return spec, chart_name


def _build_app_service_spec(
    blueprint: Blueprint,
    values: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    service_name = str(values.get("service_name", blueprint.name))
    spec: dict[str, Any] = {
        "artifactType": "app-service",
        "appService": {
            "service_name": service_name,
            "owner": str(values.get("owner", "")).strip(),
            "port": str(values.get("port", "8080")).strip(),
            "runtime": str(values.get("runtime", "python")).strip(),
            "include_helm_reference": str(values.get("include_helm_reference", "false")).strip(),
        },
    }
    chart_repo = str(values.get("helm_chart_repo", "")).strip()
    if chart_repo:
        spec["appService"]["helm_chart_repo"] = chart_repo
    return spec, service_name


def _provenance_generated_at() -> str:
    fixed = os.environ.get("REPAVE_PROVENANCE_GENERATED_AT", "").strip()
    if fixed:
        return fixed
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_provenance_document(blueprint: Blueprint, values: dict[str, Any]) -> dict[str, Any]:
    if blueprint.artifact_type == "ansible-role":
        artifact_spec, metadata_name = _build_ansible_spec(blueprint, values)
    elif blueprint.artifact_type == "ansible-playbook-project":
        artifact_spec, metadata_name = _build_ansible_playbook_project_spec(blueprint, values)
    elif blueprint.artifact_type == "ansible-collection":
        artifact_spec, metadata_name = _build_ansible_collection_spec(blueprint, values)
    elif blueprint.artifact_type == "opa-policy":
        artifact_spec, metadata_name = _build_opa_policy_spec(blueprint, values)
    elif blueprint.artifact_type == "azure-policy":
        artifact_spec, metadata_name = _build_azure_policy_spec(blueprint, values)
    elif blueprint.artifact_type == "checkov-policy":
        artifact_spec, metadata_name = _build_checkov_policy_spec(blueprint, values)
    elif blueprint.artifact_type == "terraform-environment-stack":
        artifact_spec, metadata_name = _build_environment_stack_spec(blueprint, values)
    elif blueprint.artifact_type == "observability":
        artifact_spec, metadata_name = _build_observability_spec(blueprint, values)
    elif blueprint.artifact_type == "helm-chart":
        artifact_spec, metadata_name = _build_helm_chart_spec(blueprint, values)
    elif blueprint.artifact_type == "app-service":
        artifact_spec, metadata_name = _build_app_service_spec(blueprint, values)
    else:
        artifact_spec, metadata_name = _build_terraform_spec(blueprint, values)

    policy_block = policy_provenance_block(
        values.get("_policy_selection")
        if isinstance(values.get("_policy_selection"), PolicySelection)
        else None
    )
    spec_body: dict[str, Any] = {
        **artifact_spec,
        "governance": governance_provenance_block(),
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
            "generated_at": _provenance_generated_at(),
        },
    }
    if policy_block is not None:
        spec_body["policy"] = policy_block
    spec_body["ci"] = build_ci_provenance_block(blueprint)

    return {
        "apiVersion": "repave.dev/v1beta1",
        "kind": "GoldenPathArtifact",
        "metadata": {"name": metadata_name},
        "spec": spec_body,
    }


def write_provenance_file(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    filename: str,
) -> Path:
    path = output_dir / filename
    document = build_provenance_document(blueprint, values)

    class _ProvenanceDumper(yaml.SafeDumper):
        def increase_indent(self, flow: bool = False, indentless: bool = False) -> Any:
            return super().increase_indent(flow, False)

    body = yaml.dump(
        document,
        Dumper=_ProvenanceDumper,
        sort_keys=False,
        default_flow_style=False,
        indent=2,
        width=4096,
    )
    path.write_text(f"---\n{body}", encoding="utf-8")
    return path


def validate_provenance_file(path: Path, repo_root: Path | None = None) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"Provenance file missing: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    schema = load_artifact_schema(repo_root)
    jsonschema.validate(instance=data, schema=schema)
