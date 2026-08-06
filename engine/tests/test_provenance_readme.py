from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint, validate_inputs
from repave_engine.provenance_readme import (
    provenance_section_markdown,
    sync_readme_provenance_section,
)


def test_provenance_section_markdown_includes_blueprint_and_repave_yaml(
    repo_root: Path,
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "chart_name": "api",
            "app_name": "api",
            "owner": "platform-engineering",
            "description": "API chart",
            "image_repository": "ghcr.io/acme/api",
        },
    )
    section = provenance_section_markdown(blueprint, values)

    assert section.startswith("## Provenance\n")
    assert "helm-chart-generic" in section
    assert "repave.yaml" in section


def test_sync_readme_provenance_section_replaces_existing_block(
    tmp_path: Path, repo_root: Path
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "chart_name": "api",
            "app_name": "api",
            "owner": "platform-engineering",
            "description": "API chart",
            "image_repository": "ghcr.io/acme/api",
        },
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        "# api\n\n## Usage\n\nExample.\n\n## Provenance\n\nOld placeholder.\n",
        encoding="utf-8",
    )

    sync_readme_provenance_section(tmp_path, blueprint, values)
    text = readme.read_text(encoding="utf-8")

    assert "Old placeholder" not in text
    assert text.count("## Provenance") == 1
    assert "helm-chart-generic" in text


def test_sync_readme_provenance_section_appends_when_missing(
    tmp_path: Path, repo_root: Path
) -> None:
    blueprint = load_blueprint(
        repo_root / "blueprints" / "helm-chart-generic",
        repo_root=repo_root,
    )
    values = validate_inputs(
        blueprint,
        {
            "chart_name": "api",
            "app_name": "api",
            "owner": "platform-engineering",
            "description": "API chart",
            "image_repository": "ghcr.io/acme/api",
        },
    )
    readme = tmp_path / "README.md"
    readme.write_text("# api\n\n## Usage\n\nExample.\n", encoding="utf-8")

    sync_readme_provenance_section(tmp_path, blueprint, values)
    text = readme.read_text(encoding="utf-8")

    assert "## Provenance" in text
    assert "helm-chart-generic" in text
