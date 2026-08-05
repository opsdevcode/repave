"""`repave-tf` entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from repave_cli import __version__
from repave_cli.client import StateClientError
from repave_cli.commands.state import add_state_parser
from repave_cli.config import ConfigError

EXIT_OK = 0
EXIT_ERROR = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="repave-tf",
        description="repave state and execution client",
    )
    parser.add_argument("--version", action="version", version=f"repave-tf {__version__}")
    parser.add_argument(
        "--server",
        default=None,
        help="repave state server base URL (default: $REPAVE_STATE_URL)",
    )
    parser.add_argument(
        "--tenant",
        default=None,
        help="tenant to operate in (default: $REPAVE_STATE_TENANT or 'default')",
    )
    parser.add_argument("--verbose", action="store_true", help="log HTTP and command detail")

    subparsers = parser.add_subparsers(dest="command", required=True)
    add_state_parser(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        return int(args.handler(args))
    except (ConfigError, StateClientError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
