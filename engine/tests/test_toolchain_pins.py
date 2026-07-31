from __future__ import annotations

import re
from pathlib import Path

import pytest

from repave_engine import ci_toolchain
from repave_engine.ci_workflow import render_ci_workflow
from repave_engine.doctor import _PIN_BY_TOOL


def _repo_root() -> Path:
    return ci_toolchain.PINS_FILE.parents[2]


def test_ci_toolchain_loads_all_required_pins() -> None:
    pins = ci_toolchain.load_pin_file()
    for key in ci_toolchain.PIN_ENV_KEYS:
        assert pins[key], f"{key} must be non-empty"


@pytest.mark.parametrize("key", ci_toolchain.PIN_ENV_KEYS)
def test_ci_toolchain_module_matches_pins_file(key: str) -> None:
    pins = ci_toolchain.load_pin_file()
    module_value = getattr(ci_toolchain, key)
    assert module_value == pins[key]


def test_checkov_pip_spec_is_exact_pin() -> None:
    pins = ci_toolchain.load_pin_file()
    expected = pins.get("CHECKOV_PIP_SPEC") or f"checkov=={pins['CHECKOV_VERSION']}"
    assert expected == ci_toolchain.CHECKOV_PIP_SPEC
    assert ci_toolchain.CHECKOV_PIP_SPEC.startswith("checkov==")
    assert ci_toolchain.CHECKOV_VERSION in ci_toolchain.CHECKOV_PIP_SPEC


def test_install_script_sources_pins_file() -> None:
    script = (_repo_root() / "deploy/local/install-gate-toolchain.sh").read_text(encoding="utf-8")
    assert "gate-toolchain-pins.env" in script
    assert re.search(r"source.*gate-toolchain-pins\.env", script)
    assert 'CHECKOV_PIP_SPEC="${CHECKOV_PIP_SPEC:-checkov==${CHECKOV_VERSION}}"' in script


def test_doctor_pin_map_matches_ci_toolchain() -> None:
    assert _PIN_BY_TOOL["terraform"] == ci_toolchain.TERRAFORM_VERSION
    assert _PIN_BY_TOOL["tflint"] == ci_toolchain.TFLINT_VERSION
    assert _PIN_BY_TOOL["checkov"] == ci_toolchain.CHECKOV_VERSION
    assert _PIN_BY_TOOL["conftest"] == ci_toolchain.CONFTEST_VERSION
    assert _PIN_BY_TOOL["helm"] == ci_toolchain.HELM_VERSION


def test_render_ci_workflow_embeds_pinned_toolchain(terraform_blueprint, repo_root: Path) -> None:
    from repave_engine.blueprint import load_blueprint

    text = render_ci_workflow(terraform_blueprint)
    assert ci_toolchain.TERRAFORM_VERSION in text
    assert ci_toolchain.TFLINT_VERSION in text
    assert ci_toolchain.CONFTEST_VERSION in text
    assert ci_toolchain.CHECKOV_PIP_SPEC in text

    helm_blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root
    )
    helm_text = render_ci_workflow(helm_blueprint)
    assert ci_toolchain.HELM_VERSION in helm_text


def test_load_pin_file_rejects_missing_required_key(tmp_path: Path) -> None:
    partial = tmp_path / "pins.env"
    partial.write_text("TERRAFORM_VERSION=1.0.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing required keys"):
        ci_toolchain.load_pin_file(partial)
