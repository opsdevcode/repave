from __future__ import annotations

from pathlib import Path

from repave_engine.gates import run_gates

_COMPLIANT_TAGS = '["service:svc","team:platform","org:plat","env:prod","managed-by:repave"]'


def test_grafana_dashboard_passes_valid_json(tmp_path: Path) -> None:
    dash_dir = tmp_path / "grafana" / "dashboards"
    dash_dir.mkdir(parents=True)
    (dash_dir / "overview.json").write_text(
        f'{{"title":"svc","uid":"svc_overview","schemaVersion":39,"tags":{_COMPLIANT_TAGS}}}\n',
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("grafana-dashboard",))

    assert results[0].passed is True
    assert results[0].skipped is False
    assert "validated" in results[0].message


def test_grafana_dashboard_fails_missing_tags(tmp_path: Path) -> None:
    dash_dir = tmp_path / "grafana" / "dashboards"
    dash_dir.mkdir(parents=True)
    (dash_dir / "bad.json").write_text(
        '{"title":"svc","uid":"svc_overview","schemaVersion":39,"tags":[]}\n',
        encoding="utf-8",
    )

    results = run_gates(tmp_path, ("grafana-dashboard",))

    assert results[0].passed is False
    assert "service:" in results[0].message


def test_grafana_dashboard_skips_when_no_files(tmp_path: Path) -> None:
    results = run_gates(tmp_path, ("grafana-dashboard",))

    assert results[0].passed is True
    assert results[0].skipped is True
