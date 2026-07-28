from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, cast

import jsonschema
import yaml

from repave_engine.provider_catalog import (
    get_service_definition,
    load_provider_catalog,
    normalize_provider_service_scope,
)


@dataclass(frozen=True)
class InputField:
    name: str
    type: str
    required: bool
    description: str = ""
    default: Any = None
    enum: tuple[str, ...] = ()
    multi: bool = False


@dataclass(frozen=True)
class CheckovPolicyPack:
    policies_source: str
    policy_version: str


@dataclass(frozen=True)
class OpaPolicyPack:
    policies_source: str
    policy_version: str


@dataclass(frozen=True)
class AzurePolicyPack:
    definitions_source: str
    policy_version: str


@dataclass(frozen=True)
class AnsibleLintPolicyPack:
    pack_source: str
    pack_version: str


@dataclass(frozen=True)
class AnsibleLintGateConfig:
    config_file: str = ".ansible-lint"


@dataclass(frozen=True)
class CheckovGateConfig:
    external_checks_dir: str = "policy/checkov"
    config_file: str = ".checkov.yml"
    scan_dir: str = ""
    skip_checks: tuple[str, ...] = ()
    soft_fail: bool = False


@dataclass(frozen=True)
class OpaGateConfig:
    policies_dir: str = "policy/opa/policies"
    fixtures_dir: str = "tests/fixtures"
    plan_subdir: str = ".repave"


@dataclass(frozen=True)
class AzurePolicyGateConfig:
    definitions_dir: str = "policy/definitions"


@dataclass(frozen=True)
class TflintGateConfig:
    config_file: str = ".tflint.hcl"


@dataclass(frozen=True)
class TerraformValidateGateConfig:
    var_files: tuple[str, ...] = ()


@dataclass(frozen=True)
class TerraformTestGateConfig:
    test_directory: str = "tests"


@dataclass(frozen=True)
class Blueprint:
    path: Path
    name: str
    version: str
    description: str
    artifact_type: str
    standard_source: str
    standard_version: str
    inputs: tuple[InputField, ...]
    template_engine: str
    template_path: str
    gates: tuple[str, ...]
    output_type: str
    output_repo_name_template: str
    output_title_template: str
    provenance_file: str | None = None
    checkov_policies: CheckovPolicyPack | None = None
    opa_policies: OpaPolicyPack | None = None
    azure_policy_pack: AzurePolicyPack | None = None
    ansible_lint_pack: AnsibleLintPolicyPack | None = None
    checkov_gate: CheckovGateConfig = dataclass_field(default_factory=CheckovGateConfig)
    opa_gate: OpaGateConfig = dataclass_field(default_factory=OpaGateConfig)
    azure_policy_gate: AzurePolicyGateConfig = dataclass_field(
        default_factory=AzurePolicyGateConfig
    )
    ansible_lint_gate: AnsibleLintGateConfig = dataclass_field(
        default_factory=AnsibleLintGateConfig
    )
    tflint_gate: TflintGateConfig = dataclass_field(default_factory=TflintGateConfig)
    terraform_validate_gate: TerraformValidateGateConfig = dataclass_field(
        default_factory=TerraformValidateGateConfig
    )
    terraform_test_gate: TerraformTestGateConfig = dataclass_field(
        default_factory=TerraformTestGateConfig
    )
    terraform_layout: str = "generic"
    gate_config_raw: dict[str, Any] = dataclass_field(default_factory=dict)

    @property
    def template_dir(self) -> Path:
        return self.path / self.template_path

    def gate_config_for(self, gate_name: str) -> Mapping[str, Any]:
        base: dict[str, Any] = {}
        if gate_name == "checkov":
            base = {
                "external_checks_dir": self.checkov_gate.external_checks_dir,
                "config_file": self.checkov_gate.config_file,
                "scan_dir": self.checkov_gate.scan_dir,
                "skip_checks": self.checkov_gate.skip_checks,
                "soft_fail": self.checkov_gate.soft_fail,
            }
        elif gate_name == "tflint":
            base = {"config_file": self.tflint_gate.config_file}
        elif gate_name == "terraform-validate":
            base = {"var_files": self.terraform_validate_gate.var_files}
        elif gate_name == "terraform-test":
            base = {"test_directory": self.terraform_test_gate.test_directory}
        elif gate_name == "opa":
            base = {
                "policies_dir": self.opa_gate.policies_dir,
                "fixtures_dir": self.opa_gate.fixtures_dir,
                "plan_subdir": self.opa_gate.plan_subdir,
            }
        elif gate_name == "ansible-lint":
            base = {"config_file": self.ansible_lint_gate.config_file}
        raw = self.gate_config_raw.get(gate_name, {})
        if isinstance(raw, dict):
            return {**base, **raw}
        return base


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
            multi=bool(item.get("multi", False)),
        )
        for item in spec["inputs"]
    )

    output = spec["output"]
    repository = output.get("repository", {})
    repo_name_template = repository.get("name_template", "tf-{module_name}")
    title_template = repository.get("title_template", "Bootstrap {module_name}")
    provenance_spec = output.get("provenance", {})
    provenance_file: str | None = None
    if isinstance(provenance_spec, dict) and "file" in provenance_spec:
        provenance_file = str(provenance_spec["file"])

    checkov_spec = spec.get("checkov")
    checkov_policies: CheckovPolicyPack | None = None
    if checkov_spec is not None:
        checkov_policies = CheckovPolicyPack(
            policies_source=str(checkov_spec["policies_source"]),
            policy_version=str(checkov_spec.get("policy_version", "1.0.0")),
        )

    opa_spec = spec.get("opa")
    opa_policies: OpaPolicyPack | None = None
    if opa_spec is not None:
        opa_policies = OpaPolicyPack(
            policies_source=str(opa_spec["policies_source"]),
            policy_version=str(opa_spec.get("policy_version", "1.0.0")),
        )

    azure_policy_spec = spec.get("azure_policy")
    azure_policy_pack: AzurePolicyPack | None = None
    if azure_policy_spec is not None:
        azure_policy_pack = AzurePolicyPack(
            definitions_source=str(azure_policy_spec["definitions_source"]),
            policy_version=str(azure_policy_spec.get("policy_version", "1.0.0")),
        )

    ansible_lint_spec = spec.get("ansible_lint")
    ansible_lint_pack: AnsibleLintPolicyPack | None = None
    if ansible_lint_spec is not None:
        ansible_lint_pack = AnsibleLintPolicyPack(
            pack_source=str(ansible_lint_spec["pack_source"]),
            pack_version=str(ansible_lint_spec.get("pack_version", "1.0.0")),
        )

    gate_config = spec.get("gate_config", {})
    checkov_gate_raw = gate_config.get("checkov", {}) if isinstance(gate_config, dict) else {}
    checkov_gate = CheckovGateConfig(
        external_checks_dir=str(checkov_gate_raw.get("external_checks_dir", "policy/checkov")),
        config_file=str(checkov_gate_raw.get("config_file", ".checkov.yml")),
        scan_dir=str(checkov_gate_raw.get("scan_dir", "")),
        skip_checks=tuple(checkov_gate_raw.get("skip_checks", [])),
        soft_fail=bool(checkov_gate_raw.get("soft_fail", False)),
    )
    opa_gate_raw = gate_config.get("opa", {}) if isinstance(gate_config, dict) else {}
    opa_gate = OpaGateConfig(
        policies_dir=str(opa_gate_raw.get("policies_dir", "policy/opa/policies")),
        fixtures_dir=str(opa_gate_raw.get("fixtures_dir", "tests/fixtures")),
        plan_subdir=str(opa_gate_raw.get("plan_subdir", ".repave")),
    )
    azure_gate_raw = gate_config.get("azure-policy", {}) if isinstance(gate_config, dict) else {}
    azure_policy_gate = AzurePolicyGateConfig(
        definitions_dir=str(azure_gate_raw.get("definitions_dir", "policy/definitions")),
    )
    tflint_gate_raw = gate_config.get("tflint", {}) if isinstance(gate_config, dict) else {}
    tflint_gate = TflintGateConfig(
        config_file=str(tflint_gate_raw.get("config_file", ".tflint.hcl")),
    )
    validate_gate_raw = (
        gate_config.get("terraform-validate", {}) if isinstance(gate_config, dict) else {}
    )
    terraform_validate_gate = TerraformValidateGateConfig(
        var_files=tuple(validate_gate_raw.get("var_files", [])),
    )
    test_gate_raw = gate_config.get("terraform-test", {}) if isinstance(gate_config, dict) else {}
    terraform_test_gate = TerraformTestGateConfig(
        test_directory=str(test_gate_raw.get("test_directory", "tests")),
    )
    ansible_lint_gate_raw = (
        gate_config.get("ansible-lint", {}) if isinstance(gate_config, dict) else {}
    )
    ansible_lint_gate = AnsibleLintGateConfig(
        config_file=str(ansible_lint_gate_raw.get("config_file", ".ansible-lint")),
    )

    terraform_module_spec = spec.get("terraformModule")
    terraform_layout = "generic"
    if isinstance(terraform_module_spec, dict):
        terraform_layout = str(terraform_module_spec.get("layout", "generic"))

    return Blueprint(
        path=blueprint_file.parent,
        name=metadata["name"],
        version=metadata["version"],
        description=metadata.get("description", ""),
        artifact_type=str(spec.get("artifactType", "terraform-module")),
        standard_source=spec["standard"]["source"],
        standard_version=spec["standard"]["version"],
        inputs=inputs,
        template_engine=spec["template"]["engine"],
        template_path=spec["template"]["path"],
        gates=tuple(spec["gates"]),
        output_type=output["type"],
        output_repo_name_template=str(repo_name_template),
        output_title_template=str(title_template),
        provenance_file=provenance_file,
        checkov_policies=checkov_policies,
        opa_policies=opa_policies,
        azure_policy_pack=azure_policy_pack,
        ansible_lint_pack=ansible_lint_pack,
        checkov_gate=checkov_gate,
        opa_gate=opa_gate,
        azure_policy_gate=azure_policy_gate,
        ansible_lint_gate=ansible_lint_gate,
        tflint_gate=tflint_gate,
        terraform_validate_gate=terraform_validate_gate,
        terraform_test_gate=terraform_test_gate,
        terraform_layout=terraform_layout,
        gate_config_raw=cast(dict[str, Any], gate_config) if isinstance(gate_config, dict) else {},
    )


def validate_inputs(
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    repo_root: Path | None = None,
    gate_overrides: Any = None,
) -> dict[str, Any]:
    merged_values = dict(values)
    if repo_root is not None and blueprint.artifact_type == "observability":
        from repave_engine.observability_selection import apply_recommended_configuration

        apply_recommended_configuration(blueprint, merged_values, repo_root)

    normalized: dict[str, Any] = {}
    for field in blueprint.inputs:
        if field.name in merged_values:
            normalized[field.name] = merged_values[field.name]
        elif field.default is not None:
            normalized[field.name] = field.default
        elif field.required:
            raise ValueError(f"Missing required input: {field.name}")

    unknown = set(merged_values) - {f.name for f in blueprint.inputs}
    if unknown:
        raise ValueError(f"Unknown input fields: {', '.join(sorted(unknown))}")

    for field in blueprint.inputs:
        if field.name not in normalized:
            continue
        if normalized[field.name] in (None, "") and field.default is not None:
            normalized[field.name] = field.default

    for field in blueprint.inputs:
        if field.name not in normalized or field.enum == ():
            continue
        value = str(normalized[field.name])
        if field.multi:
            parts = [part.strip() for part in value.split(",") if part.strip()]
            if field.required and not parts:
                raise ValueError(f"Missing required input: {field.name}")
            invalid = [part for part in parts if part not in field.enum]
            if invalid:
                allowed = ", ".join(field.enum)
                bad = ", ".join(invalid)
                raise ValueError(
                    f"Invalid value(s) for {field.name}: {bad!r}. Allowed values: {allowed}"
                )
            normalized[field.name] = ",".join(sorted(set(parts)))
            continue
        if value not in field.enum:
            allowed = ", ".join(field.enum)
            raise ValueError(
                f"Invalid value for {field.name}: {value!r}. Allowed values: {allowed}"
            )

    _validate_provider_scope(blueprint, normalized)
    _validate_pinned_roles(blueprint, normalized)
    _validate_pinned_modules(blueprint, normalized)
    _validate_ansible_role_platforms(blueprint, normalized)

    if repo_root is not None:
        from repave_engine.policy_selection import normalize_policy_inputs

        normalize_policy_inputs(
            blueprint,
            normalized,
            repo_root,
            gate_overrides=gate_overrides,
        )
        from repave_engine.observability_selection import normalize_observability_inputs

        normalize_observability_inputs(blueprint, normalized, repo_root)
        from repave_engine.dashboard_pack import normalize_dashboard_pack_inputs

        normalize_dashboard_pack_inputs(blueprint, normalized, repo_root)
        from repave_engine.monitor_pack import normalize_monitor_pack_inputs

        normalize_monitor_pack_inputs(blueprint, normalized, repo_root)
        from repave_engine.ansible_pattern import (
            blueprint_supports_collection_sample_patterns,
            blueprint_supports_playbook_patterns,
            blueprint_supports_role_patterns,
            normalize_collection_sample_pattern_inputs,
            normalize_playbook_pattern_inputs,
            normalize_role_pattern_inputs,
        )

        if blueprint_supports_role_patterns(blueprint):
            normalize_role_pattern_inputs(blueprint, normalized, repo_root)
        if blueprint_supports_playbook_patterns(blueprint):
            normalize_playbook_pattern_inputs(blueprint, normalized, repo_root)
        if blueprint_supports_collection_sample_patterns(blueprint):
            normalize_collection_sample_pattern_inputs(blueprint, normalized, repo_root)

    _validate_helm_chart_inputs(blueprint, normalized)
    _validate_app_service_inputs(blueprint, normalized)

    return normalized


def _validate_app_service_inputs(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.name != "app-service-generic":
        return
    if str(normalized.get("include_helm_reference", "false")).strip() == "true":
        repo = str(normalized.get("helm_chart_repo", "")).strip()
        if not repo:
            raise ValueError("helm_chart_repo is required when include_helm_reference is true")


def _validate_helm_chart_inputs(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.name != "helm-chart-generic":
        return
    if str(normalized.get("enable_ingress", "false")).strip() == "true":
        host = str(normalized.get("ingress_host", "")).strip()
        if not host:
            raise ValueError("ingress_host is required when enable_ingress is true")


def _validate_ansible_role_platforms(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.artifact_type != "ansible-role":
        return
    from repave_engine.ansible_platforms import parse_support_flag, resolve_target_platforms

    support_linux = parse_support_flag(normalized.get("support_linux"), default=True)
    support_windows = parse_support_flag(normalized.get("support_windows"), default=False)
    generation = str(normalized.get("windows_server_generation", "2022")).strip()
    advanced = normalized.get("target_platforms_advanced", "")

    resolved = resolve_target_platforms(
        support_linux=support_linux,
        support_windows=support_windows,
        windows_server_generation=generation,
        target_platforms_advanced=advanced,
    )
    normalized["support_linux"] = "true" if support_linux else "false"
    normalized["support_windows"] = "true" if support_windows else "false"
    normalized["windows_server_generation"] = generation
    normalized["target_platforms"] = resolved


def _validate_pinned_modules(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.artifact_type != "terraform-environment-stack":
        return
    from repave_engine.module_inventory import normalize_pinned_modules_raw

    raw = normalized.get("pinned_modules", "[]")
    modules = normalize_pinned_modules_raw(raw)
    if not modules:
        raise ValueError("pinned_modules must include at least one module")
    normalized["pinned_modules"] = modules


def _validate_pinned_roles(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.artifact_type != "ansible-playbook-project":
        return
    from repave_engine.ansible_role_inventory import normalize_pinned_roles_raw

    raw = normalized.get("pinned_roles", "[]")
    normalized["pinned_roles"] = normalize_pinned_roles_raw(raw)


def primary_publish_name(blueprint: Blueprint, values: dict[str, Any]) -> str:
    """Local module repo directory name for publish and PR planning."""
    if blueprint.artifact_type == "terraform-environment-stack":
        return str(values.get("stack_name", blueprint.name))
    if blueprint.artifact_type == "ansible-playbook-project":
        return str(values.get("project_name", blueprint.name))
    if blueprint.artifact_type == "ansible-collection":
        return str(values.get("collection_name", blueprint.name))
    if blueprint.artifact_type == "app-service":
        return str(values.get("service_name", blueprint.name))
    if blueprint.artifact_type == "helm-chart":
        return str(values.get("chart_name", blueprint.name))
    if blueprint.artifact_type == "observability":
        return str(values.get("service_name", blueprint.name))
    if blueprint.artifact_type == "azure-policy":
        return str(values.get("policy_name", blueprint.name))
    if blueprint.artifact_type == "opa-policy":
        return str(values.get("policy_name", blueprint.name))
    if blueprint.artifact_type == "checkov-policy":
        return str(values.get("policy_name", blueprint.name))
    if blueprint.artifact_type == "ansible-role":
        return str(values.get("role_name", blueprint.name))
    return str(values.get("module_name", blueprint.name))


def _validate_provider_scope(blueprint: Blueprint, normalized: dict[str, Any]) -> None:
    if blueprint.artifact_type != "terraform-module":
        return

    catalog = load_provider_catalog(blueprint.path)
    if not catalog:
        return

    if blueprint.terraform_layout == "single-resource":
        _validate_single_resource_scope(blueprint, normalized, catalog)
        return

    if "cloud_provider" not in normalized or "provider_services" not in normalized:
        return

    provider = str(normalized["cloud_provider"])
    raw_services = str(normalized["provider_services"]).split(",")
    services = sorted({item.strip() for item in raw_services if item.strip()})
    if not services:
        raise ValueError("provider_services must include at least one service")

    scope_raw = normalized.get("provider_service_scope", "")
    normalized["provider_services"] = ",".join(services)
    normalized["provider_service_scope"] = normalize_provider_service_scope(
        catalog,
        provider=provider,
        services=services,
        scope_raw=scope_raw,
    )
    normalized["provider_service_scope_summary"] = _format_scope_summary(
        normalized["provider_service_scope"]
    )


def _validate_single_resource_scope(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    catalog: dict[str, Any],
) -> None:
    if "cloud_provider" not in normalized:
        return
    provider = str(normalized["cloud_provider"])
    service = str(normalized.get("provider_service", "")).strip()
    resource = str(normalized.get("provider_resource", "")).strip()
    if not service or not resource:
        raise ValueError("provider_service and provider_resource are required")

    definition = get_service_definition(catalog, provider, service)
    if definition is None:
        raise ValueError(f"Unknown provider service {provider}/{service!r}")
    allowed = definition.get("resources", [])
    if resource not in allowed:
        allowed_text = ", ".join(allowed[:12])
        suffix = "..." if len(allowed) > 12 else ""
        raise ValueError(
            f"Invalid provider_resource {resource!r} for {service!r}. "
            f"Allowed: {allowed_text}{suffix}"
        )

    normalized["provider_services"] = service
    scope = {
        service: {
            "mode": "custom",
            "resources": [resource],
        }
    }
    normalized["provider_service_scope"] = json.dumps(scope)
    normalized["provider_service_scope_summary"] = _format_scope_summary(
        normalized["provider_service_scope"]
    )


def _format_scope_summary(scope_json: str) -> str:
    scope = json.loads(scope_json)
    lines: list[str] = []
    for service, entry in sorted(scope.items()):
        resources = ", ".join(entry["resources"])
        if entry["mode"] == "basic":
            additional = entry.get("additional_resources", [])
            if additional:
                mode_label = "basic capabilities + additional resources"
            else:
                mode_label = "basic capabilities"
        else:
            mode_label = "custom resources"
        lines.append(f"- **{service}** ({mode_label}): {resources}")
    return "\n".join(lines)


def list_blueprints(blueprints_dir: Path) -> list[Blueprint]:
    results: list[Blueprint] = []
    if not blueprints_dir.exists():
        return results

    for blueprint_file in sorted(blueprints_dir.glob("*/blueprint.yaml")):
        results.append(load_blueprint(blueprint_file.parent, _find_repo_root(blueprints_dir)))
    return results


# Portal catalog grouping (v1.18). Families collapse artifact types in the home UI.
_ARTIFACT_FAMILY_META: dict[str, tuple[str, str]] = {
    "terraform": ("Terraform", "Landing-zone modules, shared services, and environment stacks"),
    "ansible": ("Ansible", "Roles, collections, and automation projects for fleet operations"),
    "policy": ("Policy", "Guardrails as code—Checkov, OPA, and Azure Policy packs"),
    "observability": (
        "Observability",
        (
            "Dashboards and monitors (recommended); legacy multi-backend umbrella "
            "for OTel and mixed layouts"
        ),
    ),
    "helm": ("Kubernetes / Helm", "Workload charts for cluster delivery teams"),
    "app": ("Application services", "Service repos with Dockerfile, CI, and catalog metadata"),
}
_ARTIFACT_FAMILY_ORDER: tuple[str, ...] = (
    "terraform",
    "ansible",
    "helm",
    "app",
    "policy",
    "observability",
)
_FAMILY_ARTIFACT_ORDER: dict[str, tuple[str, ...]] = {
    "terraform": ("terraform-module", "terraform-environment-stack"),
    "ansible": ("ansible-role", "ansible-collection", "ansible-playbook-project"),
    "helm": ("helm-chart",),
    "app": ("app-service",),
    "policy": ("checkov-policy", "opa-policy", "azure-policy"),
    "observability": ("observability",),
}


def artifact_family(artifact_type: str) -> str:
    if artifact_type == "observability":
        return "observability"
    if artifact_type in ("checkov-policy", "opa-policy", "azure-policy"):
        return "policy"
    if artifact_type.startswith("terraform-"):
        return "terraform"
    if artifact_type.startswith("ansible-"):
        return "ansible"
    if artifact_type == "helm-chart":
        return "helm"
    if artifact_type == "app-service":
        return "app"
    return artifact_type


def policy_kind_label(artifact_type: str) -> str | None:
    """Short label for policy-family artifact types (portal badges)."""
    return {
        "checkov-policy": "Checkov",
        "opa-policy": "OPA",
        "azure-policy": "Azure Policy",
    }.get(artifact_type)


@dataclass(frozen=True)
class BlueprintCatalogGroup:
    family: str
    title: str
    subtitle: str
    blueprints: tuple[Blueprint, ...]


_OBSERVABILITY_BLUEPRINT_ORDER: tuple[str, ...] = (
    "dashboards-as-code-generic",
    "monitors-as-code-generic",
    "observability-as-code-generic",
)


def _sort_blueprints_in_family(family: str, items: list[Blueprint]) -> list[Blueprint]:
    if family == "observability":
        rank = {name: index for index, name in enumerate(_OBSERVABILITY_BLUEPRINT_ORDER)}

        def obs_sort_key(blueprint: Blueprint) -> tuple[int, str]:
            return (rank.get(blueprint.name, len(rank)), blueprint.name)

        return sorted(items, key=obs_sort_key)
    order = _FAMILY_ARTIFACT_ORDER.get(family, ())
    rank = {artifact_type: index for index, artifact_type in enumerate(order)}

    def sort_key(blueprint: Blueprint) -> tuple[int, str]:
        return (rank.get(blueprint.artifact_type, len(order)), blueprint.name)

    return sorted(items, key=sort_key)


def group_blueprints_by_artifact(blueprints: list[Blueprint]) -> list[BlueprintCatalogGroup]:
    """Group blueprints for the portal home catalog by Terraform / Ansible family."""
    buckets: dict[str, list[Blueprint]] = {}
    for blueprint in blueprints:
        family = artifact_family(blueprint.artifact_type)
        buckets.setdefault(family, []).append(blueprint)

    groups: list[BlueprintCatalogGroup] = []
    seen: set[str] = set()
    for family in _ARTIFACT_FAMILY_ORDER:
        items = buckets.get(family)
        if not items:
            continue
        title, subtitle = _ARTIFACT_FAMILY_META[family]
        sorted_items = _sort_blueprints_in_family(family, items)
        groups.append(
            BlueprintCatalogGroup(
                family=family,
                title=title,
                subtitle=subtitle,
                blueprints=tuple(sorted_items),
            )
        )
        seen.add(family)

    for family in sorted(buckets):
        if family in seen:
            continue
        label = family.replace("-", " ").title()
        groups.append(
            BlueprintCatalogGroup(
                family=family,
                title=label,
                subtitle="Additional golden paths",
                blueprints=tuple(sorted(buckets[family], key=lambda bp: bp.name)),
            )
        )

    family_rank = {name: index for index, name in enumerate(_ARTIFACT_FAMILY_ORDER)}

    def group_sort_key(group: BlueprintCatalogGroup) -> tuple[int, int, str]:
        return (
            -len(group.blueprints),
            family_rank.get(group.family, len(_ARTIFACT_FAMILY_ORDER)),
            group.family,
        )

    groups.sort(key=group_sort_key)
    return groups


def _find_repo_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "schemas" / "blueprint.schema.json").exists():
            return candidate
    raise FileNotFoundError("Could not locate repave repo root (schemas/blueprint.schema.json)")
