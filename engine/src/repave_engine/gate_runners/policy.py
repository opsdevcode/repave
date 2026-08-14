from __future__ import annotations

import json
from pathlib import Path

import repave_engine.gate_runners as _gr
from repave_engine.blueprint import CheckovGateConfig
from repave_engine.gate_registry import GateContext, GateResult
from repave_engine.gate_runners._core import (
    _checkov_command,
    _toolchain_skip,
    build_checkov_command,
    build_secrets_scan_command,
)
from repave_engine.gate_runners.helm import _helm_chart_dir
from repave_engine.policy_selection import load_policy_selection_file


def run_secrets(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if _gr.checkov_argv() is None:
        return _toolchain_skip(ctx, "secrets", "checkov not installed")

    cmd = _checkov_command(build_secrets_scan_command(output_dir))
    result = _gr.run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("secrets", True, False, "secrets scan passed")
    return GateResult("secrets", False, False, result.stderr.strip() or "secrets scan failed")


def run_checkov(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if _gr.checkov_argv() is None:
        return _toolchain_skip(ctx, "checkov", "checkov not installed")

    config = ctx.blueprint.checkov_gate if ctx.blueprint is not None else CheckovGateConfig()
    extra_skip: tuple[str, ...] = ()
    if ctx.gate_overrides is not None:
        extra_skip = (*extra_skip, *ctx.gate_overrides.checkov_skip_checks)
    selection = load_policy_selection_file(output_dir)
    if selection is not None:
        extra_skip = (*extra_skip, *selection.checkov_skip_checks)
    cmd = _checkov_command(build_checkov_command(output_dir, config, extra_skip_checks=extra_skip))
    scan_root = output_dir / config.scan_dir if config.scan_dir else output_dir
    result = _gr.run_command(
        cmd,
        output_dir,
        extra_env={"REPAVE_CHECKOV_SCAN_ROOT": str(scan_root.resolve())},
    )
    if result.returncode == 0:
        return GateResult("checkov", True, False, "checkov passed")
    return GateResult("checkov", False, False, result.stderr.strip() or "checkov failed")


def _write_helm_rendered_manifest(output_dir: Path, ctx: GateContext) -> tuple[Path | None, str]:
    if not _gr.tool_available("helm"):
        return None, "helm not installed"
    chart_dir = _helm_chart_dir(output_dir, ctx, "opa")
    if not (chart_dir / "Chart.yaml").is_file():
        return None, "no Chart.yaml found"
    cfg = ctx.config("opa")
    release = str(cfg.get("helm_release_name", cfg.get("release_name", "repave-test")))
    resolved_out = output_dir.resolve()
    resolved_chart = chart_dir.resolve()
    result = _gr.run_command(
        [
            "helm",
            "template",
            release,
            str(resolved_chart.relative_to(resolved_out)),
        ],
        resolved_out,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "helm template failed"
        return None, detail
    manifest_path = output_dir / ".repave" / "helm-rendered.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(result.stdout, encoding="utf-8")
    return manifest_path, ""


def _run_opa_helm_chart(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
) -> GateResult:
    manifest_path, err = _write_helm_rendered_manifest(output_dir, ctx)
    if manifest_path is None:
        if err == "helm not installed":
            return GateResult("opa", True, True, "helm not installed; skipped")
        if err == "no Chart.yaml found":
            return GateResult("opa", True, True, "no Helm chart found; skipped")
        return GateResult("opa", False, False, err)
    cmd = [
        "conftest",
        "test",
        str(manifest_path.relative_to(output_dir)),
        "-p",
        str(policies_dir),
    ]
    result = _gr.run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed on helm-rendered manifests")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    return GateResult("opa", False, False, detail)


def _opa_native_globs(ctx: GateContext) -> list[str]:
    raw = ctx.config("opa")
    configured = raw.get("native_globs")
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured]
    return [
        "datadog/monitors/*.json",
        "datadog/dashboards/*.json",
        "grafana/dashboards/*.json",
        "prometheus/rules/*.y*ml",
    ]


def _opa_gitops_globs(ctx: GateContext) -> list[str]:
    raw = ctx.config("opa")
    configured = raw.get("manifest_globs")
    if isinstance(configured, list) and configured:
        return [str(item) for item in configured]
    return ["*.y*ml", "apps/*.y*ml"]


def _run_conftest_over_files(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
    *,
    patterns: list[str],
    empty_detail: str,
    passed_detail: str,
) -> GateResult:
    """Evaluate conftest per file for artifacts with no plan or rendered manifest."""
    targets: list[Path] = []
    for pattern in patterns:
        targets.extend(sorted(output_dir.glob(pattern)))
    if not targets:
        return GateResult("opa", True, True, empty_detail)

    errors: list[str] = []
    for path in targets:
        parser = "yaml" if path.suffix in (".yaml", ".yml") else "json"
        cmd = [
            "conftest",
            "test",
            str(path.relative_to(output_dir)),
            "-p",
            str(policies_dir),
            "--parser",
            parser,
        ]
        result = _gr.run_command(cmd, output_dir)
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
            errors.append(f"{path.name}: {detail}")

    if errors:
        return GateResult("opa", False, False, "; ".join(errors))
    return GateResult("opa", True, False, passed_detail.format(count=len(targets)))


def _run_opa_native_observability(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
) -> GateResult:
    return _run_conftest_over_files(
        ctx,
        policies_dir,
        output_dir,
        patterns=_opa_native_globs(ctx),
        empty_detail="no native observability files for opa; skipped",
        passed_detail="conftest passed for {count} native file(s)",
    )


def _run_opa_gitops(
    ctx: GateContext,
    policies_dir: Path,
    output_dir: Path,
) -> GateResult:
    return _run_conftest_over_files(
        ctx,
        policies_dir,
        output_dir,
        patterns=_opa_gitops_globs(ctx),
        empty_detail="no GitOps manifests for opa; skipped",
        passed_detail="conftest passed for {count} GitOps manifest(s)",
    )


def run_opa(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is None or ctx.blueprint.opa_policies is None:
        return GateResult("opa", True, True, "opa policy pack not configured; skipped")

    if not _gr.tool_available("conftest"):
        return _toolchain_skip(ctx, "opa", "conftest not installed")

    cfg = ctx.blueprint.opa_gate
    policies_dir = output_dir / cfg.policies_dir
    selection = load_policy_selection_file(output_dir)
    from repave_engine.policy_selection import blueprint_policy_optional

    if selection is None and ctx.blueprint is not None and blueprint_policy_optional(ctx.blueprint):
        if ctx.forbid_policy_skip:
            from repave_engine.blueprint import artifact_family
            from repave_engine.mandatory_policy import MANDATORY_POLICY_GATE_ID

            family = artifact_family(ctx.blueprint.artifact_type)
            return GateResult(
                "opa",
                False,
                False,
                (
                    f"policy is mandatory on regulated family {family}; "
                    f"set enable_policy: true or add a waiver in data/waivers.jsonl "
                    f"(gate_id: {MANDATORY_POLICY_GATE_ID})"
                ),
            )
        return GateResult("opa", True, True, "policy pack not enabled; skipped")
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
    elif artifact.startswith("terraform-") or artifact == "observability":
        if artifact == "observability" and not any(output_dir.glob("*.tf")):
            return _run_opa_native_observability(ctx, policies_dir, output_dir)
        plan_json = _gr._terraform_plan_json(output_dir, cfg.plan_subdir)
        if plan_json is not None:
            target = str(plan_json)
        else:
            fixtures = output_dir / cfg.fixtures_dir
            if fixtures.is_dir() and any(fixtures.glob("*.json")):
                target = str(fixtures)
            elif not _gr.terraform_usable(output_dir):
                return _toolchain_skip(ctx, "opa", "terraform not available")
            else:
                return GateResult(
                    "opa",
                    False,
                    False,
                    (
                        "terraform plan JSON could not be produced for opa evaluation "
                        "(terraform init/plan failed). Fix the module or run the full "
                        "toolchain via deploy/local Docker Compose."
                    ),
                )
    elif artifact == "helm-chart":
        return _run_opa_helm_chart(ctx, policies_dir, output_dir)
    elif artifact == "gitops-deployment":
        return _run_opa_gitops(ctx, policies_dir, output_dir)
    else:
        return GateResult("opa", True, True, "opa gate not applicable to this artifact type")

    cmd = ["conftest", "test", target, "-p", str(policies_dir)]
    result = _gr.run_command(cmd, output_dir)
    if result.returncode == 0:
        return GateResult("opa", True, False, "conftest passed")
    detail = result.stderr.strip() or result.stdout.strip() or "conftest failed"
    detail = _format_opa_failure(detail)
    return GateResult("opa", False, False, detail)


def _format_opa_failure(detail: str) -> str:
    lowered = detail.lower()
    if "destructive delete" in lowered:
        return (
            "Publish blocked: plan-time OPA rejected a destructive change "
            "(resource delete without replacement). Adjust the plan or use a profile "
            "that allows the change only after platform review.\n\n"
            f"{detail}"
        )
    return detail


_AZURE_POLICY_REQUIRED_PROPERTIES = frozenset(
    {"displayName", "policyType", "mode", "description", "policyRule"}
)
_AZURE_POLICY_MODES = frozenset({"All", "Indexed", "Microsoft.Kubernetes.Data"})
_AZURE_POLICY_TYPES = frozenset({"Custom", "Static"})


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
    policy_type = properties.get("policyType")
    if policy_type not in _AZURE_POLICY_TYPES:
        return f"{path.name}: policyType must be Custom or Static, got {policy_type!r}"
    for label, key in (("displayName", "displayName"), ("description", "description")):
        value = properties.get(key)
        if not isinstance(value, str) or not value.strip():
            return f"{path.name}: {label} must be a non-empty string"
    parameters = properties.get("parameters")
    if parameters is not None and not isinstance(parameters, dict):
        return f"{path.name}: parameters must be an object when present"
    metadata = properties.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        return f"{path.name}: metadata must be an object when present"
    policy_rule = properties.get("policyRule")
    if not isinstance(policy_rule, dict):
        return f"{path.name}: policyRule must be an object"
    if "if" not in policy_rule or "then" not in policy_rule:
        return f"{path.name}: policyRule must include if and then"
    then = policy_rule.get("then")
    if not isinstance(then, dict) or "effect" not in then:
        return f"{path.name}: policyRule.then must include effect"
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
