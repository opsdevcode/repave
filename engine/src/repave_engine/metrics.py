"""Prometheus metrics for generation operations."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

GENERATION_TOTAL = Counter(
    "repave_generations_total",
    "Blueprint generations",
    ["outcome", "blueprint"],
)
GENERATION_DURATION = Histogram(
    "repave_generation_seconds",
    "Wall time for generate_from_blueprint",
    ["blueprint"],
)
RUN_QUEUE_GAUGE = Gauge(
    "repave_run_queue_inflight",
    "Queued plus running async generation runs",
)
RUNS_TOTAL = Counter(
    "repave_async_runs_total",
    "Async generation runs by terminal outcome",
    ["outcome", "blueprint"],
)


def record_run_queue_depth(depth: int) -> None:
    RUN_QUEUE_GAUGE.set(depth)


def record_run_terminal(outcome: str, blueprint: str) -> None:
    RUNS_TOTAL.labels(outcome=outcome, blueprint=blueprint).inc()
