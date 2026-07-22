from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint, load_blueprint, validate_inputs
from repave_engine.gates import GateResult, all_gates_passed, run_gates
from repave_engine.pr import PullRequestPlan, create_pull_request, plan_pull_request
from repave_engine.render import RenderResult, render_blueprint


@dataclass(frozen=True)
class GenerationResult:
    blueprint: Blueprint
    render: RenderResult
    gates: list[GateResult]
    pr_plan: PullRequestPlan | None
    pr_message: str


def generate_from_blueprint(
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    output_root: Path,
    dry_run: bool = True,
    github_token: str | None = None,
) -> GenerationResult:
    normalized = validate_inputs(blueprint, values)
    module_name = normalized.get("module_name", blueprint.name)
    output_dir = output_root / module_name

    render_result = render_blueprint(blueprint, normalized, output_dir)
    gate_results = run_gates(render_result.output_dir, blueprint.gates)

    pr_plan: PullRequestPlan | None = None
    pr_message = "Gates failed; pull request not planned."
    if all_gates_passed(gate_results):
        pr_plan = plan_pull_request(
            module_name=str(module_name),
            blueprint_name=blueprint.name,
            blueprint_version=blueprint.version,
            standard_version=blueprint.standard_version,
            files_root=render_result.output_dir,
        )
        if dry_run:
            pr_message = create_pull_request(pr_plan, github_token=None)
        else:
            pr_message = create_pull_request(pr_plan, github_token=github_token)

    return GenerationResult(
        blueprint=blueprint,
        render=render_result,
        gates=gate_results,
        pr_plan=pr_plan,
        pr_message=pr_message,
    )


def generate_from_path(
    blueprint_path: Path,
    values: dict[str, Any],
    *,
    repo_root: Path,
    output_root: Path,
    dry_run: bool = True,
    github_token: str | None = None,
) -> GenerationResult:
    blueprint = load_blueprint(blueprint_path, repo_root)
    return generate_from_blueprint(
        blueprint,
        values,
        output_root=output_root,
        dry_run=dry_run,
        github_token=github_token,
    )
