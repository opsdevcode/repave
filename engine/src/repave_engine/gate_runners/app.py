from __future__ import annotations

from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.gate_registry import GateContext, GateResult


def _ensure_python_project_installed(output_dir: Path) -> None:
    marker = output_dir / ".repave" / "python_dev_installed"
    if marker.is_file():
        return
    import sys

    install = _gr.run_command(
        [sys.executable, "-m", "pip", "install", "-e", ".[dev]"],
        output_dir,
    )
    if install.returncode == 0:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("ok", encoding="utf-8")


def run_dockerfile_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult(
            "dockerfile-lint",
            True,
            True,
            "dockerfile-lint gate not applicable; skipped",
        )

    if not _gr.tool_available("hadolint"):
        return GateResult("dockerfile-lint", True, True, "hadolint not installed; skipped")

    raw = ctx.config("dockerfile-lint")
    dockerfile = str(raw.get("dockerfile", "Dockerfile")).strip() or "Dockerfile"
    path = output_dir / dockerfile
    if not path.is_file():
        return GateResult("dockerfile-lint", True, True, "no Dockerfile found; skipped")

    result = _gr.run_command(["hadolint", dockerfile], output_dir)
    if result.returncode == 0:
        return GateResult("dockerfile-lint", True, False, "hadolint passed")
    detail = result.stderr.strip() or result.stdout.strip() or "hadolint failed"
    return GateResult("dockerfile-lint", False, False, detail)


def run_python_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("python-lint", True, True, "python-lint gate not applicable; skipped")

    if not _gr.tool_available("ruff"):
        return GateResult("python-lint", True, True, "ruff not installed; skipped")

    pyproject = output_dir / "pyproject.toml"
    if not _pyproject_is_valid(pyproject):
        return GateResult("python-lint", True, True, "no pyproject.toml found; skipped")

    _ensure_python_project_installed(output_dir)

    result = _gr.run_command(["ruff", "check", "src", "tests"], output_dir)
    if result.returncode == 0:
        return GateResult("python-lint", True, False, "ruff check passed")
    detail = result.stderr.strip() or result.stdout.strip() or "ruff check failed"
    return GateResult("python-lint", False, False, detail)


def run_python_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("python-test", True, True, "python-test gate not applicable; skipped")

    if not _gr.tool_available("pytest"):
        return GateResult("python-test", True, True, "pytest not installed; skipped")

    raw = ctx.config("python-test")
    test_directory = str(raw.get("test_directory", "tests"))
    pyproject = output_dir / "pyproject.toml"
    if not _pyproject_is_valid(pyproject):
        return GateResult("python-test", True, True, "no pyproject.toml found; skipped")

    test_dir = output_dir / test_directory
    if not _has_python_tests(test_dir):
        return GateResult("python-test", True, True, "no python tests; skipped")

    _ensure_python_project_installed(output_dir)

    result = _gr.run_command(["pytest", test_directory], output_dir)
    if result.returncode == 0:
        return GateResult("python-test", True, False, "pytest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "pytest failed"
    return GateResult("python-test", False, False, detail)


def _go_mod_is_valid(path: Path) -> bool:
    text = path.read_text(encoding="utf-8").strip()
    return text.startswith("module ")


def _pyproject_is_valid(path: Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def _has_python_tests(test_dir: Path) -> bool:
    if not test_dir.is_dir():
        return False
    for candidate in test_dir.glob("test_*.py"):
        if candidate.read_text(encoding="utf-8").strip():
            return True
    return False


def run_go_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("go-lint", True, True, "go-lint gate not applicable; skipped")

    if not _gr.tool_available("go"):
        return GateResult("go-lint", True, True, "go not installed; skipped")

    go_mod = output_dir / "go.mod"
    if not go_mod.is_file() or not _go_mod_is_valid(go_mod):
        return GateResult("go-lint", True, True, "no go.mod found; skipped")

    vet = _gr.run_command(["go", "vet", "./..."], output_dir)
    if vet.returncode != 0:
        detail = vet.stderr.strip() or vet.stdout.strip() or "go vet failed"
        return GateResult("go-lint", False, False, detail)

    fmt = _gr.run_command(["gofmt", "-l", "."], output_dir)
    if fmt.returncode != 0:
        detail = fmt.stderr.strip() or fmt.stdout.strip() or "gofmt failed"
        return GateResult("go-lint", False, False, detail)
    if fmt.stdout.strip():
        detail = "gofmt would change: " + fmt.stdout.strip().replace("\n", ", ")
        return GateResult("go-lint", False, False, detail)

    return GateResult("go-lint", True, False, "go vet and gofmt passed")


def run_go_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "app-service":
        return GateResult("go-test", True, True, "go-test gate not applicable; skipped")

    if not _gr.tool_available("go"):
        return GateResult("go-test", True, True, "go not installed; skipped")

    go_mod = output_dir / "go.mod"
    if not go_mod.is_file() or not _go_mod_is_valid(go_mod):
        return GateResult("go-test", True, True, "no go.mod found; skipped")

    if not any(output_dir.rglob("*_test.go")):
        return GateResult("go-test", True, True, "no Go tests; skipped")

    result = _gr.run_command(["go", "test", "./..."], output_dir)
    if result.returncode == 0:
        return GateResult("go-test", True, False, "go test passed")
    detail = result.stderr.strip() or result.stdout.strip() or "go test failed"
    return GateResult("go-test", False, False, detail)
