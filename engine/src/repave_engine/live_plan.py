"""Governed terraform plan against live state (ADR 003 Phase 2).

Plan JSON is ephemeral: summarized for the run result, then deleted. It never
enters provenance, audit records, or persisted run payloads.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.gate_runners import _core as _gr
from repave_engine.gate_toolchain import tool_available
from repave_engine.gates import GateResult
from repave_engine.git_clone import CloneError
from repave_engine.upgrade_api import UpgradeTargetError, materialize_upgrade_target

logger = logging.getLogger(__name__)

LIVE_PLAN_BLUEPRINT_SENTINEL = "live-plan"


@dataclass(frozen=True)
class LivePlanSummary:
    """Safe public summary — never includes raw plan JSON."""

    entity_id: str
    target: str
    plan_ok: bool
    opa_passed: bool
    opa_skipped: bool
    opa_detail: str
    resource_add: int
    resource_change: int
    resource_destroy: int
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "kind": "live_plan",
            "entity_id": self.entity_id,
            "target": self.target,
            "plan_ok": self.plan_ok,
            "opa_passed": self.opa_passed,
            "opa_skipped": self.opa_skipped,
            "opa_detail": self.opa_detail,
            "resource_add": self.resource_add,
            "resource_change": self.resource_change,
            "resource_destroy": self.resource_destroy,
            "detail": self.detail,
            "gates_outcome": (
                "passed" if self.plan_ok and (self.opa_passed or self.opa_skipped) else "failed"
            ),
        }


def summarize_plan_json(payload: Any) -> tuple[int, int, int]:
    """Return (add, change, destroy) counts from terraform show -json output."""
    if not isinstance(payload, dict):
        return 0, 0, 0
    changes = payload.get("resource_changes")
    if not isinstance(changes, list):
        return 0, 0, 0
    add = change = destroy = 0
    for item in changes:
        if not isinstance(item, dict):
            continue
        change_block = item.get("change")
        if not isinstance(change_block, dict):
            continue
        actions = change_block.get("actions")
        if not isinstance(actions, list):
            continue
        normalized = {str(a).lower() for a in actions}
        if "create" in normalized:
            add += 1
        if "update" in normalized or "replace" in normalized:
            change += 1
        if "delete" in normalized:
            destroy += 1
    return add, change, destroy


def terraform_live_plan_json(
    output_dir: Path,
    plan_subdir: str,
    *,
    use_backend: bool = True,
) -> Path | None:
    """Run terraform init/plan/show against the module at output_dir.

    When use_backend is True, init uses the module's configured backend (live state).
    Plan binary and JSON are written under plan_subdir for ephemeral evaluation.
    """
    if not _gr.terraform_usable(output_dir):
        return None
    work = output_dir / plan_subdir
    work.mkdir(parents=True, exist_ok=True)
    plan_binary = work / "tfplan"
    plan_json = work / "tfplan.json"

    init_cmd = ["terraform", "init", "-input=false"]
    if not use_backend:
        init_cmd.append("-backend=false")
    init = _gr.run_command(init_cmd, output_dir)
    if init.returncode != 0:
        logger.info("live plan terraform init failed: %s", (init.stderr or "")[:200])
        return None

    plan = _gr.run_command(
        [
            "terraform",
            "plan",
            "-out",
            str(plan_binary.relative_to(output_dir)),
            "-input=false",
            "-lock=false",
        ],
        output_dir,
    )
    if plan.returncode != 0:
        logger.info("live plan terraform plan failed: %s", (plan.stderr or "")[:200])
        return None

    show = _gr.run_command(
        ["terraform", "show", "-json", str(plan_binary.relative_to(output_dir))],
        output_dir,
    )
    if show.returncode != 0:
        return None
    plan_json.write_text(show.stdout, encoding="utf-8")
    return plan_json


def run_conftest_on_plan(
    plan_json: Path,
    policies_dir: Path,
    *,
    cwd: Path,
) -> GateResult:
    if not policies_dir.is_dir():
        return GateResult(
            "opa",
            True,
            True,
            f"opa policies directory missing: {policies_dir}; skipped",
        )
    if not tool_available("conftest"):
        return GateResult("opa", True, True, "conftest not installed; skipped")
    result = _gr.run_command(
        ["conftest", "test", str(plan_json), "-p", str(policies_dir)],
        cwd,
    )
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    return GateResult("opa", False, False, detail)


def _scrub_plan_artifacts(plan_dir: Path) -> None:
    if not plan_dir.is_dir():
        return
    try:
        shutil.rmtree(plan_dir)
    except OSError as exc:
        logger.warning("failed to scrub live plan artifacts at %s: %s", plan_dir, exc)


def run_live_plan(
    *,
    repo_root: Path,
    target: str,
    entity_id: str,
    policies_dir: str = "policy/opa/policies",
    plan_subdir: str = ".repave/live-plan",
    use_backend: bool = True,
) -> LivePlanSummary:
    """Materialize target, run live plan + OPA, return summary; scrub plan files."""
    try:
        with materialize_upgrade_target(target) as checkout:
            return _run_live_plan_at(
                checkout=checkout,
                repo_root=repo_root,
                target=target,
                entity_id=entity_id,
                policies_dir=policies_dir,
                plan_subdir=plan_subdir,
                use_backend=use_backend,
            )
    except (UpgradeTargetError, CloneError) as exc:
        return LivePlanSummary(
            entity_id=entity_id,
            target=target,
            plan_ok=False,
            opa_passed=False,
            opa_skipped=True,
            opa_detail="",
            resource_add=0,
            resource_change=0,
            resource_destroy=0,
            detail=str(exc),
        )


def _run_live_plan_at(
    *,
    checkout: Path,
    repo_root: Path,
    target: str,
    entity_id: str,
    policies_dir: str,
    plan_subdir: str,
    use_backend: bool,
) -> LivePlanSummary:
    plan_dir = checkout / plan_subdir
    plan_json: Path | None = None
    try:
        plan_json = terraform_live_plan_json(
            checkout,
            plan_subdir,
            use_backend=use_backend,
        )
        if plan_json is None:
            return LivePlanSummary(
                entity_id=entity_id,
                target=target,
                plan_ok=False,
                opa_passed=False,
                opa_skipped=True,
                opa_detail="",
                resource_add=0,
                resource_change=0,
                resource_destroy=0,
                detail="terraform init/plan against live state failed",
            )
        try:
            payload = json.loads(plan_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return LivePlanSummary(
                entity_id=entity_id,
                target=target,
                plan_ok=False,
                opa_passed=False,
                opa_skipped=True,
                opa_detail="",
                resource_add=0,
                resource_change=0,
                resource_destroy=0,
                detail="plan JSON could not be parsed",
            )
        add, change, destroy = summarize_plan_json(payload)

        policies = checkout / policies_dir
        if not policies.is_dir():
            policies = repo_root / policies_dir
        opa = run_conftest_on_plan(plan_json, policies, cwd=checkout)
        return LivePlanSummary(
            entity_id=entity_id,
            target=target,
            plan_ok=True,
            opa_passed=opa.passed,
            opa_skipped=opa.skipped,
            opa_detail=opa.message,
            resource_add=add,
            resource_change=change,
            resource_destroy=destroy,
            detail=(
                f"Plan: +{add} ~{change} -{destroy}; "
                f"OPA {'skipped' if opa.skipped else ('passed' if opa.passed else 'failed')}"
            ),
        )
    finally:
        _scrub_plan_artifacts(plan_dir)


def is_live_plan_run(payload: dict[str, Any]) -> bool:
    return str(payload.get("kind", "")).strip() == "live_plan"
