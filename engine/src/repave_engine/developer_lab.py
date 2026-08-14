"""v3 developer lab — bundled catalog paths from examples/platform-dev."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repave_engine.v3_foundation import load_v3_foundation_config

_PLATFORM_DEV = Path("examples") / "platform-dev"


@dataclass(frozen=True)
class DeveloperLabPaths:
    maturity_rubric: Path
    workload_profiles: Path
    deployment_sets: Path
    initiatives: Path
    default_team: str = "platform"


def is_developer_lab_enabled(repo_root: Path) -> bool:
    """True when v3.developer_lab.enabled is explicitly on."""
    return load_v3_foundation_config(repo_root).developer_lab_enabled


def load_developer_lab_paths(repo_root: Path) -> DeveloperLabPaths | None:
    """Resolve bundled catalog fixtures when developer lab is enabled.

    Does not configure environment vending or invent a GitOps repo. Live sandbox
    requests still need an explicit ``environment_vending`` block.
    """
    if not is_developer_lab_enabled(repo_root):
        return None
    root = (repo_root / _PLATFORM_DEV).resolve()
    paths = DeveloperLabPaths(
        maturity_rubric=root / "config" / "maturity-rubric.yaml",
        workload_profiles=root / "config" / "workload-profiles.yaml",
        deployment_sets=root / "config" / "deployment-sets.yaml",
        initiatives=root / "fixtures" / "platform-metrics" / "initiatives.jsonl",
    )
    missing = (
        paths.maturity_rubric,
        paths.workload_profiles,
        paths.deployment_sets,
        paths.initiatives,
    )
    absent = next((path for path in missing if not path.is_file()), None)
    if absent is not None:
        raise ValueError(
            "v3.developer_lab.enabled is true but bundled fixtures are missing: "
            f"{absent}. Set v3.developer_lab.enabled: false, ship examples/platform-dev "
            "with the image, or set service_catalog paths explicitly."
        )
    return paths
