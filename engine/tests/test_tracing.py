"""Tests for OpenTelemetry tracing configuration."""

from __future__ import annotations

import pytest

from repave_engine.settings import TracingConfig
from repave_engine.tracing import (
    _normalize_otlp_traces_endpoint,
    configure_tracing,
    pipeline_span,
    reset_tracing_for_tests,
    tracing_configured,
)


def test_normalize_otlp_traces_endpoint_appends_path() -> None:
    assert _normalize_otlp_traces_endpoint("http://localhost:4318") == (
        "http://localhost:4318/v1/traces"
    )
    assert (
        _normalize_otlp_traces_endpoint("http://localhost:4318/v1/traces")
        == "http://localhost:4318/v1/traces"
    )


def test_configure_tracing_no_config() -> None:
    reset_tracing_for_tests()
    assert configure_tracing(None) is False
    assert tracing_configured() is False


def test_configure_tracing_with_otel_extra() -> None:
    pytest.importorskip("opentelemetry.sdk.trace")
    reset_tracing_for_tests()
    try:
        ok = configure_tracing(
            TracingConfig(
                enabled=True,
                otlp_endpoint="http://127.0.0.1:4318",
                service_name="test-repave",
            )
        )
        assert ok is True
        assert tracing_configured() is True
    finally:
        reset_tracing_for_tests()


def test_pipeline_span_no_op_without_provider() -> None:
    reset_tracing_for_tests()
    with pipeline_span("test.stage"):
        pass
