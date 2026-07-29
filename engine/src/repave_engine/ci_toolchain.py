"""Pinned toolchain versions for generated-repo CI.

Values load from ``deploy/local/gate-toolchain-pins.env`` at the repo root so the
installer script and engine agree without duplicating pins.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PINS_FILE = _REPO_ROOT / "deploy" / "local" / "gate-toolchain-pins.env"


def _load_pins() -> dict[str, str]:
    if not _PINS_FILE.is_file():
        raise FileNotFoundError(f"Missing gate toolchain pins: {_PINS_FILE}")
    values: dict[str, str] = {}
    for line in _PINS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        values[key.strip()] = raw.strip()
    return values


_PINS = _load_pins()

TERRAFORM_VERSION = _PINS["TERRAFORM_VERSION"]
TFLINT_VERSION = _PINS["TFLINT_VERSION"]
CHECKOV_VERSION = _PINS["CHECKOV_VERSION"]
CHECKOV_PIP_SPEC = f"checkov=={CHECKOV_VERSION}"
PYTHON_VERSION = _PINS["PYTHON_VERSION"]
HELM_VERSION = _PINS["HELM_VERSION"]
CONFTEST_VERSION = _PINS["CONFTEST_VERSION"]
HADOLINT_VERSION = _PINS["HADOLINT_VERSION"]
GO_VERSION = _PINS["GO_VERSION"]

PINS_FILE = _PINS_FILE

__all__ = [
    "CHECKOV_PIP_SPEC",
    "CHECKOV_VERSION",
    "CONFTEST_VERSION",
    "GO_VERSION",
    "HADOLINT_VERSION",
    "HELM_VERSION",
    "PINS_FILE",
    "PYTHON_VERSION",
    "TERRAFORM_VERSION",
    "TFLINT_VERSION",
]
