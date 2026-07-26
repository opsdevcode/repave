"""Prometheus metrics for generation operations."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

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
