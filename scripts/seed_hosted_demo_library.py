#!/usr/bin/env python3
"""Publish and register the opsdevcode hosted demo library via repave CLI."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - stdlib fallback for minimal envs
    yaml = None  # type: ignore[assignment]


@dataclass(frozen=True)
class RepoSeed:
    seed_id: str
    blueprint: str
    inputs: dict[str, str]
    register_overrides: dict[str, str]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_catalog(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
    else:
        raise SystemExit(
            "PyYAML required: cd engine && uv run python ../scripts/seed_hosted_demo_library.py"
        )
    if not isinstance(data, dict):
        raise ValueError(f"invalid catalog: {path}")
    return data


def _repo_url(org: str, repo_name: str) -> str:
    return f"https://github.com/{org}/{repo_name}"


def _infer_repo_name(blueprint: str, inputs: dict[str, str]) -> str:
    cloud = inputs.get("cloud_provider", "aws")
    if blueprint == "terraform-module-generic":
        return f"tf-{cloud}-{inputs['module_name']}"
    if blueprint == "ansible-role-generic":
        return f"ansible-role-{inputs['role_name']}"
    if blueprint == "opa-policy-generic":
        return f"opa-policy-{inputs['organization']}-{inputs['policy_name']}"
    if blueprint == "checkov-policy-generic":
        return f"checkov-policy-{inputs['organization']}-{inputs['policy_name']}"
    if blueprint == "helm-chart-generic":
        return f"helm-{inputs['chart_name']}"
    if blueprint == "gitops-deployment-generic":
        return f"gitops-{inputs['environment']}-{inputs['service_name']}"
    raise ValueError(f"cannot infer repo name for blueprint {blueprint!r}")


def _modules_path(modules_root: Path, repo_name: str) -> Path:
    return modules_root / repo_name


def _repave_command(*, engine_dir: Path) -> list[str]:
    explicit = os.environ.get("REPAVE_CLI", "").strip()
    if explicit:
        return explicit.split()
    if shutil.which("repave"):
        return ["repave"]
    if shutil.which("uv"):
        return ["uv", "run", "repave"]
    raise SystemExit("repave CLI not found: install engine or set REPAVE_CLI")


def _run(cmd: list[str], *, cwd: Path, dry_run: bool, env: dict[str, str] | None = None) -> None:
    printable = " ".join(cmd)
    print(f"+ {printable}")
    if dry_run:
        return
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def _parse_seeds(catalog: dict[str, Any]) -> tuple[str, str, str, list[RepoSeed]]:
    org = str(catalog.get("org", "opsdevcode"))
    owner = str(catalog.get("owner", "platform"))
    registered_by = str(catalog.get("registered_by", "hosted-demo-seed"))
    raw = catalog.get("repos")
    if not isinstance(raw, list):
        raise ValueError("catalog.repos must be a list")
    seeds: list[RepoSeed] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each catalog repo entry must be a mapping")
        reg = item.get("register") or {}
        if not isinstance(reg, dict):
            raise ValueError("register must be a mapping when present")
        inputs = item.get("inputs") or {}
        if not isinstance(inputs, dict):
            raise ValueError("inputs must be a mapping")
        seeds.append(
            RepoSeed(
                seed_id=str(item["id"]),
                blueprint=str(item["blueprint"]),
                inputs={str(k): str(v) for k, v in inputs.items()},
                register_overrides={str(k): str(v) for k, v in reg.items()},
            )
        )
    return org, owner, registered_by, seeds


def _ensure_fleet_config(repo_root: Path, fleet_file: Path) -> None:
    fleet_file.parent.mkdir(parents=True, exist_ok=True)
    if fleet_file.is_file():
        return
    config_path = repo_root / "repave.config.yaml"
    if config_path.is_file():
        return
    example = repo_root / "repave.config.yaml.example"
    if not example.is_file():
        fleet_file.touch()
        return
    # Minimal fleet block for local register; hosted cluster uses chart config.
    fleet_file.touch()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=_repo_root())
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path(__file__).with_name("hosted-demo-library.yaml"),
    )
    parser.add_argument("--github-org", default=os.environ.get("REPAVE_GITHUB_ORG", "opsdevcode"))
    parser.add_argument(
        "--modules-root",
        type=Path,
        default=Path(os.environ.get("REPAVE_MODULES_ROOT", Path.home() / "repave-modules")),
    )
    parser.add_argument(
        "--fleet-file",
        type=Path,
        default=Path(os.environ.get("REPAVE_FLEET_FILE", "")),
    )
    parser.add_argument("--engine-dir", type=Path, default=None, help="default: <repo-root>/engine")
    parser.add_argument("--skip-publish", action="store_true")
    parser.add_argument("--skip-register", action="store_true")
    parser.add_argument("--render-manifests", action="store_true")
    parser.add_argument("--manifests-dir", type=Path, default=Path("fleet-manifests"))
    parser.add_argument("--operator-namespace", default="repave-system")
    parser.add_argument("--dry-run", action="store_true", help="print commands only")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--apply-manifests", action="store_true")
    args = parser.parse_args(argv)

    catalog = _load_catalog(args.catalog)
    org, owner, _registered_by, seeds = _parse_seeds(catalog)
    github_org = args.github_org or org
    repo_root = args.repo_root.resolve()
    engine_dir = (args.engine_dir or repo_root / "engine").resolve()
    repave = _repave_command(engine_dir=engine_dir)

    fleet_file = args.fleet_file
    if not fleet_file or str(fleet_file) == ".":
        fleet_file = repo_root / "repave-fleet" / "registry.jsonl"
    _ensure_fleet_config(repo_root, fleet_file)
    env = {
        **os.environ,
        "REPAVE_FLEET_FILE": str(fleet_file),
        "REPAVE_GITHUB_ORG": github_org,
        "REPAVE_MODULES_ROOT": str(args.modules_root.expanduser()),
    }
    if os.environ.get("REPAVE_FORCE_GITHUB_APP", "").strip().lower() in {"1", "true", "yes"}:
        # Hosted portal mounts a legacy PAT; prefer installation token for publish/git push.
        env["GITHUB_TOKEN"] = ""

    published: list[tuple[RepoSeed, str, Path]] = []

    for seed in seeds:
        repo_name = _infer_repo_name(seed.blueprint, seed.inputs)
        url = _repo_url(github_org, repo_name)
        local_path = _modules_path(args.modules_root.expanduser(), repo_name)

        if not args.skip_publish:
            cmd = [
                *repave,
                "generate",
                "--repo-root",
                str(repo_root),
                "--blueprint",
                f"blueprints/{seed.blueprint}",
                "--github-org",
                github_org,
                "--no-dry-run",
            ]
            for key, value in seed.inputs.items():
                cmd.extend(["--input", f"{key}={value}"])
            try:
                _run(cmd, cwd=engine_dir, dry_run=args.dry_run, env=env)
            except subprocess.CalledProcessError as exc:
                if not args.continue_on_error:
                    raise
                print(f"warning: publish failed for {seed.seed_id}: {exc}", file=sys.stderr)
        published.append((seed, url, local_path))

        if args.skip_register:
            continue

        reg_cmd = [
            *repave,
            "register",
            url,
            "--repo-root",
            str(repo_root),
            "--owner",
            owner,
            "--blueprint",
            seed.blueprint,
        ]
        if local_path.is_dir():
            reg_cmd.extend(["--path", str(local_path)])
        for key, value in seed.register_overrides.items():
            if key == "blueprint_version":
                reg_cmd.extend(["--blueprint-version", value])
            elif key == "blueprint":
                reg_cmd.extend(["--blueprint", value])
            elif key == "standard_source":
                reg_cmd.extend(["--standard-source", value])
            elif key == "standard_version":
                reg_cmd.extend(["--standard-version", value])
        try:
            _run(reg_cmd, cwd=engine_dir, dry_run=args.dry_run, env=env)
        except subprocess.CalledProcessError as exc:
            if not args.continue_on_error:
                raise
            print(f"warning: register failed for {seed.seed_id}: {exc}", file=sys.stderr)

    if args.render_manifests and not args.skip_register:
        out = args.manifests_dir.resolve()
        cmd = [
            *repave,
            "fleet-manifests",
            "--repo-root",
            str(repo_root),
            "--output",
            str(out),
            "--namespace",
            args.operator_namespace,
            "--kustomization",
            "--gitops-readme",
            "--prune",
            "--enable-remediation",
        ]
        _run(cmd, cwd=engine_dir, dry_run=args.dry_run, env=env)
        if args.apply_manifests and not args.dry_run:
            _run(["kubectl", "apply", "-k", str(out)], cwd=repo_root, dry_run=False)

    if not args.dry_run and not args.skip_register:
        list_cmd = [*repave, "fleet", "--repo-root", str(repo_root), "--format", "json"]
        proc = subprocess.run(
            list_cmd,
            cwd=engine_dir,
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )
        print(proc.stdout)
        summary = json.loads(proc.stdout)
        print(f"registered {summary.get('count', '?')} repositories in {fleet_file}")

    print("done — open /activity and /fleet on the portal; apply fleet-manifests for operator GPRs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
