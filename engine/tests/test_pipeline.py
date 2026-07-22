from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint
from repave_engine.pipeline import generate_from_blueprint


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generate_terraform_module_generic(tmp_path: Path) -> None:
    blueprint = load_blueprint(
        REPO_ROOT / "blueprints" / "terraform-module-generic",
        REPO_ROOT,
    )

    result = generate_from_blueprint(
        blueprint,
        {
            "module_name": "example",
            "description": "Example module generated in tests",
        },
        output_root=tmp_path,
        dry_run=True,
    )

    output_dir = result.render.output_dir
    assert output_dir.exists()
    assert (output_dir / "main.tf").exists()
    assert (output_dir / "README.md").exists()
    assert "example" in (output_dir / "README.md").read_text(encoding="utf-8")
    assert result.pr_plan is not None
    assert all(g.passed or g.skipped for g in result.gates)
