"""Declared risk classes for v3 autonomous remediation (foundation slice)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_MECHANICAL_CHANGE_TYPES = frozenset(
    {
        "pin_bump",
        "version_bump",
        "blueprint_pin_bump",
        "standard_pin_bump",
        "checkov_pin_bump",
    }
)


class RiskClass(StrEnum):
    MECHANICAL = "mechanical"
    STANDARD = "standard"
    SENSITIVE = "sensitive"


@dataclass(frozen=True)
class ChangeClassification:
    risk_class: RiskClass
    change_type: str
    blueprint: str


def classify_change(
    *,
    change_type: str,
    blueprint: str,
    declared_class: str | None = None,
) -> ChangeClassification:
    """Pure classifier — no I/O. Blueprints may declare a class; absent means inferred."""
    normalized = (change_type or "").strip().lower()
    blueprint_name = (blueprint or "").strip()
    if declared_class:
        try:
            risk = RiskClass(declared_class.strip().lower())
        except ValueError as exc:
            raise ValueError(
                f"invalid risk class {declared_class!r} on blueprint {blueprint_name!r}; "
                "use mechanical, standard, or sensitive"
            ) from exc
        return ChangeClassification(risk, normalized, blueprint_name)

    if normalized in _MECHANICAL_CHANGE_TYPES:
        return ChangeClassification(RiskClass.MECHANICAL, normalized, blueprint_name)
    if normalized in {"policy_change", "resource_shape", "crd_promotion"}:
        return ChangeClassification(RiskClass.SENSITIVE, normalized, blueprint_name)
    return ChangeClassification(RiskClass.STANDARD, normalized, blueprint_name)
