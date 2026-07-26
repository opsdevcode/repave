from __future__ import annotations

from pathlib import Path

from repave_engine.gates import run_gates

_COMPLIANT_TAGS = '["service:svc","team:platform","org:plat","env:prod","managed-by:repave"]'


def test_datadog_dashboard_passes_valid_json(tmp_path: Path) -> None:
    dash_dir = tmp_path / "datadog" / "dashboards"
    dash_dir.mkdir(parents=True)
    (dash_dir / "overview.json").write_text(
        f'{{"title":"svc","layout_type":"ordered","tags":{_COMPLIANT_TAGS},'
        '"widgets":[{"definition":{"type":"note","content":"hi"}}]}\n',
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("datadog-dashboard",))

    assert results[0].passed is True
    assert results[0].skipped is False


def test_datadog_dashboard_fails_empty_widgets(tmp_path: Path) -> None:
    dash_dir = tmp_path / "datadog" / "dashboards"
    dash_dir.mkdir(parents=True)
    (dash_dir / "bad.json").write_text(
        f'{{"title":"svc","layout_type":"ordered","tags":{_COMPLIANT_TAGS},"widgets":[]}}\n',
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("datadog-dashboard",))

    assert results[0].passed is False
    assert "widgets" in results[0].message


def test_datadog_dashboard_skips_when_no_files(tmp_path: Path) -> None:
    results = run_gates(tmp_path, ("datadog-dashboard",))

    assert results[0].passed is True
    assert results[0].skipped is True
