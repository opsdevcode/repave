"""OpenTelemetry pipeline spans (no-op until SDK + OTLP endpoint are configured)."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from repave_engine.settings import TracingConfig

_tracing_configured = False


def _normalize_otlp_traces_endpoint(endpoint: str) -> str:
    cleaned = endpoint.strip().rstrip("/")
    if cleaned.endswith("/v1/traces"):
        return cleaned
    parsed = urlparse(cleaned)
    if parsed.path and parsed.path not in ("", "/"):
        return cleaned
    return f"{cleaned}/v1/traces"


def configure_tracing(config: TracingConfig | None = None) -> bool:
    """Install a TracerProvider with OTLP HTTP export when the otel extra is installed."""
    global _tracing_configured
    if _tracing_configured:
        return True
    if config is None or not config.enabled or not config.otlp_endpoint.strip():
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return False

    endpoint = _normalize_otlp_traces_endpoint(config.otlp_endpoint)
    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracing_configured = True
    return True


def tracing_configured() -> bool:
    return _tracing_configured


def reset_tracing_for_tests() -> None:
    """Clear provider state between tests (internal)."""
    global _tracing_configured
    _tracing_configured = False
    try:
        from opentelemetry import trace

        trace.set_tracer_provider(trace.NoOpTracerProvider())
    except ImportError:
        pass


@contextmanager
def pipeline_span(name: str) -> Iterator[None]:
    try:
        from opentelemetry import trace
    except ImportError:
        yield
        return

    tracer = trace.get_tracer("repave.engine")
    with tracer.start_as_current_span(name):
        yield


def span(name: str) -> AbstractContextManager[None]:
    return pipeline_span(name)


def init_tracing_from_env() -> bool:
    """Configure from OTEL_* env vars only (CLI/serve bootstrap)."""
    endpoint = (
        os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
        or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
        or os.environ.get("REPAVE_OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    )
    if not endpoint:
        return False
    from repave_engine.settings import TracingConfig

    service = os.environ.get("OTEL_SERVICE_NAME", "").strip() or os.environ.get(
        "REPAVE_OTEL_SERVICE_NAME", "repave-engine"
    )
    return configure_tracing(
        TracingConfig(enabled=True, otlp_endpoint=endpoint, service_name=service)
    )
