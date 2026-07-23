from __future__ import annotations

import fnmatch
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from repave_engine.blueprint import Blueprint
    from repave_engine.settings import GateOverrides

GateRunner = Callable[["GateContext"], "GateResult"]

_GATES: dict[str, GateSpec] = {}
_PLUGINS_LOADED = False
_BUILTINS_LOADED = False

# Artifact paths keyed by artifact type (in addition to per-gate paths).
_ARTIFACT_TYPE_PATHS: dict[str, tuple[str, ...]] = {
    "terraform-module": (
        ".terraform",
        ".terraform.lock.hcl",
        ".tflint.d",
    ),
    "ansible-role": (
        ".ansible",
        ".molecule",
        "*.retry",
    ),
}


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    skipped: bool
    message: str


@dataclass(frozen=True)
class GateContext:
    output_dir: Path
    blueprint: Blueprint | None = None
    gate_overrides: GateOverrides | None = None

    def config(self, gate_name: str) -> Mapping[str, Any]:
        if self.blueprint is None:
            return {}
        return self.blueprint.gate_config_for(gate_name)


@dataclass(frozen=True)
class GateSpec:
    name: str
    runner: GateRunner
    artifact_types: frozenset[str] = frozenset({"terraform-module"})
    artifact_paths: tuple[str, ...] = ()


class GateRegistryError(ValueError):
    pass


def register_gate(spec: GateSpec) -> None:
    if spec.name in _GATES:
        raise GateRegistryError(f"Gate already registered: {spec.name}")
    _GATES[spec.name] = spec


def unregister_gate(name: str) -> None:
    _GATES.pop(name, None)


def get_gate(name: str) -> GateSpec | None:
    ensure_gates_loaded()
    return _GATES.get(name)


def registered_gate_names() -> frozenset[str]:
    ensure_gates_loaded()
    return frozenset(_GATES)


def artifact_paths_for_type(artifact_type: str) -> tuple[str, ...]:
    ensure_gates_loaded()
    paths: set[str] = set(_ARTIFACT_TYPE_PATHS.get(artifact_type, ()))
    for spec in _GATES.values():
        if artifact_type in spec.artifact_types:
            paths.update(spec.artifact_paths)
    return tuple(sorted(paths))


def is_gate_artifact_path(relative_path: str, *, artifact_type: str = "terraform-module") -> bool:
    for pattern in artifact_paths_for_type(artifact_type):
        if _path_matches_artifact_pattern(relative_path, pattern):
            return True
    return False


def _path_matches_artifact_pattern(relative_path: str, pattern: str) -> bool:
    if pattern.startswith("*."):
        suffix = pattern[1:]
        return relative_path.split("/")[-1].endswith(suffix)
    if pattern.startswith("."):
        parts = relative_path.split("/")
        if not parts:
            return False
        if parts[0] == pattern:
            return True
        return relative_path.startswith(f"{pattern}/")
    if "*" in pattern or "?" in pattern:
        return fnmatch.fnmatch(relative_path, pattern)
    return relative_path == pattern


def load_gate_plugins() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return
    try:
        from importlib.metadata import entry_points
    except ImportError:
        _PLUGINS_LOADED = True
        return

    try:
        eps = entry_points(group="repave.gates")
    except TypeError:
        eps = entry_points().get("repave.gates", [])

    for entry_point in eps:
        entry_point.load()

    _PLUGINS_LOADED = True


def ensure_gates_loaded() -> None:
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    from repave_engine import gate_builtin  # noqa: F401

    load_gate_plugins()
    _BUILTINS_LOADED = True


def reset_gate_registry_for_tests() -> None:
    """Clear registry state and reload built-in gate registrations."""
    import importlib
    import sys

    global _BUILTINS_LOADED, _PLUGINS_LOADED
    _GATES.clear()
    _BUILTINS_LOADED = False
    _PLUGINS_LOADED = False
    if "repave_engine.gate_builtin" in sys.modules:
        import repave_engine.gate_builtin as gate_builtin

        importlib.reload(gate_builtin)
    else:
        from repave_engine import gate_builtin
    _BUILTINS_LOADED = True
