"""Shared builders for state store tests."""

from __future__ import annotations

import json
from typing import Any

DEFAULT_LINEAGE = "0f3a1b2c-1111-2222-3333-444455556666"


def make_state(
    *,
    serial: int = 1,
    lineage: str = DEFAULT_LINEAGE,
    resources: list[dict[str, Any]] | None = None,
    outputs: dict[str, Any] | None = None,
    terraform_version: str = "1.9.0",
) -> bytes:
    """A state v4 document.

    Serialized with indentation on purpose: byte-exactness assertions are only
    meaningful against a document that is not already in canonical form.
    """
    payload = {
        "version": 4,
        "terraform_version": terraform_version,
        "serial": serial,
        "lineage": lineage,
        "outputs": outputs if outputs is not None else {},
        "resources": resources if resources is not None else [],
    }
    return json.dumps(payload, indent=2).encode("utf-8")


def managed_resource(
    resource_type: str,
    name: str,
    *,
    attributes: dict[str, Any] | None = None,
    depends_on: list[str] | None = None,
    module: str | None = None,
    provider: str = 'provider["registry.terraform.io/hashicorp/aws"]',
    index_key: Any = None,
) -> dict[str, Any]:
    instance: dict[str, Any] = {
        "schema_version": 0,
        "attributes": attributes if attributes is not None else {"id": f"{name}-id"},
    }
    if depends_on is not None:
        instance["dependencies"] = depends_on
    if index_key is not None:
        instance["index_key"] = index_key

    resource: dict[str, Any] = {
        "mode": "managed",
        "type": resource_type,
        "name": name,
        "provider": provider,
        "instances": [instance],
    }
    if module is not None:
        resource["module"] = module
    return resource
