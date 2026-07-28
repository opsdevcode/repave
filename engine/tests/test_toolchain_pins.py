from __future__ import annotations

import re
from pathlib import Path

from repave_engine import ci_toolchain


def _parse_install_script_pins(repo_root: Path) -> dict[str, str]:
    env_path = repo_root / "deploy" / "local" / "gate-toolchain-pins.env"
    text = env_path.read_text(encoding="utf-8")
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        values[key.strip()] = raw.strip()
    return values


def test_ci_toolchain_matches_pins_file() -> None:
    repo_root = ci_toolchain.PINS_FILE.parents[2]
    pins = _parse_install_script_pins(repo_root)
    assert pins["TERRAFORM_VERSION"] == ci_toolchain.TERRAFORM_VERSION
    assert pins["CONFTEST_VERSION"] == ci_toolchain.CONFTEST_VERSION
    assert f"checkov=={pins['CHECKOV_VERSION']}" == ci_toolchain.CHECKOV_PIP_SPEC


def test_install_script_sources_pins_file() -> None:
    repo_root = ci_toolchain.PINS_FILE.parents[2]
    script = (repo_root / "deploy" / "local" / "install-gate-toolchain.sh").read_text(
        encoding="utf-8"
    )
    assert "gate-toolchain-pins.env" in script
    assert re.search(r"source.*gate-toolchain-pins\.env", script)
