"""Mandatory policy on regulated blueprint families (v3)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from repave_engine.blueprint import artifact_family
from repave_engine.waivers import WaiverStatus, evaluate_waiver

if TYPE_CHECKING:
    from repave_engine.blueprint import Blueprint

MANDATORY_POLICY_GATE_ID = "mandatory-policy"

KNOWN_ARTIFACT_FAMILIES: frozenset[str] = frozenset(
    {
        "ansible",
        "app",
        "gitops",
        "helm",
        "observability",
        "platform",
        "policy",
        "terraform",
    }
)

DEFAULT_REGULATED_FAMILIES: frozenset[str] = frozenset(
    {
        "ansible",
        "gitops",
        "helm",
        "observability",
        "policy",
        "terraform",
    }
)


@dataclass(frozen=True)
class PolicySkipDecision:
    allowed: bool
    reason: str


def decide_policy_skip(
    *,
    family: str,
    v3_enabled: bool,
    mandatory_policy_enabled: bool,
    regulated_families: frozenset[str],
    waiver_status: WaiverStatus,
    waivers_file: Path | None = None,
) -> PolicySkipDecision:
    """Pure decision — no I/O. Skip is the enable_policy: false / no-selection path."""
    if not v3_enabled:
        return PolicySkipDecision(True, "v3 foundation is off; set v3.enabled: true")
    if not mandatory_policy_enabled:
        return PolicySkipDecision(
            True,
            "mandatory policy is off; set v3.mandatory_policy.enabled: true",
        )
    if family not in regulated_families:
        return PolicySkipDecision(
            True,
            f"family {family} is not in v3.mandatory_policy.regulated_families",
        )
    waiver_path = waivers_file if waivers_file is not None else Path("data/waivers.jsonl")
    if waiver_status in {WaiverStatus.ACTIVE, WaiverStatus.EXPIRING}:
        return PolicySkipDecision(True, "active mandatory-policy waiver")
    if waiver_status is WaiverStatus.EXPIRED:
        return PolicySkipDecision(
            False,
            (
                f"policy is mandatory on regulated family {family}; "
                f"waiver expired — set enable_policy: true or renew the waiver in "
                f"{waiver_path} (gate_id: {MANDATORY_POLICY_GATE_ID})"
            ),
        )
    return PolicySkipDecision(
        False,
        (
            f"policy is mandatory on regulated family {family}; "
            f"set enable_policy: true, add a waiver in {waiver_path} "
            f"(gate_id: {MANDATORY_POLICY_GATE_ID}), or remove {family} from "
            f"v3.mandatory_policy.regulated_families"
        ),
    )


def evaluate_policy_skip(
    blueprint: Blueprint,
    repo_root: Path,
    *,
    entity_id: str | None = None,
) -> PolicySkipDecision:
    """Load v3 config and waivers, then decide whether a policy skip is allowed."""
    from repave_engine.v3_foundation import load_v3_foundation_config, load_waiver_policy

    config = load_v3_foundation_config(repo_root)
    family = artifact_family(blueprint.artifact_type)
    waiver_status = WaiverStatus.MISSING
    if config.enabled and config.mandatory_policy_enabled:
        policy = load_waiver_policy(repo_root, entity_id=entity_id)
        if policy.enabled:
            evaluation = evaluate_waiver(
                gate_id=MANDATORY_POLICY_GATE_ID,
                waivers=policy.waivers,
                clock=policy.clock,
                entity_id=entity_id,
                warn_days=policy.warn_days,
            )
            waiver_status = evaluation.status
    return decide_policy_skip(
        family=family,
        v3_enabled=config.enabled,
        mandatory_policy_enabled=config.mandatory_policy_enabled,
        regulated_families=config.regulated_families,
        waiver_status=waiver_status,
        waivers_file=config.waivers_file,
    )
