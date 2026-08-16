from __future__ import annotations

from pathlib import Path


def test_component_stubs_emit_aws_resources(repo_root: Path) -> None:
    roots = repo_root / "blueprints"
    rds = (
        roots / "terraform-component-database/template/modules/_rds-stub/main.tf.jinja"
    ).read_text(encoding="utf-8")
    bucket = (
        roots / "terraform-component-bucket/template/modules/_s3-stub/main.tf.jinja"
    ).read_text(encoding="utf-8")
    queue = (
        roots / "terraform-component-queue/template/modules/_sqs-stub/main.tf.jinja"
    ).read_text(encoding="utf-8")
    assert "aws_db_instance" in rds
    assert "aws_s3_bucket" in bucket
    assert "aws_sqs_queue" in queue
    assert "null_resource" in rds
    assert "null_resource" in bucket
    assert "null_resource" in queue
