from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from repave_engine.pipeline import generate_from_blueprint
from repave_engine.publish_idempotency import (
    PublishIdempotencyContext,
    PublishIdempotencyStore,
    build_publish_key,
    compute_publish_content_hash,
    publish_message_succeeded,
)
from repave_engine.settings import OutputConfig
from repave_engine.target_repo import resolve_module_repository


def test_compute_publish_content_hash_is_stable(tmp_path: Path) -> None:
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    (staging / ".tflint.hcl").write_text("config {}\n", encoding="utf-8")
    first = compute_publish_content_hash(staging, artifact_type="terraform-module")
    second = compute_publish_content_hash(staging, artifact_type="terraform-module")
    assert first == second
    assert len(first) == 64


def test_build_publish_key_includes_owner_repo_and_hash(tmp_path: Path) -> None:
    repository = resolve_module_repository(
        module_name="demo",
        config=OutputConfig(github_org="acme", modules_root=tmp_path / "modules"),
        name_template="tf-{module_name}",
    )
    key = build_publish_key(repository, "abc123")
    assert key == "github:acme/tf-demo:abc123"


def test_publish_idempotency_store_records_and_reuses_receipt(tmp_path: Path) -> None:
    store = PublishIdempotencyStore(tmp_path / "runs.sqlite")
    repository = resolve_module_repository(
        module_name="demo",
        config=OutputConfig(github_org="acme", modules_root=tmp_path / "modules"),
        name_template="tf-{module_name}",
    )
    key = build_publish_key(repository, "deadbeef")
    receipt = store.record(
        publish_key=key,
        pr_message="published once",
        repository_web_url=repository.web_url,
        content_hash="deadbeef",
        run_id="run-1",
        client_request_id="req-1",
    )
    assert receipt.pr_message == "published once"
    assert store.get(key) == receipt


def test_publish_message_succeeded_detects_failures() -> None:
    assert publish_message_succeeded("Pushed initial commit.") is True
    assert publish_message_succeeded("GitHub publish failed.\nError") is False
    assert publish_message_succeeded("GitHub repository provisioning failed.\nError") is False


def test_generate_skips_github_publish_when_receipt_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    store = PublishIdempotencyStore(tmp_path / "runs.sqlite")
    publish_calls: list[str] = []

    def fake_create_pr(plan, *, github_token):  # type: ignore[no-untyped-def]
        publish_calls.append("create")
        return "Pushed initial commit."

    monkeypatch.setattr("repave_engine.pipeline.create_pull_request", fake_create_pr)

    from repave_engine.blueprint import blueprint_dir, load_blueprint

    blueprint = load_blueprint(
        blueprint_dir(repo_root, "terraform-module-generic"),
        repo_root=repo_root,
    )
    output = OutputConfig(
        github_org="example-org",
        modules_root=tmp_path / "modules",
    )
    values = {
        "module_name": "idempotent-demo",
        "description": "demo",
        "cloud_provider": "aws",
        "provider_services": "ec2",
    }

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    module_repository = resolve_module_repository(
        module_name="idempotent-demo",
        config=output,
        name_template=blueprint.output_repo_name_template,
        template_values=values,
    )
    content_hash = compute_publish_content_hash(staging, artifact_type=blueprint.artifact_type)
    publish_key = build_publish_key(module_repository, content_hash)
    store.record(
        publish_key=publish_key,
        pr_message="Module published to local repository\n\nPushed initial commit.",
        repository_web_url=module_repository.web_url,
        content_hash=content_hash,
        run_id="run-a",
        client_request_id="req-a",
    )

    with (
        patch("repave_engine.pipeline.run_gates") as run_gates,
        patch("repave_engine.pipeline.render_blueprint") as render_blueprint,
        patch("repave_engine.pipeline.publish_to_module_repository") as publish_local,
    ):
        from repave_engine.gates import GateResult
        from repave_engine.render import RenderResult

        render_blueprint.return_value = RenderResult(output_dir=staging, values=values)
        run_gates.return_value = [GateResult("terraform fmt", True, False, "ok")]

        result = generate_from_blueprint(
            blueprint,
            values,
            output_config=output,
            dry_run=False,
            require_run=False,
            github_token="ghp_test",
            repo_root=repo_root,
            record_operability=False,
            send_notification=False,
            skip_input_validation=True,
            publish_idempotency=PublishIdempotencyContext(
                store=store,
                run_id="run-b",
                client_request_id="req-a",
            ),
        )

    assert publish_calls == []
    publish_local.assert_not_called()
    assert "Pushed initial commit." in result.pr_message
