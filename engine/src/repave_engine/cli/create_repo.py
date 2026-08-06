"""Thin CLI alias for github-repo-generic provision."""

from __future__ import annotations

import argparse

from repave_engine.cli.generate import cmd_generate


def cmd_create_repo(args: argparse.Namespace) -> int:
    """Map friendly flags onto ``repave generate --blueprint github-repo-generic``."""
    teams = list(getattr(args, "team", None) or [])
    inputs = [
        f"repo_name={args.name}",
        f"create_mode={args.mode}",
        f"visibility={args.visibility}",
        f"team_permission={args.team_permission}",
        f"default_branch={args.default_branch}",
        f"ruleset_profile={args.ruleset_profile}",
    ]
    if args.description:
        inputs.append(f"description={args.description}")
    if args.topics:
        inputs.append(f"topics={args.topics}")
    if teams:
        inputs.append(f"team_slugs={','.join(teams)}")
    membership_source = str(getattr(args, "membership_source_team", "") or "").strip()
    if membership_source:
        inputs.append(f"membership_source_team={membership_source}")
    sync_membership = getattr(args, "sync_team_membership", None)
    if sync_membership is not None:
        inputs.append(f"sync_team_membership={'true' if sync_membership else 'false'}")
    if args.mode == "template":
        if not args.template:
            raise ValueError("--template owner/repo is required when --mode template")
        if "/" not in args.template:
            raise ValueError("--template must be owner/repo")
        owner, repo = args.template.split("/", 1)
        inputs.append(f"template_owner={owner.strip()}")
        inputs.append(f"template_repo={repo.strip()}")

    generate_args = argparse.Namespace(
        repo_root=args.repo_root,
        blueprint="blueprints/github-repo-generic",
        bundle=None,
        input=inputs,
        staging_root=getattr(args, "staging_root", None),
        dry_run=args.dry_run,
        github_token=getattr(args, "github_token", None),
        github_org=getattr(args, "github_org", None),
        modules_root=getattr(args, "modules_root", None),
    )
    return cmd_generate(generate_args)
