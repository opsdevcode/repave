"""Prometheus metrics for generation operations and DX outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from prometheus_client import Counter, Gauge, Histogram

if TYPE_CHECKING:
    from repave_engine.dx_metrics import DxMetricsSnapshot

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
JSONL_APPEND_FAILURES = Counter(
    "repave_jsonl_append_failures_total",
    "Failed append-only JSONL store writes",
    ["store"],
)
GOLDEN_PATH_ADOPTION_RATIO = Gauge(
    "repave_golden_path_adoption_ratio",
    "Governed repositories over eligible repositories",
)
PLAN_APPLY_CONVERSION_RATIO = Gauge(
    "repave_plan_apply_conversion_ratio",
    "Apply count over plan (dry-run) count from audit",
)
TIME_TO_FIRST_ARTIFACT_SECONDS = Gauge(
    "repave_dx_time_to_first_artifact_seconds",
    "p50 seconds from first audit event to first successful apply per user",
)
FINOPS_FLEET_ACTUAL_30D_USD = Gauge(
    "repave_finops_fleet_actual_30d_usd",
    "Sum of latest L30D actuals across catalog entities with cost data",
)
FINOPS_FLEET_BUDGET_MONTHLY_USD = Gauge(
    "repave_finops_fleet_budget_monthly_usd",
    "Sum of configured monthly budgets across catalog entities",
)
FINOPS_OVER_BUDGET_ENTITIES = Gauge(
    "repave_finops_over_budget_entities",
    "Catalog entities whose L30D actual exceeds monthly budget",
)


def record_jsonl_append_failure(store: str) -> None:
    JSONL_APPEND_FAILURES.labels(store=store).inc()


def record_run_queue_depth(depth: int) -> None:
    RUN_QUEUE_GAUGE.set(depth)


def record_run_terminal(outcome: str, blueprint: str) -> None:
    RUNS_TOTAL.labels(outcome=outcome, blueprint=blueprint).inc()


def record_dx_metrics(snapshot: DxMetricsSnapshot) -> None:
    if snapshot.adoption_ratio is not None:
        GOLDEN_PATH_ADOPTION_RATIO.set(snapshot.adoption_ratio)
    if snapshot.plan_apply_ratio is not None:
        PLAN_APPLY_CONVERSION_RATIO.set(snapshot.plan_apply_ratio)
    if snapshot.time_to_first_artifact_seconds_p50 is not None:
        TIME_TO_FIRST_ARTIFACT_SECONDS.set(snapshot.time_to_first_artifact_seconds_p50)


def record_finops_rollup(rollup: object) -> None:
    from repave_engine.finops_rollup import FinOpsRollup

    if not isinstance(rollup, FinOpsRollup):
        return
    FINOPS_FLEET_ACTUAL_30D_USD.set(rollup.total_actual_30d)
    FINOPS_FLEET_BUDGET_MONTHLY_USD.set(rollup.total_budget_monthly)
    FINOPS_OVER_BUDGET_ENTITIES.set(rollup.over_budget_count)
