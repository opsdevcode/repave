"""Tests for load_tracing_config."""

from __future__ import annotations

from repave_engine.settings import load_tracing_config


def test_load_tracing_config_from_env(monkeypatch, repo_root) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://collector:4318/v1/traces")
    monkeypatch.setenv("OTEL_SERVICE_NAME", "repave-test")
    cfg = load_tracing_config(repo_root)
    assert cfg is not None
    assert cfg.otlp_endpoint == "http://collector:4318/v1/traces"
    assert cfg.service_name == "repave-test"


def test_load_tracing_config_disabled_without_endpoint(repo_root, monkeypatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.delenv("REPAVE_OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert load_tracing_config(repo_root) is None
