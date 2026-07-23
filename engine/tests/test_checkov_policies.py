from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("checkov")

from checkov.runner_filter import RunnerFilter
from checkov.terraform.runner import Runner

REPAVE_LAYOUT_CHECKS = (
    "CKV2_REPAVE_3",
    "CKV2_REPAVE_4",
    "CKV2_REPAVE_5",
    "CKV2_REPAVE_6",
    "CKV2_REPAVE_7",
)

REPAVE_VERSION_CHECKS = (
    "CKV2_REPAVE_1",
    "CKV2_REPAVE_2",
)

REPAVE_SECURITY_CHECKS = (
    "CKV2_REPAVE_8",
    "CKV2_REPAVE_9",
    "CKV2_REPAVE_10",
    "CKV2_REPAVE_11",
    "CKV2_REPAVE_12",
)

ALL_REPAVE_CHECKS = REPAVE_VERSION_CHECKS + REPAVE_LAYOUT_CHECKS + REPAVE_SECURITY_CHECKS


@pytest.fixture
def policy_pack(repo_root: Path) -> Path:
    return repo_root / "examples" / "checkov" / "policies"


@pytest.fixture
def fixtures_root(repo_root: Path) -> Path:
    return repo_root / "examples" / "checkov" / "tests" / "fixtures"


def run_repave_checks(
    module_dir: Path,
    policy_pack: Path,
    *,
    checks: tuple[str, ...],
) -> tuple[list[str], list[str]]:
    os.environ["REPAVE_CHECKOV_SCAN_ROOT"] = str(module_dir.resolve())
    runner = Runner()
    runner_filter = RunnerFilter(
        framework=["terraform"],
        checks=list(checks),
        all_external=True,
    )
    report = runner.run(
        str(module_dir),
        external_checks_dir=[str(policy_pack)],
        runner_filter=runner_filter,
    )
    failed = sorted({item.check_id for item in report.failed_checks if item.check_id in checks})
    passed = sorted({item.check_id for item in report.passed_checks if item.check_id in checks})
    return failed, passed


def test_compliant_fixture_passes_layout_checks(fixtures_root: Path, policy_pack: Path) -> None:
    module_dir = fixtures_root / "pass"
    failed, passed = run_repave_checks(module_dir, policy_pack, checks=REPAVE_LAYOUT_CHECKS)
    assert not failed
    assert set(REPAVE_LAYOUT_CHECKS).issubset(set(passed))


def test_compliant_fixture_passes_security_checks(fixtures_root: Path, policy_pack: Path) -> None:
    module_dir = fixtures_root / "pass"
    failed, passed = run_repave_checks(module_dir, policy_pack, checks=REPAVE_SECURITY_CHECKS)
    assert not failed
    assert set(REPAVE_SECURITY_CHECKS).issubset(set(passed))


@pytest.mark.parametrize(
    ("fixture_name", "expected_failures"),
    [
        ("fail-no-locals", {"CKV2_REPAVE_3", "CKV2_REPAVE_7"}),
        ("fail-vars-resource", {"CKV2_REPAVE_4", "CKV2_REPAVE_7"}),
        ("fail-main-resource", {"CKV2_REPAVE_5"}),
        ("fail-missing-vars", {"CKV2_REPAVE_6"}),
        ("fail-no-local-refs", {"CKV2_REPAVE_7"}),
    ],
)
def test_fixture_violations_fail_expected_checks(
    fixtures_root: Path,
    policy_pack: Path,
    fixture_name: str,
    expected_failures: set[str],
) -> None:
    module_dir = fixtures_root / fixture_name
    failed, _ = run_repave_checks(module_dir, policy_pack, checks=REPAVE_LAYOUT_CHECKS)
    assert expected_failures.issubset(set(failed))


@pytest.mark.parametrize(
    ("fixture_name", "expected_failures"),
    [
        ("fail-provider-creds", {"CKV2_REPAVE_8", "CKV2_REPAVE_9"}),
        ("fail-secret-default", {"CKV2_REPAVE_9", "CKV2_REPAVE_12"}),
        ("fail-provisioner", {"CKV2_REPAVE_10"}),
        ("fail-sensitive-output", {"CKV2_REPAVE_11"}),
    ],
)
def test_security_fixture_violations_fail_expected_checks(
    fixtures_root: Path,
    policy_pack: Path,
    fixture_name: str,
    expected_failures: set[str],
) -> None:
    module_dir = fixtures_root / fixture_name
    failed, _ = run_repave_checks(module_dir, policy_pack, checks=REPAVE_SECURITY_CHECKS)
    assert expected_failures.issubset(set(failed))


def test_secrets_gate_passes_compliant_fixture(fixtures_root: Path) -> None:
    from repave_engine.gates import _gate_secrets

    result = _gate_secrets(fixtures_root / "pass")
    assert result.passed
    assert not result.skipped


def test_secrets_gate_fails_on_hardcoded_token(fixtures_root: Path) -> None:
    from repave_engine.gates import _gate_secrets

    result = _gate_secrets(fixtures_root / "fail-secret-default")
    assert not result.passed
    assert not result.skipped


def test_rendered_scaffold_passes_repave_checks(
    repo_root: Path,
    terraform_blueprint,
    sample_inputs,
    policy_pack: Path,
    tmp_path: Path,
) -> None:
    from repave_engine.blueprint import validate_inputs
    from repave_engine.render import render_blueprint

    values = validate_inputs(terraform_blueprint, sample_inputs)
    output_dir = tmp_path / "module"
    render_blueprint(terraform_blueprint, values, output_dir)

    failed, passed = run_repave_checks(output_dir, policy_pack, checks=ALL_REPAVE_CHECKS)
    assert not failed
    assert set(REPAVE_LAYOUT_CHECKS + REPAVE_SECURITY_CHECKS).issubset(set(passed))
