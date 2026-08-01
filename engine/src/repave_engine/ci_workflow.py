"""GitHub Actions workflow generation for generated repositories (v1.24)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from repave_engine import __version__
from repave_engine.blueprint import Blueprint, artifact_family
from repave_engine.ci_toolchain import (
    CHECKOV_PIP_SPEC,
    CONFTEST_VERSION,
    GO_VERSION,
    HADOLINT_VERSION,
    HELM_VERSION,
    INFRACOST_VERSION,
    PYTHON_VERSION,
    TERRAFORM_VERSION,
    TFLINT_VERSION,
)

_TEMPLATES = Path(__file__).resolve().parent / "templates" / "ci"

_ANSIBLE_GATES = frozenset({"ansible-lint", "ansible-syntax-check", "molecule"})
_HELM_GATES = frozenset({"helm-lint", "helm-template"})
_OBS_GATES = frozenset(
    {
        "promtool",
        "amtool",
        "grafana-dashboard",
        "datadog-dashboard",
        "datadog-monitor",
        "datadog-api-validate",
    }
)

# Prometheus / Alertmanager versions for promtool/amtool on ubuntu-latest (amd64).
_PROMETHEUS_VERSION = "2.51.2"
_ALERTMANAGER_VERSION = "0.27.0"


def ci_workflow_relpath(blueprint: Blueprint) -> str:
    family = artifact_family(blueprint.artifact_type)
    if family == "terraform":
        return ".github/workflows/terraform-gates.yml"
    return ".github/workflows/repave-gates.yml"


def snapshot_gate_config(blueprint: Blueprint) -> dict[str, object]:
    snapshot: dict[str, object] = {}
    for gate_name in blueprint.gates:
        cfg = dict(blueprint.gate_config_for(gate_name))
        if cfg:
            snapshot[gate_name] = cfg
    if blueprint.gate_config_raw:
        for gate_name, raw in blueprint.gate_config_raw.items():
            if not isinstance(raw, dict):
                continue
            existing = snapshot.get(gate_name, {})
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged.update(raw)
            snapshot[gate_name] = merged
    return snapshot


def build_ci_provenance_block(blueprint: Blueprint) -> dict[str, object]:
    toolchain: dict[str, str] = {
        "terraform": TERRAFORM_VERSION,
        "tflint": TFLINT_VERSION,
        "checkov": CHECKOV_PIP_SPEC,
    }
    if "infracost" in blueprint.gates:
        toolchain["infracost"] = INFRACOST_VERSION
    return {
        "workflow": ci_workflow_relpath(blueprint),
        "toolchain": toolchain,
        "gate_config": snapshot_gate_config(blueprint),
        "gates": list(blueprint.gates),
    }


def _gate_needs(gates: tuple[str, ...], *, artifact_type: str = "") -> dict[str, bool]:
    gate_set = set(gates)
    return {
        "needs_terraform": bool(
            gate_set & {"terraform-fmt", "terraform-validate", "terraform-test", "opa", "infracost"}
        ),
        "needs_tflint": "tflint" in gate_set,
        "needs_checkov": bool(gate_set & {"checkov", "secrets"}),
        "needs_infracost": "infracost" in gate_set,
        "needs_yamllint": "yamllint" in gate_set,
        "needs_helm": bool(gate_set & _HELM_GATES),
        "needs_ansible": bool(gate_set & _ANSIBLE_GATES),
        "needs_conftest": "opa" in gate_set,
        "needs_promtool": "promtool" in gate_set,
        "needs_amtool": "amtool" in gate_set,
        "needs_molecule": "molecule" in gate_set,
        "needs_ansible_collections": artifact_type
        in ("ansible-role", "ansible-collection", "ansible-playbook-project"),
        "needs_datadog_api": "datadog-api-validate" in gate_set,
        "needs_hadolint": "dockerfile-lint" in gate_set,
        "needs_python": bool(gate_set & {"python-lint", "python-test"}),
        "needs_go": bool(gate_set & {"go-lint", "go-test"}),
    }


def render_ci_workflow(blueprint: Blueprint) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(default_for_string=False),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("repave-gates.yml.jinja")
    needs = _gate_needs(blueprint.gates, artifact_type=blueprint.artifact_type)
    return template.render(
        engine_version=__version__,
        python_version=PYTHON_VERSION,
        terraform_version=TERRAFORM_VERSION,
        tflint_version=TFLINT_VERSION,
        checkov_spec=CHECKOV_PIP_SPEC,
        helm_version=HELM_VERSION,
        conftest_version=CONFTEST_VERSION,
        hadolint_version=HADOLINT_VERSION,
        go_version=GO_VERSION,
        infracost_version=INFRACOST_VERSION,
        prometheus_version=_PROMETHEUS_VERSION,
        alertmanager_version=_ALERTMANAGER_VERSION,
        **needs,
    )


def write_ci_workflow(output_dir: Path, blueprint: Blueprint) -> Path:
    rel = ci_workflow_relpath(blueprint)
    target = output_dir / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_ci_workflow(blueprint), encoding="utf-8")
    return target
