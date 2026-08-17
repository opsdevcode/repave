from __future__ import annotations

from pathlib import Path


def test_component_stubs_emit_cloud_resources(repo_root: Path) -> None:
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
    assert "iam_database_authentication_enabled" in rds
    assert "aws_db_parameter_group" in rds
    assert "rds.force_ssl" in rds
    assert "aws_default_security_group" in rds
    assert "aws_s3_bucket" in bucket
    assert "aws_s3_bucket_ownership_controls" in bucket
    assert "aws_sqs_queue" in queue
    assert "azurerm_postgresql_flexible_server" in rds
    assert "google_sql_database_instance" in rds
    assert "azurerm_storage_account" in bucket
    assert "google_storage_bucket" in bucket
    assert "azurerm_servicebus_queue" in queue
    assert "google_pubsub_topic" in queue
    assert "null_resource" not in rds
    assert "null_resource" not in bucket
    assert "null_resource" not in queue
