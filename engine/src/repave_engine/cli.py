from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from repave_engine.auth_context import current_acting_user
from repave_engine.blueprint import _find_repo_root, list_blueprints
from repave_engine.fleet import (
    FleetEntry,
    normalize_repo_url,
    pins_from_repave_file,
    read_fleet,
    register_repo,
    unregister_repo,
)
from repave_engine.fleet_manifests import DEFAULT_NAMESPACE, render_manifests
from repave_engine.fleet_operator_status import (
    kubectl_goldenpathrepo_list,
    parse_kubectl_gpr_list,
    write_operator_status_snapshot,
)
from repave_engine.pipeline import generate_bundle_from_path, generate_from_path
from repave_engine.settings import OutputConfig, load_fleet_config, load_output_config
from repave_engine.upgrade_plan import apply_upgrade, open_upgrade_pull_request, plan_upgrade
from repave_engine.verify import VerifyError, verify_target


def _parse_inputs(raw_inputs: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in raw_inputs:
        if "=" not in item:
            raise ValueError(f"Invalid --input value (expected key=value): {item}")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _load_output_config_from_args(args: argparse.Namespace) -> OutputConfig:
    repo_root = Path(args.repo_root).resolve()
    return load_output_config(
        repo_root,
        github_org=getattr(args, "github_org", None),
        modules_root=getattr(args, "modules_root", None),
    )


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

    github_token = args.github_token or os.environ.get("GITHUB_TOKEN")
    if args.dry_run:
        github_token = None

    bundle_name = (getattr(args, "bundle", None) or "").strip()
    if bundle_name:
        bundle_path = Path(bundle_name)
        if not bundle_path.is_absolute():
            bundle_path = (repo_root / "blueprints" / "bundles" / bundle_name).resolve()
        bundle_result = generate_bundle_from_path(
            bundle_path,
            values,
            repo_root=repo_root,
            output_config=output_config,
            dry_run=args.dry_run,
            github_token=github_token,
            staging_root=staging_root,
        )
        print(f"Bundle: {bundle_result.bundle.name}@{bundle_result.bundle.version}")
        exit_code = 0
        for member in bundle_result.members:
            print(f"\nMember: {member.member_id} ({member.result.blueprint.name})")
            if member.result.module_repository:
                print(f"  Repository: {member.result.module_repository.web_url}")
            print("  Gates:")
            for gate in member.result.gates:
                status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
                print(f"    - [{status}] {gate.name}: {gate.message}")
            failed = [g for g in member.result.gates if not g.passed and not g.skipped]
            if failed:
                exit_code = 1
        return exit_code

    blueprint_path = Path(args.blueprint)
    if not blueprint_path.is_absolute():
        blueprint_path = (repo_root / blueprint_path).resolve()

    result = generate_from_path(
        blueprint_path,
        values,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=args.dry_run,
        github_token=github_token,
        staging_root=staging_root,
    )

    print(f"Blueprint: {result.blueprint.name}@{result.blueprint.version}")
    if result.module_repository:
        print(f"Module repository: {result.module_repository.web_url}")
        print(f"Local path: {result.module_repository.local_path}")
    else:
        print(f"Staging output: {result.render.output_dir}")
    print("Gates:")
    for gate in result.gates:
        status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
        print(f"  - [{status}] {gate.name}: {gate.message}")
    if result.rendered_files:
        print("Generated files:")
        for rendered in result.rendered_files:
            suffix = " (truncated)" if rendered.truncated else ""
            print(f"  - {rendered.path}{suffix}")
    print(result.pr_message)

    failed = [g for g in result.gates if not g.passed and not g.skipped]
    return 1 if failed else 0


def cmd_list(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    blueprints = list_blueprints(repo_root / "blueprints")
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


def _fleet_registry_path(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).resolve()
    config = load_fleet_config(repo_root)
    if config is None:
        raise ValueError(
            "Fleet registry is not configured. Add a fleet block to repave.config.yaml "
            "or set REPAVE_FLEET_FILE."
        )
    if not config.enabled:
        raise ValueError("Fleet registry is disabled (fleet.enabled: false)")
    return config.file


def cmd_register(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)

    pins = {
        "blueprint_name": (args.blueprint or "").strip(),
        "blueprint_version": (args.blueprint_version or "").strip(),
        "standard_source": (args.standard_source or "").strip(),
        "standard_version": (args.standard_version or "").strip(),
    }
    if args.path:
        # Provenance in the repo wins: it is what the operator observes.
        pins.update(pins_from_repave_file(Path(args.path).resolve()))
    if not pins["blueprint_name"]:
        raise ValueError("Provide --path to a checkout with repave.yaml, or --blueprint")

    entry = register_repo(
        registry,
        FleetEntry(
            repo_url=args.repo_url,
            blueprint_name=pins["blueprint_name"],
            blueprint_version=pins["blueprint_version"],
            standard_source=pins["standard_source"],
            standard_version=pins["standard_version"],
            owner=(args.owner or "").strip(),
            registered_by=current_acting_user(),
        ),
        repo_root=Path(args.repo_root).resolve(),
    )
    print(json.dumps(entry.to_dict(), indent=2))
    return 0


def cmd_unregister(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    if not unregister_repo(registry, args.repo_url, repo_root=root):
        print(f"{args.repo_url} is not registered")
        return 1
    print(f"unregistered {normalize_repo_url(args.repo_url)}")
    return 0


def cmd_fleet(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    entries = read_fleet(registry, repo_root=root)

    if args.format == "json":
        print(json.dumps([entry.to_dict() for entry in entries], indent=2))
        return 0

    if not entries:
        print("No repositories registered.")
        return 0
    for entry in entries:
        pin = f"{entry.blueprint_name}@{entry.blueprint_version or '?'}"
        owner = f" owner={entry.owner}" if entry.owner else ""
        print(f"{entry.repo_url}  {pin}{owner}")
    return 0


def cmd_fleet_manifests(args: argparse.Namespace) -> int:
    registry = _fleet_registry_path(args)
    root = Path(args.repo_root).resolve()
    entries = read_fleet(registry, repo_root=root)
    if not entries:
        print("No repositories registered; nothing to render.")
        return 0

    output_dir = Path(args.output).expanduser().resolve()
    rendered = render_manifests(
        entries,
        output_dir,
        namespace=args.namespace,
        enable_remediation=bool(args.enable_remediation),
        prune=bool(args.prune),
        kustomization=bool(args.kustomization),
        gitops_readme=bool(args.gitops_readme),
    )
    for item in rendered:
        print(f"{item.path}  {item.entry.repo_url}")
    print(f"\nRendered {len(rendered)} GoldenPathRepo manifest(s) into {output_dir}")
    if args.kustomization:
        print(f"Kustomization: {output_dir / 'kustomization.yaml'}")
    print(
        f"Apply with: kubectl apply -k {output_dir}"
        if args.kustomization
        else f"Apply with: kubectl apply -f {output_dir}"
    )
    return 0


def cmd_fleet_operator_snapshot(args: argparse.Namespace) -> int:
    try:
        payload = kubectl_goldenpathrepo_list(
            namespace=args.namespace,
            all_namespaces=bool(args.all_namespaces),
        )
    except (RuntimeError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    statuses = parse_kubectl_gpr_list(payload)
    output = Path(args.output).expanduser().resolve()
    write_operator_status_snapshot(output, statuses)
    print(f"Wrote operator status for {len(statuses)} GoldenPathRepo(s) to {output}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    raw_target = args.path.strip()
    repo_root = Path(args.repo_root).resolve()
    try:
        result = verify_target(
            raw_target,
            repo_root,
            blueprint_name=args.blueprint,
            require_run=args.require_run,
            ref=args.ref,
        )
    except VerifyError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result.to_json_dict(), indent=2))
    else:
        print(f"Target: {result.target}")
        if result.remote:
            print("Source: shallow git clone (read-only)")
        print(
            f"Catalog blueprint: {result.catalog_blueprint_name}@{result.catalog_blueprint_version}"
        )
        if not result.provenance_present:
            print("Provenance: (none — gates from catalog only)")
        print("Gates:")
        for gate in result.gates:
            status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
            print(f"  [{status}] {gate.name}: {gate.message}")
        if result.pin_changes:
            print("Pin drift (observed vs catalog):")
            for row in result.pin_changes:
                print(f"  {row.field}: {row.before} → {row.after}")
        else:
            print("Pins: aligned with catalog")

    return 0 if result.ok else 1


def cmd_gates(args: argparse.Namespace) -> int:
    from repave_engine.artifact_blueprint import blueprint_from_repave_file
    from repave_engine.gates import all_gates_passed, run_gates

    repo_path = Path(args.path).resolve()
    repave_file = repo_path / "repave.yaml"
    blueprint = blueprint_from_repave_file(repave_file)

    results = run_gates(repo_path, blueprint.gates, blueprint=blueprint)
    for gate in results:
        status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
        print(f"[{status}] {gate.name}: {gate.message}")

    return 0 if all_gates_passed(results) else 1


def cmd_plan_upgrade(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    target_repo = Path(args.target_repo).resolve()
    staging_root = Path(args.staging_root).resolve() if args.staging_root else None

    result = plan_upgrade(
        target_repo,
        repo_root,
        blueprint_name=args.blueprint,
        staging_root=staging_root,
    )

    if args.format == "json":
        print(json.dumps(result.to_json_dict(), indent=2))
    else:
        print(result.summary)
        if result.added:
            print("Added:")
            for path in result.added:
                print(f"  + {path}")
        if result.modified:
            print("Modified:")
            for path in result.modified:
                print(f"  ~ {path}")
        if result.removed:
            print("Removed:")
            for path in result.removed:
                print(f"  - {path}")

    return 0


def cmd_apply_upgrade(args: argparse.Namespace) -> int:
    if getattr(args, "open_pr", False):
        return _cmd_open_upgrade_pull_request(args)

    repo_root = Path(args.repo_root).resolve()
    target_repo = Path(args.target_repo).resolve()
    staging_root = Path(args.staging_root).resolve() if args.staging_root else None

    if not args.git_branch:
        raise SystemExit("--git-branch is required for apply-upgrade")

    result = apply_upgrade(
        target_repo,
        repo_root,
        blueprint_name=args.blueprint,
        staging_root=staging_root,
        git_branch=args.git_branch,
        commit_message=args.commit_message,
        preserve_local=getattr(args, "preserve_local", False),
    )

    if args.format == "json":
        print(json.dumps(result.to_json_dict(), indent=2))
    else:
        print(result.summary)
        print(f"Branch: {result.git_branch}")
        print(f"Commit: {result.commit_sha}")
        if result.preserved_local:
            print("Preserved local edits (blueprint copies under .repave/upgrade-staging/):")
            for path in result.preserved_local:
                print(f"  * {path}")

    return 0


def _github_token_from_args(args: argparse.Namespace) -> str:
    token = getattr(args, "github_token", None) or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("--open-pr requires GITHUB_TOKEN or --github-token")
    return token


def _cmd_open_upgrade_pull_request(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    target_repo = Path(args.target_repo).resolve()
    staging_root = Path(args.staging_root).resolve() if args.staging_root else None

    if not args.git_branch:
        raise SystemExit("--git-branch is required when opening a pull request")

    result = open_upgrade_pull_request(
        target_repo,
        repo_root,
        github_token=_github_token_from_args(args),
        blueprint_name=args.blueprint,
        staging_root=staging_root,
        git_branch=args.git_branch,
        base_branch=getattr(args, "base_branch", "main") or "main",
        commit_message=args.commit_message,
    )

    if args.format == "json":
        print(json.dumps(result.to_json_dict(), indent=2))
    else:
        print(result.summary)
        print(f"Branch: {result.apply.git_branch}")
        print(f"Commit: {result.apply.commit_sha}")
        print(f"Pull request: {result.pull_request_url}")

    return 0


def _add_upgrade_target_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--target-repo",
        "--path",
        dest="target_repo",
        required=True,
        help="Path to an existing generated module or role repository",
    )
    parser.add_argument(
        "--blueprint",
        default=None,
        help="Override blueprint name (default: read from repave.yaml)",
    )
    parser.add_argument(
        "--staging-root",
        default=None,
        help="Optional directory to retain rendered output for debugging",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format (json is stable for operator integration)",
    )


def _add_upgrade_github_pr_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--open-pr",
        action="store_true",
        help="Push the upgrade branch and open a GitHub pull request (requires token)",
    )
    parser.add_argument(
        "--base-branch",
        default="main",
        help="Base branch for the pull request (default: main)",
    )
    parser.add_argument(
        "--github-token",
        default=None,
        help="GitHub token (defaults to GITHUB_TOKEN when using --open-pr)",
    )


def _add_preserve_local_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--preserve-local",
        action="store_true",
        help=(
            "Do not overwrite modified files; keep local content and write blueprint "
            "copies under .repave/upgrade-staging/ for manual merge"
        ),
    )


def cmd_update(args: argparse.Namespace) -> int:
    if args.dry_run:
        return cmd_plan_upgrade(args)
    if not args.git_branch:
        raise SystemExit("--git-branch is required when applying an upgrade (--no-dry-run)")
    if getattr(args, "open_pr", False):
        return _cmd_open_upgrade_pull_request(args)
    return cmd_apply_upgrade(args)


def cmd_run_worker(args: argparse.Namespace) -> int:
    import time

    from repave_engine.run_queue import RunQueueConfig, build_run_queue
    from repave_engine.run_store import RunStatus
    from repave_engine.settings import load_durability_config

    repo_root = Path(args.repo_root).resolve()
    durability = load_durability_config(repo_root)
    if durability is None:
        raise SystemExit(
            "durability.async_generation must be enabled (or REPAVE_ASYNC_GENERATION=1)"
        )

    output_config = _load_output_config_from_args(args)
    queue = build_run_queue(
        repo_root,
        output_config,
        RunQueueConfig(
            max_concurrent_runs=durability.max_concurrent_runs,
            queue_max_depth=durability.queue_max_depth,
            db_path=durability.runs_db,
            external_workers=True,
        ),
    )
    try:
        if args.run_id:
            record = queue.get(args.run_id)
            if record is None:
                raise SystemExit(f"unknown run_id: {args.run_id}")
            if record.status == RunStatus.QUEUED:
                queue._store.update_status(args.run_id, RunStatus.RUNNING)
            queue.process_run(args.run_id, record.acting_user)
            return 0
        while True:
            if queue.claim_and_process():
                if args.once:
                    return 0
                continue
            if args.once:
                return 0
            time.sleep(args.poll_interval)
    finally:
        queue.close(wait=True)


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from repave_engine.api import create_app

    repo_root = Path(args.repo_root).resolve()
    if args.reload:
        os.environ["REPAVE_SERVE_REPO_ROOT"] = str(repo_root)
        reload_dir = repo_root / "engine" / "src"
        uvicorn.run(
            "repave_engine.api:create_app_for_serve",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=[str(reload_dir)] if reload_dir.is_dir() else None,
        )
    else:
        output_config = _load_output_config_from_args(args)
        app = create_app(repo_root=repo_root, output_config=output_config)
        uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--github-org",
        default=None,
        help="GitHub organization for generated module repositories",
    )
    parser.add_argument(
        "--modules-root",
        default=None,
        help="Directory outside repave where each module gets its own git repository",
    )


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--repo-root",
        default=".",
        help="Path to repave repository root (contains schemas/ and blueprints/)",
    )

    parser = argparse.ArgumentParser(prog="repave", description="repave generation engine")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to repave repository root (contains schemas/ and blueprints/)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser(
        "generate",
        help="Render a blueprint and run gates",
        parents=[common],
    )
    _add_output_options(generate)
    generate.add_argument("--blueprint", help="Blueprint path or name (required unless --bundle)")
    generate.add_argument(
        "--bundle",
        help="Bundle name or path under blueprints/bundles/ (composite golden path)",
    )
    generate.add_argument(
        "--input",
        action="append",
        help="Input value as key=value (repeatable)",
    )
    generate.add_argument(
        "--staging-root",
        default=None,
        help="Optional directory to retain pre-publish staging output for debugging",
    )
    generate.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Plan module repository output without writing local git repos (default: true)",
    )
    generate.add_argument(
        "--github-token",
        default=None,
        help="GitHub token for remote publish (defaults to GITHUB_TOKEN when not dry-run)",
    )
    generate.set_defaults(func=cmd_generate)

    listing = sub.add_parser("list", help="List available blueprints", parents=[common])
    listing.set_defaults(func=cmd_list)

    register = sub.add_parser(
        "register",
        help="Add a generated repository to the fleet registry",
        parents=[common],
    )
    register.add_argument("repo_url", help="Git remote of the repository to govern")
    register.add_argument(
        "--path",
        default=None,
        help="Local checkout to read pins from repave.yaml (preferred over explicit pins)",
    )
    register.add_argument("--blueprint", default=None, help="Blueprint name when --path is absent")
    register.add_argument("--blueprint-version", default=None, help="Blueprint version pin")
    register.add_argument("--standard-source", default=None, help="Standard corpus source")
    register.add_argument("--standard-version", default=None, help="Standard corpus version")
    register.add_argument("--owner", default=None, help="Owning team or user")
    register.set_defaults(func=cmd_register)

    unregister = sub.add_parser(
        "unregister",
        help="Remove a repository from the fleet registry",
        parents=[common],
    )
    unregister.add_argument("repo_url", help="Git remote of the repository to drop")
    unregister.set_defaults(func=cmd_unregister)

    fleet = sub.add_parser(
        "fleet",
        help="List repositories in the fleet registry",
        parents=[common],
    )
    fleet.add_argument("--format", choices=["text", "json"], default="text")
    fleet.set_defaults(func=cmd_fleet)

    fleet_manifests = sub.add_parser(
        "fleet-manifests",
        help="Render GoldenPathRepo manifests for registered repositories",
        parents=[common],
    )
    fleet_manifests.add_argument(
        "--output",
        required=True,
        help="Directory to write one GoldenPathRepo manifest per repository",
    )
    fleet_manifests.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Namespace for the generated resources (default: {DEFAULT_NAMESPACE})",
    )
    fleet_manifests.add_argument(
        "--enable-remediation",
        action="store_true",
        help="Set spec.remediation.enabled on each GoldenPathRepo",
    )
    fleet_manifests.add_argument(
        "--prune",
        action="store_true",
        help="Remove stale *.yaml manifests in --output that are no longer registered",
    )
    fleet_manifests.add_argument(
        "--kustomization",
        action="store_true",
        help="Write kustomization.yaml listing rendered manifests",
    )
    fleet_manifests.add_argument(
        "--gitops-readme",
        action="store_true",
        help="Write README.md with apply and portal status refresh commands",
    )
    fleet_manifests.set_defaults(func=cmd_fleet_manifests)

    fleet_snapshot = sub.add_parser(
        "fleet-operator-snapshot",
        help="Export GoldenPathRepo status JSON for the portal fleet page",
        parents=[common],
    )
    fleet_snapshot.add_argument(
        "--output",
        required=True,
        help="Path to write operator status JSON (fleet.operator_status_file)",
    )
    fleet_snapshot.add_argument(
        "--namespace",
        default=DEFAULT_NAMESPACE,
        help=f"Kubernetes namespace to query (default: {DEFAULT_NAMESPACE})",
    )
    fleet_snapshot.add_argument(
        "--all-namespaces",
        action="store_true",
        help="Query GoldenPathRepo resources in every namespace",
    )
    fleet_snapshot.set_defaults(func=cmd_fleet_operator_snapshot)

    verify_cmd = sub.add_parser(
        "verify",
        help="Run gates and pin-drift checks on an existing repository (no render/publish)",
        parents=[common],
    )
    verify_cmd.add_argument(
        "path",
        help="Local path or git remote URL (https, git@, ssh)",
    )
    verify_cmd.add_argument(
        "--ref",
        default=None,
        help="Git branch or tag when path is a remote URL",
    )
    verify_cmd.add_argument(
        "--blueprint",
        default=None,
        help="Catalog blueprint name when repave.yaml is absent",
    )
    verify_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Report format (default: text)",
    )
    verify_cmd.add_argument(
        "--require-run",
        action="store_true",
        help="Treat skipped gates as failures when tools are missing (dry-run parity)",
    )
    verify_cmd.set_defaults(func=cmd_verify)

    gates_cmd = sub.add_parser(
        "gates",
        help="Run golden-path gates from repave.yaml in a generated repository",
    )
    gates_cmd.add_argument(
        "--path",
        default=".",
        help="Repository root containing repave.yaml (default: current directory)",
    )
    gates_cmd.set_defaults(func=cmd_gates)

    plan = sub.add_parser(
        "plan-upgrade",
        help="Dry-run re-render from repave.yaml inputs and diff against an existing repo",
        parents=[common],
    )
    _add_upgrade_target_options(plan)
    plan.set_defaults(func=cmd_plan_upgrade)

    apply_up = sub.add_parser(
        "apply-upgrade",
        help="Re-render, apply files to a git checkout, and commit on a branch",
        parents=[common],
    )
    _add_upgrade_target_options(apply_up)
    apply_up.add_argument(
        "--git-branch",
        required=True,
        help="Branch to create or reset for the upgrade commit",
    )
    apply_up.add_argument(
        "--commit-message",
        default="chore(repave): apply blueprint upgrade",
        help="Git commit message for the applied upgrade",
    )
    _add_upgrade_github_pr_options(apply_up)
    _add_preserve_local_option(apply_up)
    apply_up.set_defaults(func=cmd_apply_upgrade)

    update = sub.add_parser(
        "update",
        help="Plan or apply a blueprint upgrade for an existing module repository",
        parents=[common],
    )
    _add_upgrade_target_options(update)
    update.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show file diff only (default). Use --no-dry-run to apply on a git branch.",
    )
    update.add_argument(
        "--git-branch",
        default=None,
        help="Branch to create or reset when applying (--no-dry-run)",
    )
    update.add_argument(
        "--commit-message",
        default="chore(repave): apply blueprint upgrade",
        help="Git commit message when applying",
    )
    _add_upgrade_github_pr_options(update)
    _add_preserve_local_option(update)
    update.set_defaults(func=cmd_update)

    run_worker = sub.add_parser(
        "run-worker",
        help="Process async generation runs (Phase 3 external worker / Job mode)",
        parents=[common],
    )
    _add_output_options(run_worker)
    run_worker.add_argument(
        "--run-id",
        default="",
        help="Process a specific run id once (Kubernetes Job target)",
    )
    run_worker.add_argument(
        "--once",
        action="store_true",
        help="Exit after processing one run (or when the queue is empty)",
    )
    run_worker.add_argument(
        "--poll-interval",
        type=float,
        default=5.0,
        help="Seconds to wait when polling the queue (default 5)",
    )
    run_worker.set_defaults(func=cmd_run_worker)

    serve = sub.add_parser("serve", help="Run local web UI/API", parents=[common])
    _add_output_options(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8088)
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Reload Python when engine sources change (local dev)",
    )
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.repo_root == ".":
            args.repo_root = str(_find_repo_root(Path.cwd()))
    except FileNotFoundError:
        pass

    handler = cast(Callable[[argparse.Namespace], int], args.func)
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
