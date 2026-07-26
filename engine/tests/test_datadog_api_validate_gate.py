from __future__ import annotations

from pathlib import Path

from repave_engine.gates import run_gates


def test_datadog_api_validate_skips_without_credentials(tmp_path: Path, monkeypatch) -> None:
    monitors = tmp_path / "datadog" / "monitors"
    monitors.mkdir(parents=True)
    (monitors / "sample.json").write_text(
        '[{"name": "x", "type": "metric alert", "query": "avg:1", "message": "hi", '
        '"tags": ["managed-by:repave"]}]',
        encoding="utf-8",
    )
    monkeypatch.delenv("DD_API_KEY", raising=False)
    monkeypatch.delenv("DD_APP_KEY", raising=False)

    results = run_gates(tmp_path, ("datadog-api-validate",))

    assert results[0].passed is True
    assert results[0].skipped is True
    assert "DD_API_KEY" in results[0].message


def test_datadog_api_validate_calls_monitor_endpoint(tmp_path: Path, monkeypatch) -> None:
    monitors = tmp_path / "datadog" / "monitors"
    monitors.mkdir(parents=True)
    (monitors / "sample.json").write_text(
        '[{"name": "x", "type": "metric alert", "query": "avg:1", "message": "hi", '
        '"tags": ["managed-by:repave"]}]',
        encoding="utf-8",
    )
    monkeypatch.setenv("DD_API_KEY", "test-key")
    monkeypatch.setenv("DD_APP_KEY", "test-app")

    captured: dict[str, str] = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        return FakeResponse()

    monkeypatch.setattr("repave_engine.gate_runners.httpx.post", fake_post)

    results = run_gates(tmp_path, ("datadog-api-validate",))

    assert results[0].passed is True
    assert "/api/v1/monitor/validate" in captured["url"]
