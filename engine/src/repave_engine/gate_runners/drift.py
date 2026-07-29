from __future__ import annotations

import re
from pathlib import Path

import jsonschema
import yaml

import repave_engine.gate_runners as _gr
from repave_engine.blueprint import _find_repo_root
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.provenance import validate_provenance_file


def run_docs_drift(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    readme = output_dir / "README.md"
    if not readme.exists():
        return GateResult("docs-drift", False, False, "README.md missing")

    content = readme.read_text(encoding="utf-8")
    placeholders = [match for match in re.findall(r"\{\{[^}]+\}\}", content)]
    if placeholders:
        return GateResult(
            "docs-drift",
            False,
            False,
            f"README contains unresolved template placeholders: {', '.join(placeholders)}",
        )

    if "## Usage" not in content:
        return GateResult("docs-drift", False, False, "README missing Usage section")

    if "## Provenance" not in content:
        return GateResult("docs-drift", False, False, "README missing Provenance section")

    if "repave.yaml" not in content:
        return GateResult("docs-drift", False, False, "README must reference repave.yaml")

    return GateResult("docs-drift", True, False, "README present and rendered")


def run_provenance_drift(ctx: GateContext) -> GateResult:
    blueprint = ctx.blueprint
    if blueprint is None or not blueprint.provenance_file:
        return GateResult("provenance-drift", True, True, "provenance not configured; skipped")

    provenance_path = ctx.output_dir / blueprint.provenance_file
    try:
        try:
            repo_root = _find_repo_root(blueprint.path)
        except FileNotFoundError:
            repo_root = None
        validate_provenance_file(provenance_path, repo_root)
    except FileNotFoundError as exc:
        return GateResult("provenance-drift", False, False, str(exc))
    except jsonschema.ValidationError as exc:
        return GateResult(
            "provenance-drift",
            False,
            False,
            f"Invalid provenance file: {exc.message}",
        )
    except (yaml.YAMLError, ValueError, OSError) as exc:
        return GateResult("provenance-drift", False, False, str(exc))

    return GateResult("provenance-drift", True, False, "Provenance file present and valid")


def _yamllint_config_args(output_dir: Path) -> list[str]:
    config_path = output_dir / ".yamllint"
    if config_path.is_file():
        return ["-c", ".yamllint"]
    return []


def _yamllint_paths(ctx: GateContext) -> list[str]:
    raw = ctx.config("yamllint")
    paths = raw.get("paths")
    if isinstance(paths, list) and paths:
        return [str(path).strip() for path in paths if str(path).strip()]
    if ctx.blueprint is not None and ctx.blueprint.artifact_type == "helm-chart":
        return ["Chart.yaml", "values.yaml"]
    return ["."]


def run_yamllint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not _gr.tool_available("yamllint"):
        return GateResult("yamllint", True, True, "yamllint not installed; skipped")

    config_args = _yamllint_config_args(output_dir)
    targets = _yamllint_paths(ctx)
    result = _gr.run_command(["yamllint", *config_args, *targets], output_dir)
    if result.returncode == 0:
        return GateResult("yamllint", True, False, "yamllint passed")
    return GateResult(
        "yamllint",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "yamllint failed",
    )
