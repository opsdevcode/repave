from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from repave_engine.settings import OutputConfig


@dataclass(frozen=True)
class ModuleRepository:
    name: str
    owner: str
    local_path: Path
    clone_url: str
    web_url: str


def resolve_module_repository(
    *,
    module_name: str,
    config: OutputConfig,
    name_template: str,
) -> ModuleRepository:
    repo_name = name_template.format(module_name=module_name)
    local_path = config.modules_root / repo_name
    return ModuleRepository(
        name=repo_name,
        owner=config.github_org,
        local_path=local_path,
        clone_url=f"https://github.com/{config.github_org}/{repo_name}.git",
        web_url=f"https://github.com/{config.github_org}/{repo_name}",
    )


def publish_to_module_repository(
    staging_dir: Path,
    repository: ModuleRepository,
    *,
    dry_run: bool,
) -> str:
    if dry_run:
        return (
            "Dry-run: module would be written to its own repository.\n"
            f"Remote: {repository.web_url}\n"
            f"Local clone path: {repository.local_path}"
        )

    if repository.local_path.exists() and any(repository.local_path.iterdir()):
        raise FileExistsError(
            f"Module repository already exists and is not empty: {repository.local_path}"
        )

    repository.local_path.mkdir(parents=True, exist_ok=True)
    _copy_tree_contents(staging_dir, repository.local_path)
    _ensure_git_repository(repository.local_path, module_name=repository.name)

    return (
        f"Module published to local repository at {repository.local_path}\n"
        f"Planned remote: {repository.web_url}\n"
        "Create the GitHub repository and push when ready."
    )


def _copy_tree_contents(source_dir: Path, destination_dir: Path) -> None:
    for item in source_dir.iterdir():
        target = destination_dir / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required to bootstrap module repositories")
    return git


def _run_git(args: list[str], *, cwd: Path) -> None:
    subprocess.run(
        [_git_executable(), *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _ensure_git_repository(repo_dir: Path, *, module_name: str) -> None:
    if (repo_dir / ".git").exists():
        return

    _run_git(["init"], cwd=repo_dir)
    _run_git(["config", "user.email", "repave@local.dev"], cwd=repo_dir)
    _run_git(["config", "user.name", "repave"], cwd=repo_dir)
    _run_git(["add", "."], cwd=repo_dir)
    _run_git(
        ["commit", "-m", f"chore: bootstrap {module_name} from repave"],
        cwd=repo_dir,
    )
