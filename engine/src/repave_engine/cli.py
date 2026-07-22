from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

from repave_engine.blueprint import _find_repo_root, list_blueprints
from repave_engine.pipeline import generate_from_path
from repave_engine.settings import OutputConfig, load_output_config


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
    blueprint_path = Path(args.blueprint)
    if not blueprint_path.is_absolute():
        blueprint_path = (repo_root / blueprint_path).resolve()

    values = _parse_inputs(args.input or [])
    output_config = _load_output_config_from_args(args)
    staging_root = Path(args.staging_root).resolve() if args.staging_root else None

    result = generate_from_path(
        blueprint_path,
        values,
        repo_root=repo_root,
        output_config=output_config,
        dry_run=args.dry_run,
        github_token=args.github_token,
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


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from repave_engine.api import create_app

    repo_root = Path(args.repo_root).resolve()
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
    generate.add_argument("--blueprint", required=True, help="Blueprint path or name")
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
    generate.add_argument("--github-token", default=None, help="GitHub token for remote output")
    generate.set_defaults(func=cmd_generate)

    listing = sub.add_parser("list", help="List available blueprints", parents=[common])
    listing.set_defaults(func=cmd_list)

    serve = sub.add_parser("serve", help="Run local web UI/API", parents=[common])
    _add_output_options(serve)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8088)
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
