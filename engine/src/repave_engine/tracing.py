"""OpenTelemetry hooks (no-op when exporter is not configured)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager


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
