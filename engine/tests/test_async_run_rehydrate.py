from __future__ import annotations

from pathlib import Path

from repave_engine.generate_api import generation_result_from_stored_run
from repave_engine.run_store import RunRecord, RunStatus
from repave_engine.settings import OutputConfig


def test_generation_result_from_stored_run_uses_snapshot(repo_root: Path) -> None:
    record = RunRecord(
        run_id="run-snapshot",
        status=RunStatus.SUCCEEDED,
        blueprint_name="terraform-module-generic",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {"module_name": "demo-mod", "cloud_provider": "aws"}},
        result={
            "output_dir": "/worker/staging/run-snapshot",
            "gates": [
                {"name": "terraform-fmt", "passed": True, "skipped": False, "message": "ok"},
            ],
            "pr_message": "dry-run",
            "rendered_files": [
                {"path": "main.tf", "content": "# stub\n", "truncated": False},
            ],
        },
    )
    output = OutputConfig(github_org="test-org", modules_root=repo_root / "modules")
    rebuilt = generation_result_from_stored_run(
        record=record,
        repo_root=repo_root,
        output_config=output,
    )
    assert rebuilt is not None
    assert rebuilt.blueprint.name == "terraform-module-generic"
    assert rebuilt.gates[0].passed is True
    assert len(rebuilt.rendered_files) == 1
    assert rebuilt.rendered_files[0].path == "main.tf"
    assert rebuilt.rendered_files[0].content == "# stub\n"


def test_generation_result_from_stored_run_empty_list_falls_back_to_artifacts(
    repo_root: Path, tmp_path: Path
) -> None:
    """Empty rendered_files list must not block artifact rehydrate (plan preview)."""
    artifact = tmp_path / "staging-empty-list"
    artifact.mkdir()
    (artifact / "main.tf").write_text("# from disk\n", encoding="utf-8")
    record = RunRecord(
        run_id="run-empty-list",
        status=RunStatus.SUCCEEDED,
        blueprint_name="terraform-module-generic",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {"module_name": "demo-mod", "cloud_provider": "aws"}},
        result={
            "artifact_root": str(artifact),
            "rendered_files": [],
            "gates": [
                {"name": "terraform-fmt", "passed": False, "skipped": False, "message": "fmt"},
            ],
            "pr_message": "dry-run",
        },
    )
    output = OutputConfig(github_org="test-org", modules_root=repo_root / "modules")
    rebuilt = generation_result_from_stored_run(
        record=record,
        repo_root=repo_root,
        output_config=output,
    )
    assert rebuilt is not None
    assert len(rebuilt.rendered_files) >= 1
    assert rebuilt.rendered_files[0].path == "main.tf"
    assert rebuilt.rendered_files[0].content == "# from disk\n"


def test_generation_result_from_stored_run_falls_back_to_artifact_root(
    repo_root: Path, tmp_path: Path
) -> None:
    artifact = tmp_path / "staging"
    artifact.mkdir()
    (artifact / "main.tf").write_text("# stub\n", encoding="utf-8")
    record = RunRecord(
        run_id="run-1",
        status=RunStatus.SUCCEEDED,
        blueprint_name="terraform-module-generic",
        dry_run=True,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {"module_name": "demo-mod", "cloud_provider": "aws"}},
        result={
            "artifact_root": str(artifact),
            "rendered_files": 1,
            "gates": [
                {"name": "terraform-fmt", "passed": True, "skipped": False, "message": "ok"},
            ],
            "pr_message": "dry-run",
        },
    )
    output = OutputConfig(github_org="test-org", modules_root=repo_root / "modules")
    rebuilt = generation_result_from_stored_run(
        record=record,
        repo_root=repo_root,
        output_config=output,
    )
    assert rebuilt is not None
    assert rebuilt.render.output_dir == artifact
    assert rebuilt.rendered_files[0].path == "main.tf"


def test_generation_result_from_stored_run_publish_without_artifact(
    repo_root: Path,
) -> None:
    record = RunRecord(
        run_id="run-publish",
        status=RunStatus.SUCCEEDED,
        blueprint_name="terraform-module-generic",
        dry_run=False,
        client_request_id=None,
        acting_user="tester",
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        payload={"inputs": {"module_name": "demo-mod", "cloud_provider": "aws"}},
        result={
            "output_dir": "/worker/staging/run-publish",
            "gates": [
                {"name": "terraform-fmt", "passed": True, "skipped": False, "message": "ok"},
            ],
            "pr_message": "publish complete",
            "rendered_files": 0,
        },
    )
    output = OutputConfig(github_org="test-org", modules_root=repo_root / "modules")
    rebuilt = generation_result_from_stored_run(
        record=record,
        repo_root=repo_root,
        output_config=output,
    )
    assert rebuilt is not None
    assert rebuilt.dry_run is False
    assert rebuilt.rendered_files == ()
    assert rebuilt.pr_message == "publish complete"
