from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import Blueprint, InputField


def make_blueprint(
    tmp_path: Path,
    *,
    name: str = "test-blueprint",
    template_engine: str = "copier",
    gates: tuple[str, ...] = ("docs-drift",),
    inputs: tuple[InputField, ...] | None = None,
    create_template: bool = True,
) -> Blueprint:
    bp_path = tmp_path / name
    template_rel = "template"

    if create_template:
        template_dir = bp_path / template_rel
        template_dir.mkdir(parents=True)
        (template_dir / "copier.yaml").write_text(
            "\n".join(
                [
                    '_min_copier_version: "9.0.0"',
                    "_templates_suffix: .jinja",
                    "_exclude:",
                    "  - copier.yaml",
                    "module_name:",
                    "  type: str",
                    "description:",
                    "  type: str",
                ]
            ),
            encoding="utf-8",
        )
        (template_dir / "README.md.jinja").write_text(
            "# {{ module_name }}\n\n{{ description }}\n\n## Usage\n\nExample usage.\n",
            encoding="utf-8",
        )

    if inputs is None:
        inputs = (
            InputField("module_name", "string", True, "Module name"),
            InputField("description", "string", True, "Module description"),
        )

    return Blueprint(
        path=bp_path,
        name=name,
        version="0.0.1",
        description="Test blueprint",
        standard_source="examples/standards",
        standard_version="0.1.0",
        inputs=inputs,
        template_engine=template_engine,
        template_path=template_rel,
        gates=gates,
        output_type="pull_request",
        output_target="repo",
    )
