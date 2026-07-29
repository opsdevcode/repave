from __future__ import annotations

from pathlib import Path

from repave_engine.generate_api import generation_result_from_stored_run
from repave_engine.run_store import RunRecord, RunStatus
from repave_engine.settings import OutputConfig


def test_generation_result_from_stored_run(repo_root: Path, tmp_path: Path) -> None:
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
    assert rebuilt.blueprint.name == "terraform-module-generic"
    assert rebuilt.gates[0].passed is True
    assert rebuilt.render.output_dir == artifact
