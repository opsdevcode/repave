"""Pinned toolchain versions for generated-repo CI.

Values load from ``deploy/local/gate-toolchain-pins.env`` at the repo root so the
installer script, Docker image, and ``repave doctor`` agree without duplicating pins.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
PINS_FILE = _REPO_ROOT / "deploy" / "local" / "gate-toolchain-pins.env"

# Keys required in gate-toolchain-pins.env (single edit point for gate CLIs).
PIN_ENV_KEYS: tuple[str, ...] = (
    "TERRAFORM_VERSION",
    "TFLINT_VERSION",
    "CHECKOV_VERSION",
    "PYTHON_VERSION",
    "HELM_VERSION",
    "CONFTEST_VERSION",
    "HADOLINT_VERSION",
    "GO_VERSION",
    "NODE_VERSION",
    "JAVA_VERSION",
    "DOTNET_VERSION",
    "BUF_VERSION",
    "INFRACOST_VERSION",
    "KUBECTL_VERSION",
    "ACTIONLINT_VERSION",
)


def load_pin_file(path: Path | None = None) -> dict[str, str]:
    pin_path = path or PINS_FILE
    if not pin_path.is_file():
        raise FileNotFoundError(f"Missing gate toolchain pins: {pin_path}")
    values: dict[str, str] = {}
    for line in pin_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        values[key.strip()] = raw.strip()
    missing = [key for key in PIN_ENV_KEYS if key not in values]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"gate-toolchain-pins.env missing required keys: {joined}")
    return values


_PINS = load_pin_file()

TERRAFORM_VERSION = _PINS["TERRAFORM_VERSION"]
TFLINT_VERSION = _PINS["TFLINT_VERSION"]
CHECKOV_VERSION = _PINS["CHECKOV_VERSION"]
CHECKOV_PIP_SPEC = _PINS.get("CHECKOV_PIP_SPEC") or f"checkov=={CHECKOV_VERSION}"
PYTHON_VERSION = _PINS["PYTHON_VERSION"]
HELM_VERSION = _PINS["HELM_VERSION"]
CONFTEST_VERSION = _PINS["CONFTEST_VERSION"]
HADOLINT_VERSION = _PINS["HADOLINT_VERSION"]
GO_VERSION = _PINS["GO_VERSION"]
NODE_VERSION = _PINS["NODE_VERSION"]
BUF_VERSION = _PINS["BUF_VERSION"]
JAVA_VERSION = _PINS["JAVA_VERSION"]
DOTNET_VERSION = _PINS["DOTNET_VERSION"]
INFRACOST_VERSION = _PINS["INFRACOST_VERSION"]
KUBECTL_VERSION = _PINS["KUBECTL_VERSION"]
ACTIONLINT_VERSION = _PINS["ACTIONLINT_VERSION"]

__all__ = [
    "ACTIONLINT_VERSION",
    "BUF_VERSION",
    "CHECKOV_PIP_SPEC",
    "CHECKOV_VERSION",
    "CONFTEST_VERSION",
    "DOTNET_VERSION",
    "GO_VERSION",
    "HADOLINT_VERSION",
    "HELM_VERSION",
    "INFRACOST_VERSION",
    "JAVA_VERSION",
    "KUBECTL_VERSION",
    "NODE_VERSION",
    "PINS_FILE",
    "PIN_ENV_KEYS",
    "PYTHON_VERSION",
    "TERRAFORM_VERSION",
    "TFLINT_VERSION",
    "load_pin_file",
]
