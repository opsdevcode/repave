from __future__ import annotations

from pathlib import Path

from repave_engine.blueprint import load_blueprint
from repave_engine.provenance_inputs import load_provenance_document
from repave_engine.standards_diff import diff_observed_vs_catalog_pins, standards_diff_for_pin


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


def test_diff_observed_vs_catalog_for_terraform_minimal_fixture(repo_root: Path) -> None:
    fixture = repo_root / "operator" / "testdata" / "modules" / "terraform-minimal"
    doc = load_provenance_document(fixture / "repave.yaml")
    blueprint = load_blueprint(
        repo_root / "blueprints" / "terraform-module-generic",
        repo_root,
    )
    changes = diff_observed_vs_catalog_pins(doc, blueprint)
    fields = {row.field for row in changes}
    assert "Blueprint version" in fields
    version_row = next(row for row in changes if row.field == "Blueprint version")
    assert version_row.before == "0.9.0"
    assert version_row.after == blueprint.version
