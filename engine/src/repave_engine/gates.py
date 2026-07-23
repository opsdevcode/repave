from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GateResult:
    name: str
    passed: bool
    skipped: bool
    message: str


def run_gates(output_dir: Path, gate_names: tuple[str, ...]) -> list[GateResult]:
    results: list[GateResult] = []
    for gate in gate_names:
        runner = _GATE_RUNNERS.get(gate)
        if runner is None:
            results.append(GateResult(gate, False, False, f"Unknown gate: {gate}"))
            continue
        results.append(runner(output_dir))
    return results


def all_gates_passed(results: list[GateResult]) -> bool:
    return all(r.passed or r.skipped for r in results)


_GATE_ARTIFACT_NAMES = (
    ".terraform",
    ".terraform.lock.hcl",
    ".tflint.d",
)


def clean_gate_artifacts(output_dir: Path) -> None:
    for name in _GATE_ARTIFACT_NAMES:
        path = output_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.is_file():
            path.unlink()


def is_gate_artifact_path(relative_path: str) -> bool:
    parts = relative_path.split("/")
    if not parts:
        return False
    if parts[0] in {".terraform", ".tflint.d"}:
        return True
    return relative_path in {".terraform.lock.hcl"}


def _tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _terraform_usable(output_dir: Path) -> bool:
    if not _tool_available("terraform"):
        return False
    result = _run(["terraform", "version"], output_dir)
    return result.returncode == 0


def _gate_terraform_fmt(output_dir: Path) -> GateResult:
    if not _terraform_usable(output_dir):
        return GateResult("terraform-fmt", True, True, "terraform not available; skipped")

    result = _run(["terraform", "fmt", "-check", "-recursive"], output_dir)
    if result.returncode == 0:
        return GateResult("terraform-fmt", True, False, "terraform fmt check passed")
    return GateResult(
        "terraform-fmt",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "terraform fmt check failed",
    )


def _gate_terraform_validate(output_dir: Path) -> GateResult:
    if not _terraform_usable(output_dir):
        return GateResult("terraform-validate", True, True, "terraform not available; skipped")

    init = _run(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-validate",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    validate = _run(["terraform", "validate"], output_dir)
    if validate.returncode == 0:
        return GateResult("terraform-validate", True, False, "terraform validate passed")
    return GateResult(
        "terraform-validate",
        False,
        False,
        validate.stderr.strip() or validate.stdout.strip() or "terraform validate failed",
    )


def _gate_tflint(output_dir: Path) -> GateResult:
    if not _tool_available("tflint"):
        return GateResult("tflint", True, True, "tflint not installed; skipped")

    result = _run(["tflint", "--init"], output_dir)
    if result.returncode != 0:
        return GateResult("tflint", False, False, result.stderr.strip() or "tflint init failed")

    result = _run(["tflint"], output_dir)
    if result.returncode == 0:
        return GateResult("tflint", True, False, "tflint passed")
    return GateResult("tflint", False, False, result.stderr.strip() or "tflint failed")


def _gate_checkov(output_dir: Path) -> GateResult:
    if not _tool_available("checkov"):
        return GateResult("checkov", True, True, "checkov not installed; skipped")

    result = _run(["checkov", "-d", str(output_dir)], output_dir)
    if result.returncode == 0:
        return GateResult("checkov", True, False, "checkov passed")
    return GateResult("checkov", False, False, result.stderr.strip() or "checkov failed")


def _gate_docs_drift(output_dir: Path) -> GateResult:
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

    return GateResult("docs-drift", True, False, "README present and rendered")


_GATE_RUNNERS = {
    "terraform-fmt": _gate_terraform_fmt,
    "terraform-validate": _gate_terraform_validate,
    "tflint": _gate_tflint,
    "checkov": _gate_checkov,
    "docs-drift": _gate_docs_drift,
}
