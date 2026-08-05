"""Normalize a state v4 document into resources, instances, and edges (ADR 004 Phase 2).

Redaction happens here, before anything reaches a queryable column. Terraform state
stores provider secrets in plaintext, and normalizing them into indexed columns would
multiply the exposure surface — the blob is encrypted at rest, but a `SELECT` is not.

Three redaction sources, applied together:

1. `sensitive_attributes` recorded in the instance by Terraform itself.
2. Provider schema sensitivity from `<binary> providers schema -json`, when cached.
3. A conservative name denylist, because 1 and 2 both miss things in practice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

from repave_engine.statestore.state_document import StateDocument

REDACTED: Final = "__REDACTED__"

EDGE_DEPENDS_ON: Final = "depends_on"
EDGE_REFERENCE: Final = "reference"

#: Substring match, case-insensitive. Deliberately broad: a false positive costs one
#: unqueryable column, a false negative leaks a credential into the index.
SENSITIVE_NAME_PATTERNS: Final[tuple[str, ...]] = (
    "password",
    "secret",
    "token",
    "private_key",
    "privatekey",
    "credential",
    "passphrase",
    "client_secret",
    "access_key",
    "session_key",
    "encryption_key",
    "cert_key",
    "auth",
    "signature",
)

_INDEX_SUFFIX = re.compile(r"\[[^\]]*\]$")


@dataclass(frozen=True)
class ResourceInstance:
    address: str
    index_key: str | None
    schema_version: int
    attributes: dict[str, Any]
    redacted_keys: tuple[str, ...]


@dataclass(frozen=True)
class Resource:
    address: str
    module: str
    mode: str
    type: str
    name: str
    provider: str
    instances: tuple[ResourceInstance, ...] = ()

    @property
    def is_data_source(self) -> bool:
        return self.mode == "data"


@dataclass(frozen=True)
class Edge:
    from_address: str
    to_address: str
    kind: str


@dataclass
class NormalizedState:
    resources: list[Resource] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)

    @property
    def addresses(self) -> set[str]:
        return {resource.address for resource in self.resources}


def resource_address(resource: dict[str, Any]) -> str:
    """Full address including module path and the `data.` prefix for data sources."""
    parts: list[str] = []
    module = str(resource.get("module", "")).strip()
    if module:
        parts.append(module)
    if str(resource.get("mode", "managed")) == "data":
        parts.append("data")
    parts.append(str(resource.get("type", "")))
    parts.append(str(resource.get("name", "")))
    return ".".join(part for part in parts if part)


def instance_address(base: str, index_key: Any) -> str:
    if index_key is None:
        return base
    if isinstance(index_key, int) and not isinstance(index_key, bool):
        return f"{base}[{index_key}]"
    return f'{base}["{index_key}"]'


def strip_index(address: str) -> str:
    """`aws_instance.web[0]` -> `aws_instance.web`."""
    return _INDEX_SUFFIX.sub("", address)


def is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return any(pattern in lowered for pattern in SENSITIVE_NAME_PATTERNS)


def _sensitive_paths_from_instance(instance: dict[str, Any]) -> set[str]:
    """Top-level attribute names Terraform flagged as sensitive.

    Terraform records these as nested path expressions. Only the first `get_attr`
    segment is used: redacting the whole top-level attribute is the conservative
    reading, and partial redaction of a nested structure is not worth the risk.
    """
    found: set[str] = set()
    raw = instance.get("sensitive_attributes")
    if not isinstance(raw, list):
        return found
    for path in raw:
        if not isinstance(path, list) or not path:
            continue
        head = path[0]
        if isinstance(head, dict) and head.get("type") == "get_attr":
            value = head.get("value")
            if isinstance(value, str) and value:
                found.add(value)
    return found


def redact_attributes(
    attributes: dict[str, Any],
    *,
    declared_sensitive: set[str] | None = None,
    schema_sensitive: set[str] | None = None,
) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Replace sensitive values with a marker. Returns (attributes, redacted keys)."""
    declared = declared_sensitive or set()
    schema = schema_sensitive or set()

    cleaned: dict[str, Any] = {}
    redacted: list[str] = []
    for key, value in attributes.items():
        if key in declared or key in schema or is_sensitive_name(key):
            cleaned[key] = REDACTED
            redacted.append(key)
            continue
        cleaned[key] = value
    return cleaned, tuple(sorted(redacted))


def normalize_state(
    document: StateDocument,
    *,
    schema_sensitive: dict[str, set[str]] | None = None,
) -> NormalizedState:
    """Build the resource graph from a parsed state document.

    `schema_sensitive` maps a resource type to attribute names the provider schema
    marks sensitive. Absent, redaction falls back to the instance's own declarations
    and the name denylist.
    """
    per_type = schema_sensitive or {}
    result = NormalizedState()

    for raw in document.resources():
        address = resource_address(raw)
        if not address:
            continue
        resource_type = str(raw.get("type", ""))
        instances = _normalize_instances(raw, address, per_type.get(resource_type, set()))
        result.resources.append(
            Resource(
                address=address,
                module=str(raw.get("module", "")),
                mode=str(raw.get("mode", "managed")),
                type=resource_type,
                name=str(raw.get("name", "")),
                provider=str(raw.get("provider", "")),
                instances=instances,
            )
        )
        result.edges.extend(_depends_on_edges(raw, address))

    result.edges = _dedupe(result.edges)
    return result


def _normalize_instances(
    raw: dict[str, Any], address: str, schema_sensitive: set[str]
) -> tuple[ResourceInstance, ...]:
    items = raw.get("instances")
    if not isinstance(items, list):
        return ()

    instances: list[ResourceInstance] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        attributes = item.get("attributes")
        if not isinstance(attributes, dict):
            attributes = {}
        cleaned, redacted = redact_attributes(
            attributes,
            declared_sensitive=_sensitive_paths_from_instance(item),
            schema_sensitive=schema_sensitive,
        )
        index_key = item.get("index_key")
        instances.append(
            ResourceInstance(
                address=instance_address(address, index_key),
                index_key=None if index_key is None else str(index_key),
                schema_version=_as_int(item.get("schema_version")),
                attributes=cleaned,
                redacted_keys=redacted,
            )
        )
    return tuple(instances)


def _depends_on_edges(raw: dict[str, Any], address: str) -> list[Edge]:
    """Edges from the `dependencies` Terraform resolved at apply time."""
    edges: list[Edge] = []
    items = raw.get("instances")
    if not isinstance(items, list):
        return edges
    for item in items:
        if not isinstance(item, dict):
            continue
        dependencies = item.get("dependencies")
        if not isinstance(dependencies, list):
            continue
        for dependency in dependencies:
            target = strip_index(str(dependency).strip())
            if not target or target == address:
                continue
            edges.append(Edge(from_address=address, to_address=target, kind=EDGE_DEPENDS_ON))
    return edges


def edges_from_plan_json(payload: Any) -> list[Edge]:
    """Config-derived edges from `configuration.*.resources[].expressions`.

    Higher fidelity than state `dependencies`, because it captures references that
    resolved to a constant at apply time. Required before any Phase 4 partitioning
    (ADR 004 decision 5); until then it is an optional enrichment.
    """
    if not isinstance(payload, dict):
        return []
    configuration = payload.get("configuration")
    if not isinstance(configuration, dict):
        return []

    edges: list[Edge] = []
    root = configuration.get("root_module")
    if isinstance(root, dict):
        _collect_module_edges(root, prefix="", edges=edges)
    return _dedupe(edges)


def _collect_module_edges(module: dict[str, Any], *, prefix: str, edges: list[Edge]) -> None:
    resources = module.get("resources")
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, dict):
                continue
            address = str(resource.get("address", "")).strip()
            if not address:
                continue
            full = f"{prefix}{address}"
            for target in _expression_references(resource.get("expressions")):
                resolved = f"{prefix}{target}"
                if resolved != full:
                    edges.append(Edge(from_address=full, to_address=resolved, kind=EDGE_REFERENCE))

    calls = module.get("module_calls")
    if isinstance(calls, dict):
        for name, call in calls.items():
            if not isinstance(call, dict):
                continue
            child = call.get("module")
            if isinstance(child, dict):
                _collect_module_edges(child, prefix=f"{prefix}module.{name}.", edges=edges)


def _expression_references(expressions: Any) -> set[str]:
    """Resource addresses referenced by an expressions block, at any nesting depth."""
    found: set[str] = set()
    if isinstance(expressions, dict):
        references = expressions.get("references")
        if isinstance(references, list):
            for reference in references:
                target = _reference_to_address(str(reference))
                if target:
                    found.add(target)
        for key, value in expressions.items():
            if key != "references":
                found |= _expression_references(value)
    elif isinstance(expressions, list):
        for item in expressions:
            found |= _expression_references(item)
    return found


def _reference_to_address(reference: str) -> str:
    """Trim a reference like `aws_vpc.main.id` down to `aws_vpc.main`.

    Plan JSON emits both the attribute reference and the bare resource address, so
    dropping trailing attribute segments and de-duplicating recovers the resource.
    Non-resource scopes (var, local, each, count, path) are not graph nodes.
    """
    value = reference.strip()
    if not value:
        return ""
    parts = value.split(".")
    scope = parts[0]
    if scope in ("var", "local", "each", "count", "path", "terraform", "self"):
        return ""
    if scope == "data":
        return ".".join(parts[:3]) if len(parts) >= 3 else ""
    if scope == "module":
        return ".".join(parts[:2]) if len(parts) >= 2 else ""
    return ".".join(parts[:2]) if len(parts) >= 2 else ""


def sensitive_attributes_from_provider_schema(payload: Any) -> dict[str, set[str]]:
    """Map resource type to sensitive attribute names from `providers schema -json`."""
    result: dict[str, set[str]] = {}
    if not isinstance(payload, dict):
        return result
    schemas = payload.get("provider_schemas")
    if not isinstance(schemas, dict):
        return result

    for provider in schemas.values():
        if not isinstance(provider, dict):
            continue
        for key in ("resource_schemas", "data_source_schemas"):
            block = provider.get(key)
            if not isinstance(block, dict):
                continue
            for resource_type, schema in block.items():
                names = _sensitive_names(schema)
                if names:
                    result.setdefault(str(resource_type), set()).update(names)
    return result


def _sensitive_names(schema: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(schema, dict):
        return found
    block = schema.get("block")
    if not isinstance(block, dict):
        return found
    attributes = block.get("attributes")
    if isinstance(attributes, dict):
        for name, attribute in attributes.items():
            if isinstance(attribute, dict) and attribute.get("sensitive") is True:
                found.add(str(name))
    return found


def _dedupe(edges: list[Edge]) -> list[Edge]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[Edge] = []
    for edge in edges:
        key = (edge.from_address, edge.to_address, edge.kind)
        if key in seen:
            continue
        seen.add(key)
        unique.append(edge)
    return unique


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
