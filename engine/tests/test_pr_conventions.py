from __future__ import annotations

from pathlib import Path

import pytest

from repave_engine.gate_registry import GateResult
from repave_engine.pr_conventions import (
    branch_name,
    load_pull_request_conventions,
    render_evidence_checklist,
)


def test_load_pull_request_conventions_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REPAVE_PR_LABELS", raising=False)
    monkeypatch.delenv("REPAVE_PR_BRANCH_PREFIX_UPGRADE", raising=False)
    monkeypatch.delenv("REPAVE_PR_EVIDENCE_CHECKLIST", raising=False)
    conventions = load_pull_request_conventions(tmp_path)
    assert conventions.branch_prefix_upgrade == "repave/upgrade"
    assert conventions.labels == ("repave", "governed")
    assert conventions.evidence_checklist is True


def test_load_pull_request_conventions_from_config(repo_root: Path, tmp_path: Path) -> None:
    config = tmp_path / "repave.config.yaml"
    config.write_text(
        """
pull_requests:
  branch_prefix:
    upgrade: acme/repave-upgrade
    import: acme/repave-import
  labels: [repave, platform]
  evidence_checklist: false
""".strip(),
        encoding="utf-8",
    )
    conventions = load_pull_request_conventions(tmp_path)
    assert conventions.branch_prefix_upgrade == "acme/repave-upgrade"
    assert conventions.labels == ("repave", "platform")
    assert conventions.evidence_checklist is False


def test_branch_name_sanitizes_segments() -> None:
    assert branch_name("repave/upgrade", "terraform-minimal", "1.2.3") == (
        "repave/upgrade/terraform-minimal-1.2.3"
    )


def test_render_evidence_checklist_marks_gate_states() -> None:
    body = render_evidence_checklist(
        (
            GateResult(name="checkov", passed=True, skipped=False, message="ok"),
            GateResult(name="opa", passed=False, skipped=False, message="deny"),
            GateResult(name="fmt", passed=False, skipped=True, message="missing"),
        )
    )
    assert "[x] `checkov` (passed)" in body
    assert "[ ] `opa` (failed)" in body
    assert "[~] `fmt` (skipped)" in body


def test_render_evidence_checklist_annotates_cost_estimate() -> None:
    body = render_evidence_checklist(
        (
            GateResult(
                name="infracost",
                passed=True,
                skipped=False,
                message="Estimated USD 42.00/month across 2 resource(s)",
            ),
        )
    )
    assert "**Cost estimate:** Estimated USD 42.00/month across 2 resource(s)" in body


def test_load_pull_request_conventions_rejects_invalid_block(
    repo_root: Path, tmp_path: Path
) -> None:
    (tmp_path / "repave.config.yaml").write_text("pull_requests: bad\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_pull_request_conventions(tmp_path)
