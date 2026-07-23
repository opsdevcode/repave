from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint, load_blueprint, validate_inputs
from repave_engine.gates import GateResult, all_gates_passed, clean_gate_artifacts, run_gates
from repave_engine.pr import PullRequestPlan, create_pull_request, plan_pull_request
from repave_engine.render import (
    RenderedFile,
    RenderResult,
    collect_rendered_files,
    render_blueprint,
)
from repave_engine.settings import GateOverrides, OutputConfig, load_gate_overrides
from repave_engine.target_repo import (
    ModuleRepository,
    publish_to_module_repository,
    resolve_module_repository,
)


@dataclass(frozen=True)
class GenerationResult:
    blueprint: Blueprint
    render: RenderResult
    gates: list[GateResult]
    module_repository: ModuleRepository | None
    pr_plan: PullRequestPlan | None
    pr_message: str
    rendered_files: tuple[RenderedFile, ...] = ()
    dry_run: bool = True


def generate_from_blueprint(
    blueprint: Blueprint,
    values: dict[str, Any],
    *,
    output_config: OutputConfig,
    dry_run: bool = True,
    github_token: str | None = None,
    staging_root: Path | None = None,
    repo_root: Path | None = None,
) -> GenerationResult:
    normalized = validate_inputs(blueprint, values)
    module_name = str(normalized.get("module_name", blueprint.name))
    module_repository = resolve_module_repository(
        module_name=module_name,
        config=output_config,
        name_template=blueprint.output_repo_name_template,
        template_values=normalized,
    )

    if staging_root is None:
        temp_dir = tempfile.TemporaryDirectory(prefix="repave-staging-")
        staging_dir = Path(temp_dir.name)
        owns_staging = True
    else:
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root
        temp_dir = None
        owns_staging = False

    try:
        render_result = render_blueprint(blueprint, normalized, staging_dir)
        gate_overrides = load_gate_overrides(repo_root) if repo_root is not None else None
        gate_results = run_gates(
            render_result.output_dir,
            blueprint.gates,
            blueprint=blueprint,
            gate_overrides=gate_overrides,
        )
        clean_gate_artifacts(render_result.output_dir)

        pr_plan: PullRequestPlan | None = None
        pr_message = "Gates failed; module repository not updated."
        published_repository: ModuleRepository | None = module_repository

        if all_gates_passed(gate_results):
            publish_message = publish_to_module_repository(
                render_result.output_dir,
                module_repository,
                dry_run=dry_run,
            )
            pr_plan = plan_pull_request(
                blueprint_name=blueprint.name,
                blueprint_version=blueprint.version,
                standard_version=blueprint.standard_version,
                title_template=blueprint.output_title_template,
                input_fields=tuple(field.name for field in blueprint.inputs),
                files_root=module_repository.local_path,
                repository=module_repository,
                module_values=normalized,
            )
            if dry_run:
                pr_body = create_pull_request(pr_plan, github_token=None)
                pr_message = f"{publish_message}\n\n{pr_body}"
            else:
                pr_body = create_pull_request(pr_plan, github_token=github_token)
                pr_message = f"{publish_message}\n\n{pr_body}"
        else:
            published_repository = None

        rendered_files = collect_rendered_files(render_result.output_dir) if dry_run else ()
        if dry_run:
            display_output_dir = render_result.output_dir
        elif published_repository is not None:
            display_output_dir = module_repository.local_path
        else:
            display_output_dir = render_result.output_dir
        display_render = RenderResult(output_dir=display_output_dir, values=render_result.values)

        return GenerationResult(
            blueprint=blueprint,
            render=display_render,
            gates=gate_results,
            module_repository=published_repository,
            pr_plan=pr_plan,
            pr_message=pr_message,
            rendered_files=rendered_files,
            dry_run=dry_run,
        )
    finally:
        if owns_staging and temp_dir is not None:
            temp_dir.cleanup()


def generate_from_path(
    blueprint_path: Path,
    values: dict[str, Any],
    *,
    repo_root: Path,
    output_config: OutputConfig,
    dry_run: bool = True,
    github_token: str | None = None,
    staging_root: Path | None = None,
) -> GenerationResult:
    blueprint = load_blueprint(blueprint_path, repo_root)
    return generate_from_blueprint(
        blueprint,
        values,
        output_config=output_config,
        dry_run=dry_run,
        github_token=github_token,
        staging_root=staging_root,
        repo_root=repo_root,
    )
