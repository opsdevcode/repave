from __future__ import annotations

import argparse
import json
from pathlib import Path

import repave_engine.cli as _cli
from repave_engine.blueprint import blueprints_dir, bundles_dir, list_blueprints
from repave_engine.cli._common import _load_output_config_from_args, _parse_inputs
from repave_engine.cli._style import brand, gate_status, heading
from repave_engine.github_auth import resolve_github_access_token


def cmd_generate(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    bundle_name = (getattr(args, "bundle", None) or "").strip()
    blueprint = (getattr(args, "blueprint", None) or "").strip()
    if not bundle_name and not blueprint:
        raise ValueError("Provide --blueprint or --bundle")
    if bundle_name and blueprint:
        raise ValueError("Use only one of --blueprint or --bundle")

    values = _parse_inputs(args.input or [])
    output_config = _load_output_config_from_args(args)
    staging_root = Path(args.staging_root).resolve() if args.staging_root else None

    github_token = resolve_github_access_token(getattr(args, "github_token", None))
    if args.dry_run:
        github_token = None

    bundle_name = (getattr(args, "bundle", None) or "").strip()
    if bundle_name:
        bundle_path = Path(bundle_name)
        if not bundle_path.is_absolute():
            bundle_path = (bundles_dir(repo_root) / bundle_name).resolve()
        bundle_result = _cli.generate_bundle_from_path(
            bundle_path,
            values,
            repo_root=repo_root,
            output_config=output_config,
            dry_run=args.dry_run,
            github_token=github_token,
            staging_root=staging_root,
        )
        print(
            f"{heading('Bundle:')} "
            f"{brand(bundle_result.bundle.name)}@{bundle_result.bundle.version}"
        )
        exit_code = 0
        for member in bundle_result.members:
            print(
                f"\n{heading('Member:')} {member.member_id} ({brand(member.result.blueprint.name)})"
            )
            if member.result.module_repository:
                print(f"  Repository: {member.result.module_repository.web_url}")
            print(f"  {heading('Gates:')}")
            for gate in member.result.gates:
                status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
                print(f"    - [{gate_status(status)}] {gate.name}: {gate.message}")
            failed = [g for g in member.result.gates if not g.passed and not g.skipped]
            if failed:
                exit_code = 1
        return exit_code

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.is_absolute():
        blueprint_path = (repo_root / blueprint_path).resolve()

    result = _cli.generate_from_path(
        blueprint_path,
        values,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=args.dry_run,
        github_token=github_token,
        staging_root=staging_root,
    )

    print(f"{heading('Blueprint:')} {brand(result.blueprint.name)}@{result.blueprint.version}")
    if result.module_repository:
        print(f"{heading('Module repository:')} {result.module_repository.web_url}")
        print(f"{heading('Local path:')} {result.module_repository.local_path}")
    else:
        print(f"{heading('Staging output:')} {result.render.output_dir}")
    print(heading("Gates:"))
    for gate in result.gates:
        status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
        print(f"  - [{gate_status(status)}] {gate.name}: {gate.message}")
    if result.rendered_files:
        print(heading("Generated files:"))
        for rendered in result.rendered_files:
            suffix = " (truncated)" if rendered.truncated else ""
            print(f"  - {rendered.path}{suffix}")
    print(result.pr_message)

    failed = [g for g in result.gates if not g.passed and not g.skipped]
    return 1 if failed else 0


def cmd_list(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    blueprints = list_blueprints(blueprints_dir(repo_root))
    payload = [
        {
            "name": bp.name,
            "version": bp.version,
            "description": bp.description,
            "gates": list(bp.gates),
        }
        for bp in blueprints
    ]
    print(json.dumps(payload, indent=2))
    return 0
