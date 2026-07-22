from __future__ import annotations

from pathlib import Path

import pytest

from helpers import make_blueprint
from repave_engine.render import render_blueprint


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
