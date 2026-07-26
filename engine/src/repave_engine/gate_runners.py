from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import jsonschema

from repave_engine.blueprint import CheckovGateConfig, TflintGateConfig, _find_repo_root
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.policy_selection import load_policy_selection_file
from repave_engine.provenance import validate_provenance_file


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def run_command(
    cmd: list[str],
    cwd: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = None
    if extra_env is not None:
        import os

        env = os.environ.copy()
        env.update(extra_env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def terraform_usable(output_dir: Path) -> bool:
    if not tool_available("terraform"):
        return False
    result = run_command(["terraform", "version"], output_dir)
    return result.returncode == 0


def tflint_config_args(output_dir: Path, config: TflintGateConfig) -> list[str]:
    config_path = output_dir / config.config_file
    if config_path.is_file():
        return ["--config", config.config_file]
    return []


def run_terraform_fmt(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not terraform_usable(output_dir):
        return GateResult("terraform-fmt", True, True, "terraform not available; skipped")

    result = run_command(["terraform", "fmt", "-check", "-recursive"], output_dir)
    if result.returncode == 0:
        return GateResult("terraform-fmt", True, False, "terraform fmt check passed")
    return GateResult(
        "terraform-fmt",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "terraform fmt check failed",
    )


def run_terraform_validate(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not terraform_usable(output_dir):
        return GateResult("terraform-validate", True, True, "terraform not available; skipped")

    init = run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-validate",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    validate = run_command(["terraform", "validate"], output_dir)
    if validate.returncode == 0:
        return GateResult("terraform-validate", True, False, "terraform validate passed")
    return GateResult(
        "terraform-validate",
        False,
        False,
        validate.stderr.strip() or validate.stdout.strip() or "terraform validate failed",
    )


def run_terraform_test(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not terraform_usable(output_dir):
        return GateResult("terraform-test", True, True, "terraform not available; skipped")

    raw = ctx.config("terraform-test")
    test_directory = str(raw.get("test_directory", "tests"))
    test_dir = output_dir / test_directory
    if not test_dir.is_dir() or not any(test_dir.rglob("*.tftest.hcl")):
        return GateResult("terraform-test", True, True, "no terraform tests; skipped")

    init = run_command(["terraform", "init", "-backend=false"], output_dir)
    if init.returncode != 0:
        return GateResult(
            "terraform-test",
            False,
            False,
            init.stderr.strip() or init.stdout.strip() or "terraform init failed",
        )

    result = run_command(["terraform", "test"], output_dir)
    if result.returncode == 0:
        return GateResult("terraform-test", True, False, "terraform test passed")
    return GateResult(
        "terraform-test",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "terraform test failed",
    )


def run_tflint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("tflint"):
        return GateResult("tflint", True, True, "tflint not installed; skipped")

    config = ctx.blueprint.tflint_gate if ctx.blueprint is not None else TflintGateConfig()
    config_args = tflint_config_args(output_dir, config)

    result = run_command(["tflint", "--init", *config_args], output_dir)
    if result.returncode != 0:
        return GateResult("tflint", False, False, result.stderr.strip() or "tflint init failed")

    result = run_command(["tflint", *config_args], output_dir)
    if result.returncode == 0:
        return GateResult("tflint", True, False, "tflint passed")
    return GateResult("tflint", False, False, result.stderr.strip() or "tflint failed")


def build_checkov_command(
    output_dir: Path,
    config: CheckovGateConfig,
    *,
    extra_skip_checks: tuple[str, ...] = (),
) -> list[str]:
    cmd = ["checkov", "-d", str(output_dir)]
    config_path = output_dir / config.config_file
    if config_path.is_file():
        cmd.extend(["--config-file", str(config_path)])

    checks_dir = output_dir / config.external_checks_dir
    if checks_dir.is_dir():
        cmd.extend(["--external-checks-dir", str(checks_dir)])

    skip_checks = {*config.skip_checks, *extra_skip_checks}
    for check_id in sorted(skip_checks):
        cmd.extend(["--skip-check", check_id])

    if config.soft_fail:
        cmd.append("--soft-fail")
    return cmd


def build_secrets_scan_command(output_dir: Path) -> list[str]:
    return [
        "checkov",
        "-d",
        str(output_dir),
        "--framework",
        "secrets",
        "--enable-secret-scan-all-files",
    ]


def run_secrets(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("checkov"):
        return GateResult("secrets", True, True, "checkov not installed; skipped")

    cmd = build_secrets_scan_command(output_dir)
    result = run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("secrets", True, False, "secrets scan passed")
    return GateResult("secrets", False, False, result.stderr.strip() or "secrets scan failed")


def run_checkov(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("checkov"):
        return GateResult("checkov", True, True, "checkov not installed; skipped")

    config = ctx.blueprint.checkov_gate if ctx.blueprint is not None else CheckovGateConfig()
    extra_skip: tuple[str, ...] = ()
    if ctx.gate_overrides is not None:
        extra_skip = (*extra_skip, *ctx.gate_overrides.checkov_skip_checks)
    selection = load_policy_selection_file(output_dir)
    if selection is not None:
        extra_skip = (*extra_skip, *selection.checkov_skip_checks)
    cmd = build_checkov_command(output_dir, config, extra_skip_checks=extra_skip)
    result = run_command(
        cmd,
        output_dir,
        extra_env={"REPAVE_CHECKOV_SCAN_ROOT": str(output_dir.resolve())},
    )
    if result.returncode == 0:
        return GateResult("checkov", True, False, "checkov passed")
    return GateResult("checkov", False, False, result.stderr.strip() or "checkov failed")


def run_docs_drift(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
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


def run_provenance_drift(ctx: GateContext) -> GateResult:
    blueprint = ctx.blueprint
    if blueprint is None or not blueprint.provenance_file:
        return GateResult("provenance-drift", True, True, "provenance not configured; skipped")

    provenance_path = ctx.output_dir / blueprint.provenance_file
    try:
        repo_root = _find_repo_root(blueprint.path)
        validate_provenance_file(provenance_path, repo_root)
    except FileNotFoundError as exc:
        return GateResult("provenance-drift", False, False, str(exc))
    except jsonschema.ValidationError as exc:
        return GateResult(
            "provenance-drift",
            False,
            False,
            f"Invalid provenance file: {exc.message}",
        )
    except Exception as exc:
        return GateResult("provenance-drift", False, False, str(exc))

    return GateResult("provenance-drift", True, False, "Provenance file present and valid")


def _yamllint_config_args(output_dir: Path) -> list[str]:
    config_path = output_dir / ".yamllint"
    if config_path.is_file():
        return ["-c", ".yamllint"]
    return []


def run_yamllint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("yamllint"):
        return GateResult("yamllint", True, True, "yamllint not installed; skipped")

    config_args = _yamllint_config_args(output_dir)
    result = run_command(["yamllint", *config_args, "."], output_dir)
    if result.returncode == 0:
        return GateResult("yamllint", True, False, "yamllint passed")
    return GateResult(
        "yamllint",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "yamllint failed",
    )


def run_ansible_lint(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("ansible-lint"):
        return GateResult("ansible-lint", True, True, "ansible-lint not installed; skipped")

    result = run_command(["ansible-lint"], output_dir)
    if result.returncode == 0:
        return GateResult("ansible-lint", True, False, "ansible-lint passed")
    return GateResult(
        "ansible-lint",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "ansible-lint failed",
    )


def _syntax_check_playbook(output_dir: Path) -> Path | None:
    candidates = (
        output_dir / "site.yml",
        output_dir / "playbooks" / "site.yml",
        output_dir / "molecule" / "default" / "converge.yml",
        output_dir / "molecule" / "default" / "playbook.yml",
    )
    for path in candidates:
        if path.is_file():
            return path
    return None


def run_ansible_syntax_check(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if not tool_available("ansible-playbook"):
        return GateResult(
            "ansible-syntax-check",
            True,
            True,
            "ansible-playbook not installed; skipped",
        )

    playbook = _syntax_check_playbook(output_dir)
    if playbook is None:
        return GateResult(
            "ansible-syntax-check",
            True,
            True,
            "no playbook found for syntax check; skipped",
        )

    result = run_command(
        ["ansible-playbook", "--syntax-check", str(playbook.relative_to(output_dir))],
        output_dir,
    )
    if result.returncode == 0:
        return GateResult("ansible-syntax-check", True, False, "ansible syntax check passed")
    return GateResult(
        "ansible-syntax-check",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "ansible syntax check failed",
    )


def run_molecule(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    molecule_config = output_dir / "molecule" / "default" / "molecule.yml"
    if not molecule_config.is_file():
        return GateResult("molecule", True, True, "no molecule scenario; skipped")

    if not tool_available("molecule"):
        return GateResult("molecule", True, True, "molecule not installed; skipped")

    result = run_command(["molecule", "test"], output_dir)
    if result.returncode == 0:
        return GateResult("molecule", True, False, "molecule test passed")
    return GateResult(
        "molecule",
        False,
        False,
        result.stderr.strip() or result.stdout.strip() or "molecule test failed",
    )


def _terraform_plan_json(output_dir: Path, plan_subdir: str) -> Path | None:
    if not terraform_usable(output_dir):
        return None
    work = output_dir / plan_subdir
    work.mkdir(parents=True, exist_ok=True)
    plan_binary = work / "tfplan"
    plan_json = work / "tfplan.json"

    init = run_command(["terraform", "init", "-backend=false", "-input=false"], output_dir)
    if init.returncode != 0:
        return None

    plan = run_command(
        [
            "terraform",
            "plan",
            "-out",
            str(plan_binary.relative_to(output_dir)),
            "-input=false",
            "-lock=false",
        ],
        output_dir,
    )
    if plan.returncode != 0:
        return None

    show = run_command(
        ["terraform", "show", "-json", str(plan_binary.relative_to(output_dir))],
        output_dir,
    )
    if show.returncode != 0:
        return None
    plan_json.write_text(show.stdout, encoding="utf-8")
    return plan_json


def run_opa(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is None or ctx.blueprint.opa_policies is None:
        return GateResult("opa", True, True, "opa policy pack not configured; skipped")

    if not tool_available("conftest"):
        return GateResult("opa", True, True, "conftest not installed; skipped")

    cfg = ctx.blueprint.opa_gate
    policies_dir = output_dir / cfg.policies_dir
    selection = load_policy_selection_file(output_dir)
    if selection is not None and not selection.opa_rego_files:
        return GateResult("opa", True, True, "no OPA policies selected; skipped")

    if not policies_dir.is_dir():
        return GateResult(
            "opa",
            False,
            False,
            f"opa policies directory missing: {cfg.policies_dir}",
        )

    artifact = ctx.blueprint.artifact_type
    if artifact == "opa-policy":
        fixtures = output_dir / cfg.fixtures_dir
        if not fixtures.is_dir() or not any(fixtures.iterdir()):
            return GateResult(
                "opa",
                False,
                False,
                f"opa fixtures missing or empty: {cfg.fixtures_dir}",
            )
        target = str(fixtures)
    elif artifact.startswith("terraform-"):
        plan_json = _terraform_plan_json(output_dir, cfg.plan_subdir)
        if plan_json is None:
            return GateResult(
                "opa",
                False,
                False,
                "terraform plan JSON could not be produced for opa evaluation",
            )
        target = str(plan_json)
    else:
        return GateResult("opa", True, True, "opa gate not applicable to this artifact type")

    cmd = ["conftest", "test", target, "-p", str(policies_dir)]
    result = run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    return GateResult("opa", False, False, detail)


_AZURE_POLICY_REQUIRED_PROPERTIES = frozenset(
    {"displayName", "policyType", "mode", "description", "policyRule"}
)
_AZURE_POLICY_MODES = frozenset({"All", "Indexed", "Microsoft.Kubernetes.Data"})


def _validate_azure_policy_definition(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return f"{path.name}: invalid JSON ({exc.msg})"
    if not isinstance(data, dict):
        return f"{path.name}: root must be a JSON object"
    properties = data.get("properties")
    if not isinstance(properties, dict):
        return f"{path.name}: missing properties object"
    missing = _AZURE_POLICY_REQUIRED_PROPERTIES - set(properties)
    if missing:
        missing_list = ", ".join(sorted(missing))
        return f"{path.name}: properties missing required fields: {missing_list}"
    mode = properties.get("mode")
    if mode not in _AZURE_POLICY_MODES:
        return f"{path.name}: invalid mode {mode!r}"
    if not isinstance(properties.get("policyRule"), dict):
        return f"{path.name}: policyRule must be an object"
    return None


def run_azure_policy(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is None or ctx.blueprint.artifact_type != "azure-policy":
        return GateResult("azure-policy", True, True, "azure-policy gate not applicable; skipped")

    cfg = ctx.blueprint.azure_policy_gate
    definitions_dir = output_dir / cfg.definitions_dir
    if not definitions_dir.is_dir():
        return GateResult(
            "azure-policy",
            False,
            False,
            f"azure policy definitions directory missing: {cfg.definitions_dir}",
        )

    json_files = sorted(definitions_dir.glob("*.json"))
    if not json_files:
        return GateResult(
            "azure-policy",
            False,
            False,
            f"no Azure Policy definition JSON files in {cfg.definitions_dir}",
        )

    errors: list[str] = []
    for path in json_files:
        problem = _validate_azure_policy_definition(path)
        if problem:
            errors.append(problem)
    if errors:
        return GateResult("azure-policy", False, False, "; ".join(errors))
    return GateResult("azure-policy", True, False, "azure policy definitions validated")
