from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ServiceCatalog = dict[str, list[str]]
ProviderServices = dict[str, ServiceCatalog]
ProviderCatalog = dict[str, ProviderServices]

SCOPE_MODES = frozenset({"basic", "custom"})


def load_provider_catalog(blueprint_path: Path) -> ProviderCatalog:
    catalog_path = blueprint_path / "provider-catalog.json"
    if not catalog_path.exists():
        return {}

    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected object in {catalog_path}")

    catalog: ProviderCatalog = {}
    for provider, services in data.items():
        if not isinstance(services, dict):
            raise ValueError(f"Expected service map for provider {provider!r} in {catalog_path}")
        provider_services: ProviderServices = {}
        for service, definition in services.items():
            if not isinstance(definition, dict):
                raise ValueError(
                    f"Expected resource definition for {provider}/{service} in {catalog_path}"
                )
            resources = definition.get("resources", [])
            basic = definition.get("basic", [])
            if not isinstance(resources, list) or not all(
                isinstance(item, str) for item in resources
            ):
                raise ValueError(f"Expected resources string list for {provider}/{service}")
            if not isinstance(basic, list) or not all(isinstance(item, str) for item in basic):
                raise ValueError(f"Expected basic string list for {provider}/{service}")
            provider_services[str(service)] = {
                "resources": resources,
                "basic": basic,
            }
        catalog[str(provider)] = provider_services
    return catalog


def list_provider_services(catalog: ProviderCatalog, provider: str) -> list[str]:
    return sorted(catalog.get(provider, {}))


def get_service_definition(
    catalog: ProviderCatalog, provider: str, service: str
) -> ServiceCatalog | None:
    return catalog.get(provider, {}).get(service)


def normalize_provider_service_scope(
    catalog: ProviderCatalog,
    *,
    provider: str,
    services: list[str],
    scope_raw: Any,
) -> str:
    if provider not in catalog:
        allowed = ", ".join(sorted(catalog))
        raise ValueError(
            f"Invalid value for cloud_provider: {provider!r}. Allowed values: {allowed}"
        )

    scope = _parse_scope(scope_raw)
    normalized: dict[str, dict[str, Any]] = {}

    for service in services:
        if service not in catalog[provider]:
            raise ValueError(
                f"Invalid provider_services for {provider}: {service}. "
                f"Choose from the {len(catalog[provider])} services in provider-catalog.json."
            )

        entry = scope.get(service, {"mode": "basic"})
        if not isinstance(entry, dict):
            raise ValueError(f"provider_service_scope entry for {service!r} must be an object")

        mode = str(entry.get("mode", "basic"))
        if mode not in SCOPE_MODES:
            raise ValueError(
                f"Invalid mode for {service!r}: {mode!r}. Allowed values: basic, custom"
            )

        definition = catalog[provider][service]
        allowed_resources = set(definition["resources"])
        basic_resources = list(definition["basic"])

        if mode == "basic":
            if not basic_resources:
                raise ValueError(
                    f"No basic resources defined for {provider}/{service}; choose custom instead"
                )
            raw_additional = entry.get("additional_resources", [])
            if not isinstance(raw_additional, list):
                raise ValueError(f"additional_resources for {service!r} must be a list")
            additional = sorted({str(item).strip() for item in raw_additional if str(item).strip()})
            invalid = sorted(set(additional) - allowed_resources)
            if invalid:
                raise ValueError(
                    f"Invalid additional resources for {provider}/{service}: {', '.join(invalid)}"
                )
            resources = sorted(set(basic_resources) | set(additional))
            normalized[service] = {
                "mode": "basic",
                "include_basic": True,
                "additional_resources": additional,
                "resources": resources,
            }
        else:
            raw_resources = entry.get("resources", [])
            if not isinstance(raw_resources, list):
                raise ValueError(f"resources for {service!r} must be a list")
            resources = sorted({str(item).strip() for item in raw_resources if str(item).strip()})
            if not resources:
                raise ValueError(f"Custom scope for {service!r} must include at least one resource")
            invalid = sorted(set(resources) - allowed_resources)
            if invalid:
                raise ValueError(
                    f"Invalid resources for {provider}/{service}: {', '.join(invalid)}"
                )

            normalized[service] = {
                "mode": "custom",
                "include_basic": False,
                "additional_resources": [],
                "resources": resources,
            }

    return json.dumps(normalized, separators=(",", ":"), sort_keys=True)


def _parse_scope(scope_raw: Any) -> dict[str, Any]:
    if scope_raw in (None, ""):
        return {}
    if isinstance(scope_raw, dict):
        return scope_raw
    if isinstance(scope_raw, str):
        try:
            parsed = json.loads(scope_raw)
        except json.JSONDecodeError as exc:
            raise ValueError("provider_service_scope must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("provider_service_scope must be a JSON object")
        return parsed
    raise ValueError("provider_service_scope must be a JSON object")
