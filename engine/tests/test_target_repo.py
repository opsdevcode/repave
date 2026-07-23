from __future__ import annotations

import subprocess
from pathlib import Path

from repave_engine.target_repo import ModuleRepository, publish_to_module_repository


def _repository(modules_root: Path) -> ModuleRepository:
    return ModuleRepository(
        name="tf-aws-example",
        owner="example-org",
        local_path=modules_root / "tf-aws-example",
        clone_url="https://github.com/example-org/tf-aws-example.git",
        web_url="https://github.com/example-org/tf-aws-example",
    )


def test_publish_bootstraps_git_repo_on_main(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.tf").write_text("# stub\n", encoding="utf-8")

    modules_root = tmp_path / "modules"
    repository = _repository(modules_root)

    publish_to_module_repository(staging, repository, dry_run=False)

    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=repository.local_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert branch.stdout.strip() == "main"
    assert (repository.local_path / ".git").exists()


def test_publish_dry_run_does_not_create_local_repo(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    modules_root = tmp_path / "modules"
    repository = _repository(modules_root)

    message = publish_to_module_repository(staging, repository, dry_run=True)

    assert not repository.local_path.exists()
    assert "Dry-run" in message
