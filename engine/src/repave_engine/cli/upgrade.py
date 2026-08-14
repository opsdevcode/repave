from __future__ import annotations

import argparse
import json
from pathlib import Path

from repave_engine.cli._common import _github_token_from_args
from repave_engine.cli._style import heading, muted, success
from repave_engine.upgrade_plan import apply_upgrade, open_upgrade_pull_request, plan_upgrade


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
        if result.auto_merge is not None:
            verdict = "allowed" if result.auto_merge.allowed else "review required"
            print(muted(f"Auto-merge: {verdict} — {result.auto_merge.reason}"))
        if result.added:
            print(heading("Added:"))
            for path in result.added:
                print(f"  + {path}")
        if result.modified:
            print(heading("Modified:"))
            for path in result.modified:
                print(f"  ~ {path}")
        if result.removed:
            print(heading("Removed:"))
            for path in result.removed:
                print(f"  - {path}")

    return 0


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
        print(f"{heading('Branch:')} {result.apply.git_branch}")
        print(f"{heading('Commit:')} {result.apply.commit_sha}")
        print(success(f"Pull request: {result.pull_request_url}"))
        if result.merge is not None:
            if result.merge.merged:
                print(success(f"Auto-merge: merged — {result.merge.reason}"))
                if result.merge.merge_commit_sha:
                    print(f"{heading('Merge commit:')} {result.merge.merge_commit_sha}")
            else:
                print(muted(f"Auto-merge: review required — {result.merge.reason}"))

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
        print(f"{heading('Branch:')} {result.git_branch}")
        print(f"{heading('Commit:')} {result.commit_sha}")
        if result.preserved_local:
            print(muted("Preserved local edits (blueprint copies under .repave/upgrade-staging/):"))
            for path in result.preserved_local:
                print(f"  * {path}")

    return 0


def cmd_update(args: argparse.Namespace) -> int:
    if args.dry_run:
        return cmd_plan_upgrade(args)
    if not args.git_branch:
        raise SystemExit("--git-branch is required when applying an upgrade (--no-dry-run)")
    if getattr(args, "open_pr", False):
        return _cmd_open_upgrade_pull_request(args)
    return cmd_apply_upgrade(args)
