from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from repave_engine import __version__, ci_action_pins
from repave_engine.blueprint import artifact_family, list_blueprints
from repave_engine.ci_action_pins import action_pin, action_pins, load_action_pins
from repave_engine.ci_toolchain import INFRACOST_VERSION, TERRAFORM_VERSION
from repave_engine.ci_workflow import (
    build_ci_provenance_block,
    ci_workflow_relpath,
    render_ci_workflow,
    snapshot_gate_config,
)

_USES = re.compile(r"uses:\s*([A-Za-z0-9._/-]+)@([^\s#]+)")
_SHA = re.compile(r"[0-9a-f]{40}")


def test_ci_workflow_path_for_terraform(terraform_blueprint) -> None:
    assert artifact_family(terraform_blueprint.artifact_type) == "terraform"
    assert ci_workflow_relpath(terraform_blueprint) == ".github/workflows/terraform-gates.yml"


def test_ci_workflow_path_for_helm(repo_root) -> None:
    from repave_engine.blueprint import load_blueprint

    blueprint = load_blueprint(repo_root / "blueprints" / "helm-chart-generic", repo_root=repo_root)
    assert ci_workflow_relpath(blueprint) == ".github/workflows/repave-gates.yml"


def test_build_ci_provenance_block_includes_gates(terraform_blueprint) -> None:
    block = build_ci_provenance_block(terraform_blueprint)
    assert "terraform-fmt" in block["gates"]
    assert block["toolchain"]["terraform"] == TERRAFORM_VERSION
    assert block["toolchain"]["infracost"] == INFRACOST_VERSION
    assert block["workflow"] == ".github/workflows/terraform-gates.yml"


def test_render_ci_workflow_includes_repave_gates_command(terraform_blueprint) -> None:
    text = render_ci_workflow(terraform_blueprint)
    assert "repave gates --path ." in text
    assert "hashicorp/setup-terraform" in text
    assert "setup-tflint" in text
    assert "Install Infracost" in text
    assert INFRACOST_VERSION in text
    assert "INFRACOST_API_KEY" in text


def test_action_pins_are_full_commit_shas() -> None:
    for name, pin in action_pins().items():
        assert _SHA.fullmatch(pin.sha), f"{name} pin must be a 40-character commit SHA"
        assert pin.tag, f"{name} pin must record the tag it resolves to"


def test_action_pin_rejects_unknown_repository() -> None:
    with pytest.raises(KeyError, match="unknown action pin"):
        action_pin("acme/setup-nonexistent")


def test_action_pins_load_from_repository_pin_file(repo_root: Path) -> None:
    """Generated CI and this repo's own workflows must not drift apart."""
    on_disk = json.loads((repo_root / ".github" / "action-pins.json").read_text(encoding="utf-8"))
    by_repository = {spec.split("@")[0]: sha for spec, sha in on_disk.items()}
    for repository, pin in action_pins().items():
        assert pin.sha == by_repository[repository]


def test_pins_are_only_needed_to_render_a_workflow(monkeypatch, tmp_path, terraform_blueprint):
    """The published image ships no .github/, so only rendering may require the pin file."""
    monkeypatch.setattr(ci_action_pins, "PINS_FILE", tmp_path / "absent.json")
    ci_action_pins._pins.cache_clear()
    try:
        # Gate config and workflow paths must keep working without pins.
        assert ci_workflow_relpath(terraform_blueprint)
        assert snapshot_gate_config(terraform_blueprint) is not None
        with pytest.raises(FileNotFoundError, match="Missing action pins"):
            render_ci_workflow(terraform_blueprint)
    finally:
        ci_action_pins._pins.cache_clear()


def test_load_action_pins_rejects_missing_required_action(tmp_path: Path) -> None:
    partial = tmp_path / "action-pins.json"
    partial.write_text('{"actions/checkout@v4": "' + "a" * 40 + '"}', encoding="utf-8")
    with pytest.raises(ValueError, match="missing required actions"):
        load_action_pins(partial)


def test_generated_workflows_pin_every_action_by_sha(repo_root: Path) -> None:
    """A mutable tag would let an action owner change what runs in every generated repo."""
    for blueprint in list_blueprints(repo_root / "blueprints"):
        text = render_ci_workflow(blueprint)
        for repository, ref in _USES.findall(text):
            assert _SHA.fullmatch(ref), (
                f"{blueprint.name} workflow references {repository}@{ref}; "
                "pin it by commit SHA in .github/action-pins.json"
            )


def test_snapshot_gate_config_merges_raw(terraform_blueprint) -> None:
    snapshot = snapshot_gate_config(terraform_blueprint)
    assert "checkov" in snapshot
    assert snapshot["checkov"]["config_file"] == ".checkov.yml"


def test_terraform_artifacts_install_the_state_client(terraform_blueprint) -> None:
    """Phase 3 rollout: repave-tf ships with terraform CI, gated on a repo variable."""
    rendered = render_ci_workflow(terraform_blueprint)
    assert "Install repave-tf" in rendered
    assert "if: vars.REPAVE_STATE_URL != ''" in rendered
    assert f'pip install "repave-cli=={__version__}"' in rendered


def test_only_terraform_artifacts_install_the_state_client(repo_root: Path) -> None:
    """Nothing else owns state, so nothing else should carry the client."""
    for blueprint in list_blueprints(repo_root / "blueprints"):
        rendered = render_ci_workflow(blueprint)
        expected = artifact_family(blueprint.artifact_type) == "terraform"
        assert ("repave-cli" in rendered) is expected, blueprint.artifact_type
