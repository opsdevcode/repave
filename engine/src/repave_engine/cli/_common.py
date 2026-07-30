from __future__ import annotations

import argparse
import os
from pathlib import Path

from repave_engine.settings import (
    OutputConfig,
    load_audit_config,
    load_fleet_config,
    load_output_config,
)


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


def _audit_file(args: argparse.Namespace) -> Path:
    root = Path(args.repo_root).resolve()
    audit_cfg = load_audit_config(root)
    if audit_cfg is None or not audit_cfg.enabled:
        raise ValueError("Audit is not enabled (set audit.enabled in repave.config.yaml)")
    return audit_cfg.file


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


def _github_token_from_args(args: argparse.Namespace) -> str:
    token = getattr(args, "github_token", None) or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("--open-pr requires GITHUB_TOKEN or --github-token")
    return token


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
