from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import cast

from repave_engine.blueprint import _find_repo_root
from repave_engine.cli._common import _parse_inputs
from repave_engine.cli.audit import cmd_audit_query
from repave_engine.cli.create_repo import cmd_create_repo
from repave_engine.cli.doctor import cmd_doctor
from repave_engine.cli.fleet import (
    cmd_fleet,
    cmd_fleet_manifests,
    cmd_fleet_operator_snapshot,
    cmd_register,
    cmd_unregister,
)
from repave_engine.cli.generate import cmd_generate, cmd_list
from repave_engine.cli.parser import build_parser
from repave_engine.cli.serve import cmd_run_worker, cmd_serve
from repave_engine.cli.upgrade import cmd_apply_upgrade, cmd_plan_upgrade, cmd_update
from repave_engine.cli.verify import cmd_gates, cmd_verify
from repave_engine.pipeline import generate_bundle_from_path, generate_from_path

__all__ = [
    "_parse_inputs",
    "build_parser",
    "cmd_apply_upgrade",
    "cmd_audit_query",
    "cmd_create_repo",
    "cmd_doctor",
    "cmd_fleet",
    "cmd_fleet_manifests",
    "cmd_fleet_operator_snapshot",
    "cmd_gates",
    "cmd_generate",
    "cmd_list",
    "cmd_plan_upgrade",
    "cmd_register",
    "cmd_run_worker",
    "cmd_serve",
    "cmd_unregister",
    "cmd_update",
    "cmd_verify",
    "generate_bundle_from_path",
    "generate_from_path",
    "main",
]


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
