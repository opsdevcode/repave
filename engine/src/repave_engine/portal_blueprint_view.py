"""Blueprint form template context assembly for the developer portal."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from repave_engine.ansible_catalog import catalog_for_api as ansible_catalog_for_api
from repave_engine.ansible_catalog import load_ansible_catalog
from repave_engine.ansible_pattern import (
    blueprint_supports_collection_sample_patterns,
    blueprint_supports_playbook_patterns,
    blueprint_supports_role_patterns,
)
from repave_engine.assistant_draft import validate_draft_inputs
from repave_engine.blueprint import blueprint_dir, load_blueprint
from repave_engine.dashboard_pack import blueprint_supports_dashboard_packs
from repave_engine.diff_view import (
    catalog_pin_diff_panels,
    diff_view_models,
    split_diff_view_models,
)
from repave_engine.governance_annotations import build_governance_previews
from repave_engine.governance_preflight import build_blueprint_preflight
from repave_engine.mandatory_policy import evaluate_policy_skip
from repave_engine.monitor_pack import blueprint_supports_monitor_packs
from repave_engine.observability_catalog import catalog_for_api as observability_catalog_for_api
from repave_engine.observability_catalog import catalog_has_field_options
from repave_engine.observability_selection import (
    blueprint_supports_observability_field_catalog,
    blueprint_supports_observability_notifications,
    observability_input_defaults,
)
from repave_engine.policy_catalog import (
    catalog_for_api,
    enabled_rule_ids_for_profile,
    load_policy_catalog,
)
from repave_engine.policy_selection import (
    blueprint_supports_optional_policy,
    blueprint_supports_policy_customization,
    policy_input_defaults,
)
from repave_engine.portal_context import portal_recent_activity
from repave_engine.provider_catalog import load_provider_catalog
from repave_engine.service_inventory import load_merged_observability_catalog
from repave_engine.settings import OutputConfig
from repave_engine.standards_diff import catalog_pin_diffs_for_blueprint, standards_diff_for_pin


def build_blueprint_form_extras(
    *,
    repo_root: Path,
    blueprint_name: str,
    modules_root: Path,
    output_config: OutputConfig,
    query_params: Mapping[str, str] | None = None,
) -> dict[str, object]:
    blueprint = load_blueprint(blueprint_dir(repo_root, blueprint_name), repo_root=repo_root)
    policy_catalog: dict[str, object] | None = None
    policy_defaults: dict[str, str] = {}
    policy_enabled_rule_ids: set[str] = set()
    if blueprint_supports_policy_customization(blueprint) or blueprint_supports_optional_policy(
        blueprint
    ):
        policy_defaults = policy_input_defaults(blueprint)
        catalog = load_policy_catalog(repo_root)
        policy_catalog = catalog_for_api(
            catalog,
            blueprint.artifact_type,
            defaults=policy_defaults,
        )
        profile = policy_defaults.get("policy_profile", "estate-default")
        policy_enabled_rule_ids = enabled_rule_ids_for_profile(
            catalog,
            profile=profile,
            artifact_type=blueprint.artifact_type,
        )
    policy_mandatory = not evaluate_policy_skip(blueprint, repo_root).allowed
    if policy_mandatory:
        policy_defaults = {**policy_defaults, "enable_policy": "true"}
    observability_catalog: dict[str, object] | None = None
    observability_defaults: dict[str, str] = {}
    observability_field_catalog = False
    obs_catalog_form = (
        blueprint_supports_observability_notifications(blueprint)
        or blueprint_supports_dashboard_packs(blueprint)
        or blueprint_supports_observability_field_catalog(blueprint)
    )
    if obs_catalog_form:
        observability_defaults = observability_input_defaults(blueprint, repo_root)
        for field in blueprint.inputs:
            if field.name == "backend" and field.default not in (None, ""):
                observability_defaults.setdefault("backend", str(field.default))
        obs_cat, obs_catalog_service_ids = load_merged_observability_catalog(
            repo_root,
            modules_root,
        )
        observability_field_catalog = blueprint_supports_observability_field_catalog(
            blueprint
        ) and catalog_has_field_options(obs_cat)
        observability_catalog = observability_catalog_for_api(
            obs_cat,
            defaults=observability_defaults,
            backend=observability_defaults.get("backend", "grafana"),
            blueprint_name=blueprint.name,
            catalog_service_ids=obs_catalog_service_ids,
        )
    ansible_catalog: dict[str, object] | None = None
    ansible_role_patterns = blueprint_supports_role_patterns(blueprint)
    ansible_playbook_patterns = blueprint_supports_playbook_patterns(blueprint)
    ansible_collection_sample_patterns = blueprint_supports_collection_sample_patterns(blueprint)
    if ansible_role_patterns or ansible_playbook_patterns or ansible_collection_sample_patterns:
        ansible_cat = load_ansible_catalog(repo_root)
        ansible_catalog = ansible_catalog_for_api(
            ansible_cat,
            defaults=dict(ansible_cat.defaults),
            support_linux=True,
            support_windows=False,
            blueprint_name=blueprint.name,
        )
    provider_catalog = load_provider_catalog(blueprint.path)
    form_stepper = None
    supports_form_mode = any(field.advanced or field.guided_from for field in blueprint.inputs)
    form_mode_default = "guided"
    profile = policy_defaults.get("policy_profile", "estate-default")
    standards = standards_diff_for_pin(
        repo_root,
        standard_source=blueprint.standard_source,
        pinned_version=blueprint.standard_version,
    )
    pin_diffs = catalog_pin_diffs_for_blueprint(repo_root, blueprint)
    pin_diff_panels = catalog_pin_diff_panels(repo_root, pin_diffs)
    pin_drift = any(item.has_changes for item in pin_diffs)
    try:
        policy_catalog_obj = load_policy_catalog(repo_root)
    except FileNotFoundError:
        policy_catalog_obj = None
    enabled_policy_ids = policy_enabled_rule_ids
    if not enabled_policy_ids and policy_catalog_obj is not None:
        enabled_policy_ids = enabled_rule_ids_for_profile(
            policy_catalog_obj,
            profile=profile,
            artifact_type=blueprint.artifact_type,
        )
    policy_rules = (
        tuple(rule for rule in policy_catalog_obj.rules if rule.id in enabled_policy_ids)
        if policy_catalog_obj is not None
        else ()
    )
    governance_previews = build_governance_previews(
        repo_root,
        standards,
        policy_rules,
    )
    raw_query = {
        str(key): str(value)
        for key, value in (query_params or {}).items()
        if isinstance(value, str)
    }
    form_prefill = validate_draft_inputs(blueprint, raw_query)
    return {
        "blueprint": blueprint,
        "provider_catalog": provider_catalog,
        "form_stepper": form_stepper,
        "supports_form_mode": supports_form_mode,
        "form_mode_default": form_mode_default,
        "has_guided_identity": any(field.guided_from for field in blueprint.inputs),
        "standards_diff": standards,
        "standards_diff_views": diff_view_models(standards),
        "standards_diff_split_views": split_diff_view_models(repo_root, standards),
        "pin_diff_panels": pin_diff_panels,
        "pin_drift": pin_drift,
        "governance_previews": governance_previews,
        "form_prefill": form_prefill,
        "governance_preflight": build_blueprint_preflight(
            blueprint,
            output_config=output_config,
            policy_profile=profile,
        ),
        "recent_activity": portal_recent_activity(repo_root),
        "policy_customization": blueprint_supports_policy_customization(blueprint),
        "policy_customization_optional": blueprint_supports_optional_policy(blueprint),
        "policy_mandatory": policy_mandatory,
        "policy_defaults": policy_defaults,
        "policy_catalog": policy_catalog,
        "policy_enabled_rule_ids": policy_enabled_rule_ids,
        "observability_notifications": blueprint_supports_observability_notifications(blueprint),
        "observability_dashboard_packs": blueprint_supports_dashboard_packs(blueprint),
        "observability_monitor_packs": blueprint_supports_monitor_packs(blueprint),
        "observability_field_catalog": observability_field_catalog,
        "observability_defaults": observability_defaults,
        "observability_catalog": observability_catalog,
        "ansible_role_patterns": ansible_role_patterns,
        "ansible_playbook_patterns": ansible_playbook_patterns,
        "ansible_collection_sample_patterns": ansible_collection_sample_patterns,
        "ansible_catalog": ansible_catalog,
    }
