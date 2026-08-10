from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from repave_engine.cli._style import muted, success
from repave_engine.environment_reclaim import (
    EnvironmentReclaimError,
    reclaim_expired_environments,
)
from repave_engine.github_auth import resolve_github_access_token
from repave_engine.settings import EnvironmentVendingConfig, load_environment_vending_config


def _environment_vending_config(
    args: argparse.Namespace,
) -> tuple[Path, EnvironmentVendingConfig]:
    repo_root = Path(args.repo_root).resolve()
    config = load_environment_vending_config(repo_root)
    if config is None:
        raise SystemExit(
            "environment_vending is not enabled; set environment_vending.enabled in "
            "repave.config.yaml or REPAVE_ENVIRONMENT_VENDING=1"
        )
    return repo_root, config


def cmd_environments_reclaim(args: argparse.Namespace) -> int:
    repo_root, config = _environment_vending_config(args)
    github_token: str | None
    if args.dry_run:
        github_token = None
    else:
        github_token = resolve_github_access_token(getattr(args, "github_token", None))
        if not github_token:
            print(
                "GITHUB_TOKEN is required unless --dry-run is set; "
                "export GITHUB_TOKEN or pass --github-token",
                file=sys.stderr,
            )
            return 1
    try:
        summary = reclaim_expired_environments(
            repo_root=repo_root,
            config=config,
            github_token=github_token,
            dry_run=args.dry_run,
            stack_name=(args.stack or "").strip() or None,
        )
    except EnvironmentReclaimError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(summary.to_public_dict(), indent=2))
        return 0

    if not summary.results:
        print(muted("No expired environments eligible for auto-reclaim."))
        return 0

    for item in summary.results:
        if item.mode == "registry_finalize" and item.reclaimed:
            state = success("finalized")
        elif item.reclaimed:
            state = success("reclaimed")
        elif item.skipped:
            state = "skipped"
        elif item.mode == "decommission_review":
            state = "decommission-review"
        else:
            state = "dry-run"
        print(f"{item.stack_name}: {state} — {item.detail}")
    return 0
