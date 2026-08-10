from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from repave_engine.cli._style import brand, error, heading, success
from repave_engine.pr_conventions import add_pull_request_title, load_pull_request_conventions
from repave_engine.repo_add import (
    AddPlan,
    NotGovernedError,
    RepoAddError,
    apply_add,
    plan_add,
    record_add_from_env,
    suggested_add_branch,
)


def _print_plan(plan: AddPlan) -> None:
    print(f"Target: {plan.target}")
    print(f"Component: {plan.component_id}")
    print(f"{heading('Blueprint:')} {brand(plan.blueprint_name)}@{plan.blueprint_version}")
    print(plan.summary)
    if plan.conflicts:
        print(error("Conflicts (add blocked):"))
        for line in plan.conflicts:
            print(f"  {line}")
        return
    if plan.files_added:
        print(heading("Files to add:"))
        for rel in plan.files_added:
            print(f"  + {rel}")
    if plan.files_overwritten:
        print(heading("Files to overwrite (--force):"))
        for rel in plan.files_overwritten:
            print(f"  ~ {rel}")


def cmd_add(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    target = str(Path(args.repo).expanduser().resolve())

    values: dict[str, str] = {}
    if args.input:
        for item in args.input:
            if "=" not in item:
                print(f"invalid --input (expected key=value): {item}", file=sys.stderr)
                return 2
            key, value = item.split("=", 1)
            values[key.strip()] = value.strip()

    try:
        plan = plan_add(
            target,
            repo_root,
            blueprint_name=args.blueprint,
            values=values or None,
            component_id=args.component_id,
            force=args.force,
        )
    except NotGovernedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except RepoAddError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(plan.to_json_dict(), indent=2))
    else:
        _print_plan(plan)

    if args.dry_run or not args.apply:
        return 0 if plan.ok else 1

    if not plan.ok:
        return 1

    conventions = load_pull_request_conventions(repo_root)
    git_branch = args.branch or suggested_add_branch(
        plan, conventions_prefix=conventions.branch_prefix_add
    )
    commit_message = add_pull_request_title(plan.blueprint_name, plan.component_id)

    with tempfile.TemporaryDirectory(prefix="repave-add-apply-") as temp_name:
        staging = Path(temp_name)
        try:
            result = apply_add(
                Path(target),
                repo_root,
                plan,
                staging_dir=staging,
                git_branch=git_branch,
                commit_message=commit_message,
            )
        except RepoAddError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    record_add_from_env(repo_root, result)
    if args.format == "json":
        print(
            json.dumps(
                {
                    "git_branch": result.git_branch,
                    "commit_sha": result.commit_sha,
                    "plan": plan.to_json_dict(),
                },
                indent=2,
            )
        )
    else:
        print(success(f"Committed on branch {result.git_branch} ({result.commit_sha[:12]})"))
    return 0
