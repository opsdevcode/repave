from __future__ import annotations

import os
import re
from pathlib import Path

VARIABLE_BLOCK_PATTERN = re.compile(r'^\s*variable\s+"([^"]+)"\s*\{', re.MULTILINE)
RESOURCE_BLOCK_PATTERN = re.compile(r'^\s*resource\s+"', re.MULTILINE)


def candidate_scan_roots() -> list[Path]:
    roots: list[Path] = []
    env_root = os.environ.get("REPAVE_CHECKOV_SCAN_ROOT")
    if env_root:
        roots.append(Path(env_root))
    roots.append(Path.cwd())
    return roots


def resolve_module_root(scanned_file: str) -> Path:
    path = Path(scanned_file)
    if path.is_file():
        start = path.parent
    else:
        filename = path.name
        start = None
        for root in candidate_scan_roots():
            candidate = root / filename
            if candidate.is_file():
                start = root
                break
        if start is None:
            start = Path.cwd()

    current = start.resolve()
    while True:
        if (current / "versions.tf").is_file():
            return current
        if current.parent == current:
            return start.resolve()
        current = current.parent


def module_dir(scanned_file: str) -> Path:
    return resolve_module_root(scanned_file)


def read_module_file(module_root: Path, filename: str) -> str | None:
    path = module_root / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def read_scanned_resource_file(scanned_file: str) -> str | None:
    path = Path(scanned_file)
    if path.is_file():
        return path.read_text(encoding="utf-8")

    filename = path.name
    for root in candidate_scan_roots():
        candidate = root / filename
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def declared_variable_names(module_root: Path) -> set[str]:
    content = read_module_file(module_root, "variables.tf")
    if content is None:
        return set()
    return set(VARIABLE_BLOCK_PATTERN.findall(content))


def file_contains_resource_blocks(content: str) -> bool:
    return RESOURCE_BLOCK_PATTERN.search(content) is not None


def references_shared_locals(content: str) -> bool:
    normalized = content.replace(" ", "")
    return "local.name_prefix" in normalized and "local.common_tags" in normalized
