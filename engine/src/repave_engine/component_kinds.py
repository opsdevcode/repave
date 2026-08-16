"""Catalog of vended managed-component kinds (ADR 013)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repave_engine.workload_profiles import STACK_NAME_RE
from repave_engine.yaml_util import load_yaml_mapping_soft

COMPONENT_NAME_RE = STACK_NAME_RE
BUILTIN_COMPONENT_KIND_IDS = frozenset({"database", "bucket", "queue"})
DEFAULT_COMPONENT_BLUEPRINT = "terraform-environment-stack"


class ComponentVendError(ValueError):
    """Invalid component vend request; the message names the field to change."""


@dataclass(frozen=True)
class ComponentKind:
    id: str
    label: str
    blueprint: str
    description: str = ""
    default_inputs: dict[str, Any] = field(default_factory=dict)

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "blueprint": self.blueprint,
            "description": self.description,
            "default_inputs": dict(self.default_inputs),
        }


def builtin_component_kinds() -> tuple[ComponentKind, ...]:
    return (
        ComponentKind(
            id="database",
            label="Managed database",
            blueprint="terraform-component-database",
            description="Relational database instance requested through GitOps.",
            default_inputs={"description": "Managed database component"},
        ),
        ComponentKind(
            id="bucket",
            label="Object bucket",
            blueprint="terraform-component-bucket",
            description="Object storage bucket requested through GitOps.",
            default_inputs={"description": "Managed bucket component"},
        ),
        ComponentKind(
            id="queue",
            label="Message queue",
            blueprint="terraform-component-queue",
            description="Managed queue requested through GitOps.",
            default_inputs={"description": "Managed queue component"},
        ),
    )


def load_component_kinds(path: Path | None) -> tuple[ComponentKind, ...]:
    """Return operator overrides, or the built-in database/bucket/queue catalog."""
    if path is None or not path.is_file():
        return builtin_component_kinds()
    doc = load_yaml_mapping_soft(path)
    if doc is None:
        return builtin_component_kinds()
    raw_list = doc.get("kinds")
    if not isinstance(raw_list, list) or not raw_list:
        return builtin_component_kinds()
    kinds: list[ComponentKind] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        kind_id = str(item.get("id", "")).strip()
        blueprint = str(item.get("blueprint", "")).strip() or DEFAULT_COMPONENT_BLUEPRINT
        if not kind_id:
            continue
        inputs_raw = item.get("default_inputs", {})
        inputs = dict(inputs_raw) if isinstance(inputs_raw, dict) else {}
        kinds.append(
            ComponentKind(
                id=kind_id,
                label=str(item.get("label", kind_id)).strip() or kind_id,
                blueprint=blueprint,
                description=str(item.get("description", "")).strip(),
                default_inputs=inputs,
            )
        )
    return tuple(kinds) if kinds else builtin_component_kinds()


def find_component_kind(kinds: tuple[ComponentKind, ...], kind_id: str) -> ComponentKind | None:
    needle = kind_id.strip()
    for item in kinds:
        if item.id == needle:
            return item
    return None
