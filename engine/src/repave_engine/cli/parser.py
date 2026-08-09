from __future__ import annotations

import argparse

from repave_engine.cli._common import (
    _add_output_options,
    _add_preserve_local_option,
    _add_upgrade_github_pr_options,
    _add_upgrade_target_options,
)
from repave_engine.cli.add import cmd_add
from repave_engine.cli.audit import cmd_audit_query
from repave_engine.cli.create_repo import cmd_create_repo
from repave_engine.cli.doctor import cmd_doctor
from repave_engine.cli.environments import cmd_environments_reclaim
from repave_engine.cli.fleet import (
    cmd_fleet,
    cmd_fleet_manifests,
    cmd_fleet_operator_snapshot,
    cmd_register,
    cmd_unregister,
)
from repave_engine.cli.generate import cmd_generate, cmd_list
from repave_engine.cli.metrics import cmd_metrics_adoption
from repave_engine.cli.repo_import import cmd_import
from repave_engine.cli.serve import cmd_run_worker, cmd_serve
from repave_engine.cli.upgrade import cmd_apply_upgrade, cmd_plan_upgrade, cmd_update
from repave_engine.cli.verify import cmd_gates, cmd_verify
from repave_engine.fleet_manifests import DEFAULT_NAMESPACE


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

    create_repo = sub.add_parser(
        "create-repo",
        help="Provision a GitHub repository (github-repo-generic alias)",
        parents=[common],
    )
    _add_output_options(create_repo)
    create_repo.add_argument("--name", required=True, help="Repository name")
    create_repo.add_argument(
        "--mode",
        choices=("selection", "template"),
        default="selection",
        help="Create mode (default: selection)",
    )
    create_repo.add_argument(
        "--template",
        default=None,
        help="Template repository as owner/repo (required for --mode template)",
    )
    create_repo.add_argument(
        "--visibility",
        choices=("private", "public", "internal"),
        default="private",
        help="Repository visibility (default: private)",
    )
    create_repo.add_argument("--description", default="", help="Repository description")
    create_repo.add_argument("--topics", default="", help="Comma-separated GitHub topics")
    create_repo.add_argument(
        "--team",
        action="append",
        default=[],
        help="Org team slug to grant (repeatable)",
    )
    create_repo.add_argument(
        "--team-permission",
        choices=("pull", "triage", "push", "maintain", "admin"),
        default="push",
        help="Permission for selected teams (default: push)",
    )
    create_repo.add_argument(
        "--default-branch",
        default="main",
        help="Default branch for overlay push (default: main)",
    )
    create_repo.add_argument(
        "--ruleset-profile",
        choices=("none", "default-pr"),
        default="none",
        help="Repository ruleset profile after overlay push (default: none)",
    )
    create_repo.add_argument(
        "--membership-source-team",
        default="",
        help="Existing org team slug to copy members from into --team destinations",
    )
    create_repo.add_argument(
        "--sync-team-membership",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Create missing destination teams and sync members from "
            "--membership-source-team (default: on when source team is set)"
        ),
    )
    create_repo.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Plan without creating the remote repository (default: true)",
    )
    create_repo.add_argument(
        "--github-token",
        default=None,
        help="GitHub token for remote publish (defaults to GITHUB_TOKEN when not dry-run)",
    )
    create_repo.add_argument(
        "--staging-root",
        default=None,
        help="Optional directory to retain pre-publish staging output",
    )
    create_repo.set_defaults(func=cmd_create_repo)

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

    metrics = sub.add_parser("metrics", help="Platform adoption and DX outcome metrics")
    metrics_sub = metrics.add_subparsers(dest="metrics_command", required=True)
    metrics_adoption = metrics_sub.add_parser(
        "adoption",
        help="Show golden-path adoption ratio, funnel, and friction",
        parents=[common],
    )
    metrics_adoption.add_argument("--format", choices=["text", "json"], default="text")
    metrics_adoption.add_argument(
        "--persist",
        action="store_true",
        help="Append a snapshot to the configured snapshot store",
    )
    metrics_adoption.add_argument(
        "--history",
        type=int,
        default=0,
        help="With --format json, include N recent snapshots",
    )
    metrics_adoption.set_defaults(func=cmd_metrics_adoption)

    audit = sub.add_parser("audit", help="Query the generation audit log")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_query = audit_sub.add_parser(
        "query",
        help="Filter audit entries by blueprint, user, outcome, or time range",
        parents=[common],
    )
    audit_query.add_argument("--blueprint", default=None, help="Exact blueprint name")
    audit_query.add_argument("--module-name", default=None, help="Substring match on module name")
    audit_query.add_argument("--repository-url", default=None, help="Substring match on repo URL")
    audit_query.add_argument("--acting-user", default=None, help="Exact acting user id")
    audit_query.add_argument(
        "--gates-outcome",
        default=None,
        choices=["passed", "failed", "empty"],
        help="Gate summary outcome",
    )
    audit_query.add_argument("--since", default=None, help="Inclusive ISO-8601 lower bound")
    audit_query.add_argument("--until", default=None, help="Inclusive ISO-8601 upper bound")
    audit_query.add_argument("--limit", type=int, default=50)
    audit_query.add_argument("--offset", type=int, default=0)
    audit_query.add_argument("--format", choices=["text", "json"], default="text")
    audit_query.set_defaults(func=cmd_audit_query)

    doctor_cmd = sub.add_parser(
        "doctor",
        help="Report gate CLI presence and pin alignment",
        parents=[common],
    )
    doctor_cmd.add_argument(
        "--blueprint",
        default=None,
        help="Blueprint path or name — check only tools required by its gates",
    )
    doctor_cmd.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when a required CLI is missing or mismatched",
    )
    doctor_cmd.add_argument(
        "--all-pins",
        action="store_true",
        help="Check every pin in gate-toolchain-pins.env (includes hadolint/go not in Compose)",
    )
    doctor_cmd.set_defaults(func=cmd_doctor)

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

    environments = sub.add_parser(
        "environments",
        help="Environment registry operations (ADR 003 Phase 3)",
        parents=[common],
    )
    env_sub = environments.add_subparsers(dest="environments_command", required=True)
    reclaim = env_sub.add_parser(
        "reclaim",
        help="Reclaim expired sandbox environments via GitOps decommission PRs",
        parents=[common],
    )
    reclaim.add_argument(
        "--dry-run",
        action="store_true",
        help="List expired environments without opening GitOps pull requests",
    )
    reclaim.add_argument(
        "--stack",
        default="",
        help="Reclaim a single stack by name (must be expired and in auto_reclaim_classes)",
    )
    reclaim.add_argument(
        "--github-token",
        default=None,
        help="GitHub token (defaults to GITHUB_TOKEN)",
    )
    reclaim.add_argument("--format", choices=["text", "json"], default="text")
    reclaim.set_defaults(func=cmd_environments_reclaim)

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

    import_cmd = sub.add_parser(
        "import",
        help="Rearrange an ungoverned repository into a golden path layout and open a PR",
        parents=[common],
    )
    import_cmd.add_argument(
        "path",
        help="Local path or git remote URL (https, git@, ssh) of the repository to import",
    )
    import_cmd.add_argument(
        "--ref",
        default=None,
        help="Git branch or tag when path is a remote URL",
    )
    import_cmd.add_argument(
        "--blueprint",
        default=None,
        help="Golden path blueprint name (default: detect from the repository's marker files)",
    )
    import_cmd.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Report format (default: text)",
    )
    import_cmd.add_argument(
        "--skip-gates",
        action="store_true",
        help="Skip running gates on the reorganized tree (faster preview)",
    )
    import_cmd.add_argument(
        "--open-pr",
        action="store_true",
        help="Apply the plan on a branch, push it, and open a pull request on the source repo",
    )
    import_cmd.add_argument(
        "--git-branch",
        default="",
        help="Branch for the import commits (default: repave/import/<blueprint>-<version>)",
    )
    import_cmd.add_argument(
        "--base-branch",
        default="",
        help="Pull request base branch (default: the source repository's default branch)",
    )
    import_cmd.add_argument(
        "--github-token",
        default=None,
        help="GitHub token for --open-pr (falls back to GITHUB_TOKEN or GitHub App auth)",
    )
    import_cmd.add_argument(
        "--force-clone",
        action="store_true",
        help="Shallow-clone remote repos for preview (default: GitHub trees API for github.com)",
    )
    import_cmd.add_argument(
        "--overrides",
        default=None,
        help="JSON object mapping source paths to destinations, keep-in-place, or quarantine",
    )
    import_cmd.add_argument(
        "--batch-file",
        default=None,
        help="Path to a newline-separated list of repository URLs to plan as a batch",
    )
    import_cmd.add_argument(
        "--org",
        default="",
        help="With --batch-file, also query repositories in this GitHub org",
    )
    import_cmd.add_argument(
        "--topic",
        default="",
        help="With --batch-file, filter the org query by topic",
    )
    import_cmd.add_argument(
        "--language",
        default="",
        help="With --batch-file or --org, filter repositories by GitHub language (for example HCL)",
    )
    import_cmd.add_argument(
        "--pushed-since",
        default="",
        help="With --batch-file or --org, filter repos pushed after YYYY-MM-DD",
    )
    import_cmd.add_argument(
        "--include-archived",
        action="store_true",
        help="With --batch-file or --org, include archived repositories in discovery",
    )
    import_cmd.add_argument(
        "--include-forks",
        action="store_true",
        help="With --batch-file or --org, include fork repositories in discovery",
    )
    import_cmd.set_defaults(func=cmd_import)

    add_cmd = sub.add_parser(
        "add",
        help="Add a second golden-path component to a governed repository",
        parents=[common],
    )
    add_cmd.add_argument(
        "repo",
        help="Local path to the governed repository",
    )
    add_cmd.add_argument(
        "--blueprint",
        required=True,
        help="Blueprint to add (for example helm-chart-generic)",
    )
    add_cmd.add_argument(
        "--component-id",
        default="",
        help="Component id recorded in repave.yaml (default: derived from blueprint)",
    )
    add_cmd.add_argument(
        "--input",
        action="append",
        default=[],
        help="Blueprint input as key=value (repeatable)",
    )
    add_cmd.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files that differ from generated scaffold",
    )
    add_cmd.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; do not modify the repository",
    )
    add_cmd.add_argument(
        "--apply",
        action="store_true",
        help="Apply the add plan locally (creates a git commit on a branch)",
    )
    add_cmd.add_argument(
        "--branch",
        default="",
        help="Git branch for the add commit (default: repave/add/<component>-<version>)",
    )
    add_cmd.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for plan/apply results",
    )
    add_cmd.set_defaults(func=cmd_add)

    gates_cmd = sub.add_parser(
        "gates",
        help="Run golden-path gates from repave.yaml in a generated repository",
    )
    gates_cmd.add_argument(
        "--path",
        default=".",
        help="Repository root containing repave.yaml (default: current directory)",
    )
    gates_cmd.add_argument(
        "--json",
        action="store_true",
        help="Emit results as JSON, for `repave-tf tf apply --gates`",
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
