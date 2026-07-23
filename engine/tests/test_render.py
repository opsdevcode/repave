from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.render import collect_rendered_files, render_blueprint


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
