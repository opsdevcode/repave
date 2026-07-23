from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.render import (
    build_scoped_resources,
    collect_rendered_files,
    render_blueprint,
)


def test_render_blueprint_writes_output(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path)
    output_dir = tmp_path / "out" / "example"

    result = render_blueprint(
        blueprint,
        {"module_name": "example", "description": "Rendered in test"},
        output_dir,
    )

    readme = result.output_dir / "README.md"
    assert readme.exists()
    assert "example" in readme.read_text(encoding="utf-8")
    assert result.values["_repave_blueprint_name"] == blueprint.name


def test_render_unsupported_engine(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, template_engine="helm")

    with pytest.raises(ValueError, match="Unsupported template engine"):
        render_blueprint(
            blueprint,
            {"module_name": "example", "description": "test"},
            tmp_path / "out",
        )


def test_render_missing_template_dir(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, create_template=False)

    with pytest.raises(FileNotFoundError, match="Template directory not found"):
        render_blueprint(
            blueprint,
            {"module_name": "example", "description": "test"},
            tmp_path / "out",
        )


def test_render_refuses_existing_output_without_overwrite(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path)
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    with pytest.raises(FileExistsError, match="Output directory already exists"):
        render_blueprint(
            blueprint,
            {"module_name": "example", "description": "test"},
            output_dir,
            overwrite=False,
        )


def test_build_scoped_resources_flattens_scope() -> None:
    scope = '{"ec2":{"resources":["diff","id"]},"s3":{"resources":["bucket","object"]}}'
    items = build_scoped_resources(scope)

    assert [item.file_stem for item in items] == [
        "ec2_diff",
        "ec2_id",
        "s3_bucket",
        "s3_object",
    ]


def test_render_writes_scoped_resource_files(
    terraform_blueprint,
    sample_inputs,
    tmp_path: Path,
) -> None:
    from repave_engine.blueprint import validate_inputs

    values = validate_inputs(terraform_blueprint, sample_inputs)
    output_dir = tmp_path / "module"

    render_blueprint(terraform_blueprint, values, output_dir)

    assert (output_dir / "locals.tf").exists()
    assert (output_dir / "ec2_diff.tf").exists()
    assert (output_dir / "s3_bucket.tf").exists()
    assert not (output_dir / "main.tf").exists()
    assert not (output_dir / "ec2.tf").exists()
    assert not (output_dir / "s3.tf").exists()
    variables = (output_dir / "variables.tf").read_text(encoding="utf-8")
    assert 'variable "provider_service_scope"' not in variables
    ec2_diff = (output_dir / "ec2_diff.tf").read_text(encoding="utf-8")
    assert 'null_resource" "ec2_diff"' in ec2_diff
    assert "ec2 — diff" in ec2_diff
    assert "local.common_tags" in ec2_diff
    assert "local.name_prefix" in ec2_diff
    locals_tf = (output_dir / "locals.tf").read_text(encoding="utf-8")
    assert "common_tags = merge(" in locals_tf
    assert "sort(distinct(var.provider_services))" in locals_tf
    assert "name_prefix" in locals_tf
    outputs = (output_dir / "outputs.tf").read_text(encoding="utf-8")
    assert "null_resource.ec2_diff.id" in outputs
    assert "null_resource.s3_bucket.id" in outputs


def test_collect_rendered_files_returns_text_files(tmp_path: Path) -> None:
    output_dir = tmp_path / "module"
    output_dir.mkdir()
    (output_dir / "main.tf").write_text('resource "null_resource" "x" {}\n', encoding="utf-8")
    (output_dir / "README.md").write_text("# Example\n", encoding="utf-8")
    (output_dir / "image.bin").write_bytes(b"\0binary")

    files = collect_rendered_files(output_dir)

    paths = {item.path for item in files}
    assert "main.tf" in paths
    assert "README.md" in paths
    assert "image.bin" not in paths


def test_collect_rendered_files_marks_truncated_content(tmp_path: Path) -> None:
    output_dir = tmp_path / "module"
    output_dir.mkdir()
    (output_dir / "large.txt").write_text("a" * 40_000, encoding="utf-8")

    files = collect_rendered_files(output_dir, max_bytes=1024)

    assert len(files) == 1
    assert files[0].truncated is True
    assert len(files[0].content) == 1024


def test_collect_rendered_files_excludes_gate_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "module"
    output_dir.mkdir()
    (output_dir / "main.tf").write_text("# module\n", encoding="utf-8")
    terraform_dir = output_dir / ".terraform" / "providers" / "hashicorp" / "aws"
    terraform_dir.mkdir(parents=True)
    (terraform_dir / "LICENSE.txt").write_text("provider license\n", encoding="utf-8")

    paths = {item.path for item in collect_rendered_files(output_dir)}

    assert paths == {"main.tf"}
