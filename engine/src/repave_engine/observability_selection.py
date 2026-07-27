from __future__ import annotations

from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.observability_catalog import (
    catalog_has_field_options,
    form_preset_for_blueprint,
    load_observability_catalog,
    service_by_id,
    source_by_id,
    target_ids_for_source,
    teams_for_organization,
)


def blueprint_supports_observability_notifications(blueprint: Blueprint) -> bool:
    return any(field.name == "notification_source" for field in blueprint.inputs)


def blueprint_supports_observability_field_catalog(blueprint: Blueprint) -> bool:
    return blueprint.artifact_type == "observability"


def _blueprint_input_names(blueprint: Blueprint) -> set[str]:
    return {field.name for field in blueprint.inputs}


def observability_input_defaults(blueprint: Blueprint, repo_root: Path) -> dict[str, str]:
    catalog = load_observability_catalog(repo_root)
    defaults = dict(catalog.defaults)
    for field in blueprint.inputs:
        if field.name in defaults and field.default not in (None, ""):
            defaults[field.name] = str(field.default)
    source_id = defaults.get("notification_source", "")
    source = source_by_id(catalog, source_id)
    if source and source.targets:
        target_default = defaults.get("notification_target", "")
        if target_default not in {t.id for t in source.targets}:
            defaults["notification_target"] = source.targets[0].id
    service = service_by_id(catalog, defaults.get("service_name", ""))
    if service:
        defaults.setdefault("organization", service.organization)
        defaults.setdefault("team", service.team)
        defaults.setdefault("description", service.description)
        if service.runbook_url:
            defaults.setdefault("runbook_url", service.runbook_url)
    return defaults


def effective_catalog_defaults(
    blueprint: Blueprint,
    values: dict[str, Any],
    repo_root: Path,
) -> dict[str, str]:
    catalog = load_observability_catalog(repo_root)
    merged = observability_input_defaults(blueprint, repo_root)
    for key, value in values.items():
        if value not in (None, ""):
            merged[str(key)] = str(value).strip()
    service_id = str(merged.get("service_name", "")).strip()
    service = service_by_id(catalog, service_id)
    if service:
        merged["service_name"] = service.id
        merged["organization"] = service.organization
        merged["team"] = service.team
        merged["description"] = service.description
        if service.runbook_url:
            merged["runbook_url"] = service.runbook_url
    source_id = merged.get("notification_source", "")
    source = source_by_id(catalog, source_id)
    if source and source.targets:
        target_default = merged.get("notification_target", "")
        if target_default not in {t.id for t in source.targets}:
            merged["notification_target"] = source.targets[0].id
    return merged


def apply_recommended_configuration(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    mode = str(normalized.get("configuration_mode", "recommended")).strip()
    if mode != "recommended":
        return
    catalog = load_observability_catalog(repo_root)
    preset = form_preset_for_blueprint(catalog, blueprint.name)
    if preset is None:
        return
    effective = effective_catalog_defaults(blueprint, normalized, repo_root)
    decision = set(preset.decision_fields)
    for field in blueprint.inputs:
        if field.name in decision:
            continue
        if field.name in effective:
            normalized[field.name] = effective[field.name]


def normalize_observability_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    if blueprint_supports_observability_field_catalog(blueprint):
        apply_recommended_configuration(blueprint, normalized, repo_root)
    if blueprint_supports_observability_notifications(blueprint):
        _normalize_notification_inputs(blueprint, normalized, repo_root)
    if blueprint_supports_observability_field_catalog(blueprint):
        _normalize_catalog_field_inputs(blueprint, normalized, repo_root)
    mode = str(normalized.get("configuration_mode", "recommended")).strip()
    if mode not in ("recommended", "custom"):
        raise ValueError(
            f"Invalid configuration_mode: {mode!r}. Allowed values: recommended, custom"
        )
    normalized["configuration_mode"] = mode
    if blueprint.name == "observability-as-code-generic":
        output_mode = str(normalized.get("output_mode", "native")).strip()
        if output_mode not in ("native", "terraform"):
            raise ValueError(
                f"Invalid output_mode: {output_mode!r}. Allowed values: native, terraform"
            )
        normalized["output_mode"] = output_mode
        backend = str(normalized.get("backend", "prometheus")).strip()
        if output_mode == "terraform" and backend not in (
            "datadog",
            "grafana",
            "prometheus",
            "otel",
        ):
            raise ValueError(
                "Terraform output_mode for observability-as-code requires backend: "
                "datadog, grafana, prometheus, or otel"
            )
    if blueprint.name == "monitors-as-code-generic":
        output_mode = str(normalized.get("output_mode", "native")).strip()
        if output_mode not in ("native", "terraform"):
            raise ValueError(
                f"Invalid output_mode: {output_mode!r}. Allowed values: native, terraform"
            )
        normalized["output_mode"] = output_mode
        backend = str(normalized.get("backend", "datadog")).strip()
        if backend not in ("datadog", "prometheus"):
            raise ValueError(
                "Invalid backend for monitors-as-code. Allowed values: datadog, prometheus"
            )
        if output_mode == "terraform" and backend not in ("datadog", "prometheus"):
            raise ValueError(
                "Terraform output_mode for monitors-as-code requires backend: datadog or prometheus"
            )
    if blueprint.name == "dashboards-as-code-generic":
        output_mode = str(normalized.get("output_mode", "native")).strip()
        if output_mode not in ("native", "terraform"):
            raise ValueError(
                f"Invalid output_mode: {output_mode!r}. Allowed values: native, terraform"
            )
        normalized["output_mode"] = output_mode
        if output_mode == "terraform":
            backend = str(normalized.get("backend", "grafana")).strip()
            if backend not in ("grafana", "datadog"):
                raise ValueError(
                    "Terraform output_mode for dashboards-as-code requires backend: "
                    "grafana or datadog"
                )


def _normalize_notification_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    catalog = load_observability_catalog(repo_root)
    form_defaults = observability_input_defaults(blueprint, repo_root)

    source_id = str(
        normalized.get("notification_source", form_defaults.get("notification_source", ""))
    ).strip()
    source = source_by_id(catalog, source_id)
    if source is None:
        allowed = ", ".join(item.id for item in catalog.notification_sources)
        raise ValueError(f"Invalid notification_source: {source_id!r}. Allowed values: {allowed}")
    normalized["notification_source"] = source_id

    target_id = str(
        normalized.get("notification_target", form_defaults.get("notification_target", ""))
    ).strip()
    allowed_targets = target_ids_for_source(catalog, source_id)
    if target_id not in allowed_targets:
        allowed = ", ".join(sorted(allowed_targets))
        raise ValueError(
            f"Invalid notification_target: {target_id!r} for source {source_id!r}. "
            f"Allowed values: {allowed}"
        )
    normalized["notification_target"] = target_id
    _enrich_notification_metadata(catalog, normalized)


def _enrich_notification_metadata(catalog: Any, normalized: dict[str, Any]) -> None:
    source_id = str(normalized.get("notification_source", "")).strip()
    source = source_by_id(catalog, source_id)
    if source is None:
        return
    target_id = str(normalized.get("notification_target", "")).strip()
    target = next((item for item in source.targets if item.id == target_id), None)
    if target is None:
        return
    normalized["notification_provider"] = source.provider
    normalized["notification_target_label"] = target.label


def _normalize_catalog_field_inputs(
    blueprint: Blueprint,
    normalized: dict[str, Any],
    repo_root: Path,
) -> None:
    catalog = load_observability_catalog(repo_root)
    if not catalog_has_field_options(catalog):
        return

    names = _blueprint_input_names(blueprint)
    form_defaults = observability_input_defaults(blueprint, repo_root)

    if "service_name" in names:
        service_id = str(
            normalized.get("service_name", form_defaults.get("service_name", ""))
        ).strip()
        service = service_by_id(catalog, service_id)
        if service is None:
            allowed = ", ".join(item.id for item in catalog.services)
            raise ValueError(f"Invalid service_name: {service_id!r}. Allowed values: {allowed}")
        normalized["service_name"] = service_id

    if "organization" in names:
        org = str(normalized.get("organization", form_defaults.get("organization", ""))).strip()
        if org not in {item.id for item in catalog.organizations}:
            allowed = ", ".join(item.id for item in catalog.organizations)
            raise ValueError(f"Invalid organization: {org!r}. Allowed values: {allowed}")
        normalized["organization"] = org

    if "team" in names:
        team = str(normalized.get("team", form_defaults.get("team", ""))).strip()
        org = str(normalized.get("organization", "")).strip()
        allowed_teams = teams_for_organization(catalog, org) if org else catalog.teams
        allowed_ids = {item.id for item in allowed_teams}
        if team not in allowed_ids:
            allowed = ", ".join(sorted(allowed_ids))
            raise ValueError(
                f"Invalid team: {team!r} for organization {org!r}. Allowed values: {allowed}"
            )
        normalized["team"] = team

    if "environment" in names and catalog.environments:
        env = str(normalized.get("environment", form_defaults.get("environment", ""))).strip()
        if env not in {item.id for item in catalog.environments}:
            allowed = ", ".join(item.id for item in catalog.environments)
            raise ValueError(f"Invalid environment: {env!r}. Allowed values: {allowed}")
        normalized["environment"] = env

    if "datasource_uid" in names and catalog.grafana_datasources:
        uid = str(normalized.get("datasource_uid", form_defaults.get("datasource_uid", ""))).strip()
        if uid not in {item.uid for item in catalog.grafana_datasources}:
            allowed = ", ".join(item.uid for item in catalog.grafana_datasources)
            raise ValueError(f"Invalid datasource_uid: {uid!r}. Allowed values: {allowed}")
        normalized["datasource_uid"] = uid

    if "runbook_url" in names and catalog.runbooks:
        url = str(normalized.get("runbook_url", form_defaults.get("runbook_url", ""))).strip()
        allowed_urls = {item.url for item in catalog.runbooks}
        if url and url not in allowed_urls:
            allowed = ", ".join(sorted(allowed_urls))
            raise ValueError(f"Invalid runbook_url: {url!r}. Allowed values: {allowed}")
        normalized["runbook_url"] = url

    if "slo_target_percent" in names and catalog.slo_targets:
        slo = str(
            normalized.get("slo_target_percent", form_defaults.get("slo_target_percent", ""))
        ).strip()
        allowed_values = {item.value for item in catalog.slo_targets}
        if slo not in allowed_values:
            allowed = ", ".join(sorted(allowed_values))
            raise ValueError(f"Invalid slo_target_percent: {slo!r}. Allowed values: {allowed}")
        normalized["slo_target_percent"] = slo
