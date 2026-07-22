from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class OutputConfig:
    github_org: str
    modules_root: Path
    repo_name_template: str = "tf-{module_name}"


def load_output_config(
    repo_root: Path,
    *,
    github_org: str | None = None,
    modules_root: Path | str | None = None,
    repo_name_template: str | None = None,
) -> OutputConfig:
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    output = file_data.get("output", {}) if isinstance(file_data, dict) else {}

    resolved_org = (
        github_org
        or os.environ.get("REPAVE_GITHUB_ORG")
        or output.get("github_org")
        or ""
    )
    modules_root_value = (
        modules_root
        or os.environ.get("REPAVE_MODULES_ROOT")
        or output.get("modules_root")
        or ""
    )
    resolved_template = (
        repo_name_template
        or output.get("repo_name_template")
        or "tf-{module_name}"
    )

    if not resolved_org:
        raise ValueError(
            "GitHub organization is required. Set output.github_org in repave.config.yaml "
            "or REPAVE_GITHUB_ORG."
        )
    if not modules_root_value:
        raise ValueError(
            "Module output root is required. Set output.modules_root in repave.config.yaml "
            "or REPAVE_MODULES_ROOT to a directory outside the repave repo."
        )

    root_path = Path(modules_root_value).expanduser()
    if not root_path.is_absolute():
        root_path = (repo_root / root_path).resolve()

    return OutputConfig(
        github_org=str(resolved_org),
        modules_root=root_path,
        repo_name_template=str(resolved_template),
    )


def _load_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping in {path}")
    return data
