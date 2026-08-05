"""The client must never gain database access (ADR 004, credential boundary).

Direct database access from clients is the failure mode the state store exists to
avoid: it would put a DSN on every engineer's laptop and in every CI runner. These
tests fail loudly if an import sneaks in.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "repave_cli"

FORBIDDEN_MODULES = {
    "psycopg",
    "psycopg2",
    "sqlite3",
    "sqlalchemy",
    "asyncpg",
    "repave_engine.sql_store",
    "repave_engine.statestore",
    "repave_engine.api_state",
    "repave_engine.api",
    "fastapi",
    "uvicorn",
    "starlette",
}


def _module_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _source_files() -> list[Path]:
    return sorted(SOURCE_ROOT.rglob("*.py"))


def test_source_tree_is_not_empty() -> None:
    assert _source_files(), f"no sources under {SOURCE_ROOT}"


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_database_or_server_imports(path: Path) -> None:
    imported = _module_names(path)
    for name in imported:
        root = name.split(".")[0]
        assert name not in FORBIDDEN_MODULES, f"{path.name} imports forbidden module {name}"
        assert root not in FORBIDDEN_MODULES, f"{path.name} imports forbidden package {root}"


def test_importing_the_cli_does_not_load_fastapi() -> None:
    """The engine's server extra must stay optional for client installs."""
    for module in [name for name in sys.modules if name.startswith(("repave_cli", "fastapi"))]:
        sys.modules.pop(module, None)

    import repave_cli.main  # noqa: F401

    assert "fastapi" not in sys.modules
    assert "psycopg" not in sys.modules


def test_client_reaches_the_store_only_over_http() -> None:
    from repave_cli import client

    assert client.httpx is not None
    assert not hasattr(client, "connect")
