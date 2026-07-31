from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_engine.github_auth import resolve_github_access_token
from repave_engine.repo_import import (
    AlreadyGovernedError,
    ImportPlan,
    RepoImportError,
    build_import_plan,
    materialize_import_target,
    open_import_pull_request,
    plan_import,
    record_import,
    suggested_import_branch,
)


def _print_plan(plan: ImportPlan) -> None:
    print(f"Target: {plan.target}")
    if plan.remote:
        print("Source: git clone (temporary)")
    label = "detected" if plan.detected else "requested"
    print(f"Golden path: {plan.blueprint_name}@{plan.blueprint_version} ({label})")
    if plan.detected and plan.candidates:
        top = plan.candidates[0]
        evidence = ", ".join(top.evidence[:4])
        print(f"  {top.percent}% confidence — matched {evidence}")
    print(plan.summary)

    if plan.conflicts:
        print("Conflicts (import blocked):")
        for line in plan.conflicts:
            print(f"  {line}")
        return

    if plan.renames:
        print("Moves (content unchanged):")
        for move in plan.renames:
            print(f"  {move.source} -> {move.destination}  ({move.reason})")
    if plan.scaffold_added:
        print("Added scaffold:")
        for rel in plan.scaffold_added:
            print(f"  + {rel}")
    if plan.unmapped:
        print("Left in place (no rule matched):")
        for rel in plan.unmapped:
            print(f"  = {rel}")
    if plan.scorecard.total:
        print(
            f"Scorecard: {plan.scorecard.passing_before} of {plan.scorecard.total} passing today, "
            f"{plan.scorecard.passing_after} of {plan.scorecard.total} after this PR"
        )
    if plan.gates:
        print("Gates on the reorganized tree:")
        for gate in plan.gates:
            status = "SKIP" if gate.skipped else ("PASS" if gate.passed else "FAIL")
            print(f"  [{status}] {gate.name}: {gate.message}")


def cmd_import(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    raw_target = str(args.path).strip()
    with_gates = not args.skip_gates

    if not args.open_pr:
        try:
            plan = plan_import(
                raw_target,
                repo_root,
                blueprint_name=args.blueprint,
                ref=args.ref,
                with_gates=with_gates,
            )
        except (AlreadyGovernedError, RepoImportError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        if args.format == "json":
            print(json.dumps(plan.to_json_dict(), indent=2))
        else:
            _print_plan(plan)
        return 0 if plan.ok and not plan.is_noop else 1

    token = resolve_github_access_token(args.github_token)
    if not token:
        print(
            "--open-pr requires GITHUB_TOKEN, --github-token, or GitHub App credentials",
            file=sys.stderr,
        )
        return 2

    try:
        with materialize_import_target(raw_target, git_token=token, ref=args.ref) as (
            repo_dir,
            remote,
            display,
        ):
            plan = build_import_plan(
                repo_dir,
                repo_root,
                target=display,
                blueprint_name=args.blueprint,
                remote=remote,
                with_gates=with_gates,
            )
            if not plan.ok or plan.is_noop:
                if args.format == "json":
                    print(json.dumps(plan.to_json_dict(), indent=2))
                else:
                    _print_plan(plan)
                return 1
            result = open_import_pull_request(
                repo_dir,
                plan,
                repo_root,
                github_token=token,
                git_branch=args.git_branch or suggested_import_branch(plan),
                base_branch=args.base_branch or "",
            )
    except (AlreadyGovernedError, RepoImportError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    registered = record_import(repo_root, result)
    if args.format == "json":
        payload = result.to_json_dict()
        payload["fleet_registered"] = registered
        print(json.dumps(payload, indent=2))
    else:
        _print_plan(result.apply.plan)
        print(f"Branch: {result.apply.git_branch}")
        print(
            f"Move commit {result.apply.move_commit_sha[:12]} — "
            f"{result.apply.verified_moves} file(s) verified byte-identical"
        )
        print(f"Scaffold commit {result.apply.scaffold_commit_sha[:12]}")
        draft = " (draft — gates did not pass)" if result.draft else ""
        print(f"Pull request: {result.pull_request_url}{draft}")
        if registered:
            print("Registered in the fleet registry")
    return 0
