"""Import boundaries for v3 package split (ADR 007).

Until modules physically move into separate repos, these tests enforce that server,
worker, and core packages do not cross forbidden dependency lines.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGINE_SRC = REPO_ROOT / "engine" / "src" / "repave_engine"
PACKAGES = REPO_ROOT / "packages"


def _load_manifest(name: str) -> dict:
    path = PACKAGES / name / "MANIFEST.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _module_path(module: str) -> Path:
    rel = module.removeprefix("repave_engine.").replace(".", "/")
    candidate = ENGINE_SRC / f"{rel}.py"
    if candidate.is_file():
        return candidate
    return ENGINE_SRC / rel / "__init__.py"


def _import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize(
    "package",
    ["repave-core", "repave-server", "repave-worker"],
)
def test_package_modules_exist(package: str) -> None:
    manifest = _load_manifest(package)
    for module in manifest["modules"]:
        path = _module_path(module)
        assert path.is_file(), f"missing module file for {module}: {path}"


@pytest.mark.parametrize(
    ("package", "forbidden"),
    [
        ("repave-core", "forbidden_import_roots"),
        ("repave-server", "forbidden_import_roots"),
        ("repave-worker", "forbidden_import_roots"),
    ],
)
def test_package_import_boundaries(package: str, forbidden: str) -> None:
    manifest = _load_manifest(package)
    blocked = set(manifest[forbidden])
    for module in manifest["modules"]:
        path = _module_path(module)
        if not path.is_file():
            continue
        imported = _import_roots(path)
        for root in imported:
            assert root not in blocked, (
                f"{path.relative_to(REPO_ROOT)} imports forbidden root {root!r} "
                f"for package {package}"
            )
