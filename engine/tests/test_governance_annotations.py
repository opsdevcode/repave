from __future__ import annotations

from repave_engine.governance_annotations import (
    annotate_file_lines,
    build_governance_previews,
    render_annotated_lines_html,
)
from repave_engine.policy_catalog import PolicyRule
from repave_engine.standards_diff import StandardsDiffResult


def test_annotate_markdown_section_and_policy_keyword() -> None:
    text = """## Module contract

- Include native Terraform tests under `tests/`.
- Place shared module locals in `locals.tf`.
"""
    rules = (
        PolicyRule(
            id="checkov:CKV2_REPAVE_3",
            family="checkov",
            title="Module must include locals.tf for shared derived values",
            artifact_types=("terraform-module",),
            required=False,
            removable=True,
            checkov_id="CKV2_REPAVE_3",
        ),
    )
    lines = annotate_file_lines(
        text,
        relative_path="standards/terraform-standards/terraform-standards.md",
        policy_rules=rules,
    )
    locals_line = next(line for line in lines if "locals.tf" in line.text)
    assert any(marker.kind == "policy" for marker in locals_line.markers)
    assert any(marker.kind == "standard" for marker in locals_line.markers)
    html = render_annotated_lines_html(lines)
    assert "gov-marker--policy" in html
    assert "locals.tf" in html


def test_build_governance_previews_when_pin_matches_head(repo_root) -> None:
    standards = StandardsDiffResult(
        available=True,
        pinned_version="1.1.0",
        standard_source="standards/terraform-standards",
        baseline_commit="abc123",
        baseline_ref="abc123",
        reason="",
        files=(),
    )
    previews = build_governance_previews(repo_root, standards, ())
    assert previews
    assert any("standards/terraform-standards" in preview.path for preview in previews)
