"""Tests for v3 mandatory policy on regulated blueprint families."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.blueprint import InputField, OpaPolicyPack, load_blueprint
from repave_engine.gate_registry import GateContext
from repave_engine.gate_runners import run_opa
from repave_engine.mandatory_policy import (
    DEFAULT_REGULATED_FAMILIES,
    MANDATORY_POLICY_GATE_ID,
    decide_policy_skip,
    evaluate_policy_skip,
)
from repave_engine.policy_selection import normalize_policy_inputs
from repave_engine.v3_foundation import load_v3_foundation_config
from repave_engine.waivers import WaiverStatus


def _write_v3_mandatory(
    root: Path,
    *,
    enabled: bool = True,
    v3_enabled: bool = True,
    families: list[str] | None = None,
    waivers: str = "",
) -> None:
    families_yaml = ""
    if families is not None:
        items = "\n".join(f"      - {name}" for name in families)
        families_yaml = f"    regulated_families:\n{items}\n"
    (root / "repave.config.yaml").write_text(
        "apiVersion: repave.dev/v1\n"
        "v3:\n"
        f"  enabled: {'true' if v3_enabled else 'false'}\n"
        "  mandatory_policy:\n"
        f"    enabled: {'true' if enabled else 'false'}\n"
        f"{families_yaml}"
        "output:\n"
        "  github_org: acme\n"
        "  modules_root: ../mods\n",
        encoding="utf-8",
    )
    if waivers:
        (root / "data").mkdir(exist_ok=True)
        (root / "data" / "waivers.jsonl").write_text(waivers, encoding="utf-8")


def _observability_blueprint(tmp_path: Path):
    return make_blueprint(
        tmp_path,
        artifact_type="observability",
        inputs=(
            InputField(
                "enable_policy",
                "string",
                False,
                default="false",
                enum=("true", "false"),
            ),
        ),
    )


def test_decide_policy_skip_allows_when_v3_off() -> None:
    decision = decide_policy_skip(
        family="observability",
        v3_enabled=False,
        mandatory_policy_enabled=True,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.MISSING,
    )
    assert decision.allowed is True
    assert "v3.enabled" in decision.reason


def test_decide_policy_skip_allows_when_feature_off() -> None:
    decision = decide_policy_skip(
        family="observability",
        v3_enabled=True,
        mandatory_policy_enabled=False,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.MISSING,
    )
    assert decision.allowed is True
    assert "mandatory_policy.enabled" in decision.reason


def test_decide_policy_skip_allows_unlisted_family() -> None:
    decision = decide_policy_skip(
        family="platform",
        v3_enabled=True,
        mandatory_policy_enabled=True,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.MISSING,
    )
    assert decision.allowed is True
    assert "regulated_families" in decision.reason


def test_decide_policy_skip_refuses_observability_without_waiver() -> None:
    decision = decide_policy_skip(
        family="observability",
        v3_enabled=True,
        mandatory_policy_enabled=True,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.MISSING,
    )
    assert decision.allowed is False
    assert "enable_policy: true" in decision.reason
    assert MANDATORY_POLICY_GATE_ID in decision.reason


def test_decide_policy_skip_allows_active_waiver() -> None:
    decision = decide_policy_skip(
        family="observability",
        v3_enabled=True,
        mandatory_policy_enabled=True,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.ACTIVE,
    )
    assert decision.allowed is True
    assert "waiver" in decision.reason


def test_decide_policy_skip_refuses_expired_waiver() -> None:
    decision = decide_policy_skip(
        family="observability",
        v3_enabled=True,
        mandatory_policy_enabled=True,
        regulated_families=DEFAULT_REGULATED_FAMILIES,
        waiver_status=WaiverStatus.EXPIRED,
        waivers_file=Path("data/custom-waivers.jsonl"),
    )
    assert decision.allowed is False
    assert "expired" in decision.reason
    assert "data/custom-waivers.jsonl" in decision.reason


def test_v3_mandatory_policy_opt_in_defaults_families(tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path)
    config = load_v3_foundation_config(tmp_path)
    assert config.mandatory_policy_enabled is True
    assert config.regulated_families == DEFAULT_REGULATED_FAMILIES


def test_v3_mandatory_policy_requires_v3_enabled(tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path, v3_enabled=False)
    with pytest.raises(ValueError, match=r"v3\.mandatory_policy\.enabled"):
        load_v3_foundation_config(tmp_path)


def test_v3_mandatory_policy_rejects_unknown_family(tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path, families=["not-a-family"])
    with pytest.raises(ValueError, match="unknown regulated family"):
        load_v3_foundation_config(tmp_path)


def test_evaluate_policy_skip_refuses_observability(tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path)
    blueprint = _observability_blueprint(tmp_path)
    decision = evaluate_policy_skip(blueprint, tmp_path)
    assert decision.allowed is False
    assert "observability" in decision.reason


def test_evaluate_policy_skip_allows_with_waiver(tmp_path: Path) -> None:
    _write_v3_mandatory(
        tmp_path,
        waivers=(
            '{"waiver_id":"w1","gate_id":"mandatory-policy","expires_at":"2027-01-01T00:00:00Z"}\n'
        ),
    )
    blueprint = _observability_blueprint(tmp_path)
    decision = evaluate_policy_skip(blueprint, tmp_path)
    assert decision.allowed is True


def test_normalize_refuses_enable_policy_false(repo_root: Path, tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path)
    shutil.copytree(repo_root / "policy", tmp_path / "policy")
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    values = {
        "enable_policy": "false",
        "policy_profile": "observability-default",
        "policy_pack_source": "repave-observability-pack",
    }
    with pytest.raises(ValueError, match="enable_policy: true"):
        normalize_policy_inputs(blueprint, values, tmp_path)


def test_normalize_allows_enable_policy_false_when_off(repo_root: Path, tmp_path: Path) -> None:
    _write_v3_mandatory(tmp_path, enabled=False)
    shutil.copytree(repo_root / "policy", tmp_path / "policy")
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    values = {
        "enable_policy": "false",
        "policy_profile": "observability-default",
        "policy_pack_source": "repave-observability-pack",
    }
    assert normalize_policy_inputs(blueprint, values, tmp_path) is None
    assert values["enable_policy"] == "false"


def test_normalize_allows_enable_policy_false_with_waiver(repo_root: Path, tmp_path: Path) -> None:
    _write_v3_mandatory(
        tmp_path,
        waivers=(
            '{"waiver_id":"w1","gate_id":"mandatory-policy","expires_at":"2027-01-01T00:00:00Z"}\n'
        ),
    )
    shutil.copytree(repo_root / "policy", tmp_path / "policy")
    blueprint = load_blueprint(
        repo_root / "blueprints" / "monitors-as-code-generic",
        repo_root=repo_root,
    )
    values = {
        "enable_policy": "false",
        "policy_profile": "observability-default",
        "policy_pack_source": "repave-observability-pack",
    }
    assert normalize_policy_inputs(blueprint, values, tmp_path) is None


def test_run_opa_fails_when_policy_skip_forbidden(tmp_path: Path) -> None:
    from dataclasses import replace

    blueprint = replace(
        _observability_blueprint(tmp_path),
        opa_policies=OpaPolicyPack(
            policies_source="policy/opa/policies",
            policy_version="1.0.0",
        ),
    )
    result = run_opa(GateContext(output_dir=tmp_path, blueprint=blueprint, forbid_policy_skip=True))
    assert result.passed is False
    assert result.skipped is False
    assert "enable_policy: true" in result.message
    assert MANDATORY_POLICY_GATE_ID in result.message


def test_run_opa_skips_when_policy_skip_allowed(tmp_path: Path) -> None:
    from dataclasses import replace

    blueprint = replace(
        _observability_blueprint(tmp_path),
        opa_policies=OpaPolicyPack(
            policies_source="policy/opa/policies",
            policy_version="1.0.0",
        ),
    )
    result = run_opa(GateContext(output_dir=tmp_path, blueprint=blueprint))
    assert result.skipped is True
    assert "not enabled" in result.message
