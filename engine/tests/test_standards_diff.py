from __future__ import annotations

from pathlib import Path

from repave_engine.standards_diff import standards_diff_for_pin


def test_standards_diff_for_pin_on_repo(repo_root: Path) -> None:
    result = standards_diff_for_pin(
        repo_root,
        standard_source="standards/terraform-standards",
        pinned_version="1.1.0",
    )
    assert result.standard_source == "standards/terraform-standards"
    assert result.pinned_version == "1.1.0"
    if result.available:
        assert result.baseline_ref
    else:
        assert result.reason


def test_standards_diff_missing_path(repo_root: Path) -> None:
    result = standards_diff_for_pin(
        repo_root,
        standard_source="standards/does-not-exist",
        pinned_version="1.0.0",
    )
    assert not result.available
    assert "not found" in result.reason.lower()
