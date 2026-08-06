"""Golden-path adoption and developer-experience outcome metrics.

Pure, framework-free core. Handlers/CLI/CronJobs orchestrate I/O; this module
computes frozen result objects from already-loaded audit, fleet, and eligible
repo sets.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.fleet import FleetEntry, normalize_repo_url
from repave_engine.github_inventory import GitHubInventoryError


@dataclass(frozen=True)
class FunnelStep:
    name: str
    count: int


@dataclass(frozen=True)
class BlueprintFunnel:
    blueprint_name: str
    plans: int
    applies: int
    passed_applies: int
    conversion_ratio: float


@dataclass(frozen=True)
class BlueprintFriction:
    blueprint_name: str
    total: int
    failed: int
    fail_ratio: float


@dataclass(frozen=True)
class DxMetricsSnapshot:
    """Point-in-time platform outcome metrics."""

    captured_at: str
    audit_available: bool
    fleet_enabled: bool
    eligible_count: int
    governed_count: int
    adoption_ratio: float | None
    bypass_repos: tuple[str, ...]
    plan_count: int
    apply_count: int
    plan_apply_ratio: float | None
    funnels: tuple[BlueprintFunnel, ...]
    time_to_first_artifact_seconds_p50: float | None
    time_to_first_artifact_seconds_p90: float | None
    service_creation_seconds_p50: float | None
    service_creation_seconds_p90: float | None
    friction: tuple[BlueprintFriction, ...]
    baseline_adoption_ratio: float | None = None
    baseline_plan_apply_ratio: float | None = None
    eligible_source: str = "fleet"
    message: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "captured_at": self.captured_at,
            "audit_available": self.audit_available,
            "fleet_enabled": self.fleet_enabled,
            "eligible_count": self.eligible_count,
            "governed_count": self.governed_count,
            "adoption_ratio": self.adoption_ratio,
            "bypass_repos": list(self.bypass_repos),
            "plan_count": self.plan_count,
            "apply_count": self.apply_count,
            "plan_apply_ratio": self.plan_apply_ratio,
            "funnels": [
                {
                    "blueprint_name": item.blueprint_name,
                    "plans": item.plans,
                    "applies": item.applies,
                    "passed_applies": item.passed_applies,
                    "conversion_ratio": item.conversion_ratio,
                }
                for item in self.funnels
            ],
            "time_to_first_artifact_seconds_p50": self.time_to_first_artifact_seconds_p50,
            "time_to_first_artifact_seconds_p90": self.time_to_first_artifact_seconds_p90,
            "service_creation_seconds_p50": self.service_creation_seconds_p50,
            "service_creation_seconds_p90": self.service_creation_seconds_p90,
            "friction": [
                {
                    "blueprint_name": item.blueprint_name,
                    "total": item.total,
                    "failed": item.failed,
                    "fail_ratio": item.fail_ratio,
                }
                for item in self.friction
            ],
            "baseline_adoption_ratio": self.baseline_adoption_ratio,
            "baseline_plan_apply_ratio": self.baseline_plan_apply_ratio,
            "eligible_source": self.eligible_source,
            "message": self.message,
        }


def _safe_ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def _parse_ts(raw: str) -> datetime | None:
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _percentile(sorted_values: list[float], pct: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return round(sorted_values[0], 3)
    index = round((pct / 100.0) * (len(sorted_values) - 1))
    index = max(0, min(index, len(sorted_values) - 1))
    return round(sorted_values[index], 3)


def compute_adoption(
    *,
    governed_urls: Sequence[str],
    eligible_urls: Sequence[str],
) -> tuple[float | None, tuple[str, ...], int, int]:
    """Return adoption_ratio, bypass_repos, eligible_count, governed_count."""
    governed = {normalize_repo_url(url) for url in governed_urls if url.strip()}
    eligible = {normalize_repo_url(url) for url in eligible_urls if url.strip()}
    if not eligible and governed:
        # No external denominator configured — treat fleet as the known universe.
        eligible = set(governed)
    bypass = tuple(sorted(url for url in eligible if url not in governed))
    governed_in_eligible = len(eligible & governed) if eligible else len(governed)
    eligible_count = len(eligible) if eligible else len(governed)
    return (
        _safe_ratio(governed_in_eligible, eligible_count),
        bypass,
        eligible_count,
        len(governed),
    )


def compute_plan_apply_funnels(
    entries: Sequence[AuditHistoryEntry],
) -> tuple[int, int, float | None, tuple[BlueprintFunnel, ...]]:
    by_blueprint: dict[str, list[int]] = {}
    plan_total = 0
    apply_total = 0
    for entry in entries:
        name = entry.blueprint_name or "unknown"
        stats = by_blueprint.setdefault(name, [0, 0, 0])
        if entry.dry_run:
            stats[0] += 1
            plan_total += 1
        else:
            stats[1] += 1
            apply_total += 1
            if entry.gates_outcome == "passed":
                stats[2] += 1
    funnels = tuple(
        sorted(
            (
                BlueprintFunnel(
                    blueprint_name=name,
                    plans=counts[0],
                    applies=counts[1],
                    passed_applies=counts[2],
                    conversion_ratio=_safe_ratio(counts[1], counts[0]) or 0.0,
                )
                for name, counts in by_blueprint.items()
            ),
            key=lambda item: (-item.plans, item.blueprint_name),
        )
    )
    return plan_total, apply_total, _safe_ratio(apply_total, plan_total), funnels


def compute_time_to_first_artifact(
    entries: Sequence[AuditHistoryEntry],
) -> tuple[float | None, float | None]:
    """Per acting_user: first seen → first successful apply (seconds)."""
    first_seen: dict[str, datetime] = {}
    first_success: dict[str, datetime] = {}
    # entries are newest-first from audit_history; walk oldest→newest
    chronological = list(reversed(entries))
    for entry in chronological:
        user = entry.acting_user or "unknown"
        ts = _parse_ts(entry.timestamp)
        if ts is None:
            continue
        if user not in first_seen:
            first_seen[user] = ts
        if user not in first_success and not entry.dry_run and entry.gates_outcome == "passed":
            first_success[user] = ts
    durations = sorted(
        (first_success[user] - first_seen[user]).total_seconds()
        for user in first_success
        if user in first_seen and first_success[user] >= first_seen[user]
    )
    return _percentile(durations, 50), _percentile(durations, 90)


def compute_service_creation_times(
    entries: Sequence[AuditHistoryEntry],
) -> tuple[float | None, float | None]:
    """p50/p90 of apply duration_seconds from audit extra, falling back to median of available."""
    durations: list[float] = []
    for entry in entries:
        if entry.dry_run or entry.gates_outcome != "passed":
            continue
        raw = entry.extra.get("duration_seconds")
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if value >= 0:
            durations.append(value)
    durations.sort()
    if not durations:
        return None, None
    p50 = round(float(median(durations)), 3)
    return p50, _percentile(durations, 90)


def compute_gate_friction(
    entries: Sequence[AuditHistoryEntry],
    *,
    limit: int = 10,
) -> tuple[BlueprintFriction, ...]:
    by_blueprint: dict[str, list[int]] = {}
    for entry in entries:
        name = entry.blueprint_name or "unknown"
        stats = by_blueprint.setdefault(name, [0, 0])
        stats[0] += 1
        if entry.gates_outcome == "failed":
            stats[1] += 1
    friction = [
        BlueprintFriction(
            blueprint_name=name,
            total=counts[0],
            failed=counts[1],
            fail_ratio=_safe_ratio(counts[1], counts[0]) or 0.0,
        )
        for name, counts in by_blueprint.items()
        if counts[1] > 0
    ]
    friction.sort(key=lambda item: (-item.fail_ratio, -item.failed, item.blueprint_name))
    return tuple(friction[:limit])


def build_dx_metrics_snapshot(
    *,
    captured_at: str,
    fleet_entries: Sequence[FleetEntry],
    eligible_urls: Sequence[str],
    audit_entries: Sequence[AuditHistoryEntry] | None,
    audit_available: bool,
    fleet_enabled: bool,
    eligible_source: str = "fleet",
    baseline_adoption_ratio: float | None = None,
    baseline_plan_apply_ratio: float | None = None,
    message: str = "",
) -> DxMetricsSnapshot:
    governed_urls = [entry.repo_url for entry in fleet_entries]
    adoption_ratio, bypass, eligible_count, governed_count = compute_adoption(
        governed_urls=governed_urls,
        eligible_urls=eligible_urls,
    )
    entries = tuple(audit_entries or ())
    if not audit_available:
        return DxMetricsSnapshot(
            captured_at=captured_at,
            audit_available=False,
            fleet_enabled=fleet_enabled,
            eligible_count=eligible_count,
            governed_count=governed_count,
            adoption_ratio=adoption_ratio,
            bypass_repos=bypass,
            plan_count=0,
            apply_count=0,
            plan_apply_ratio=None,
            funnels=(),
            time_to_first_artifact_seconds_p50=None,
            time_to_first_artifact_seconds_p90=None,
            service_creation_seconds_p50=None,
            service_creation_seconds_p90=None,
            friction=(),
            baseline_adoption_ratio=baseline_adoption_ratio,
            baseline_plan_apply_ratio=baseline_plan_apply_ratio,
            eligible_source=eligible_source,
            message=message
            or "Audit is disabled — funnel and time-to-first-artifact require audit.enabled.",
        )

    plan_count, apply_count, plan_apply_ratio, funnels = compute_plan_apply_funnels(entries)
    ttf_p50, ttf_p90 = compute_time_to_first_artifact(entries)
    create_p50, create_p90 = compute_service_creation_times(entries)
    friction = compute_gate_friction(entries)
    return DxMetricsSnapshot(
        captured_at=captured_at,
        audit_available=True,
        fleet_enabled=fleet_enabled,
        eligible_count=eligible_count,
        governed_count=governed_count,
        adoption_ratio=adoption_ratio,
        bypass_repos=bypass,
        plan_count=plan_count,
        apply_count=apply_count,
        plan_apply_ratio=plan_apply_ratio,
        funnels=funnels,
        time_to_first_artifact_seconds_p50=ttf_p50,
        time_to_first_artifact_seconds_p90=ttf_p90,
        service_creation_seconds_p50=create_p50,
        service_creation_seconds_p90=create_p90,
        friction=friction,
        baseline_adoption_ratio=baseline_adoption_ratio,
        baseline_plan_apply_ratio=baseline_plan_apply_ratio,
        eligible_source=eligible_source,
        message=message,
    )


def collect_eligible_repo_urls(
    *,
    github_orgs: Sequence[str],
    github_topics: Sequence[str],
    token: str | None,
    search_limit: int = 100,
    search_fn: Any | None = None,
) -> tuple[tuple[str, ...], str, str]:
    """Return (urls, eligible_source, message).

    When no orgs/topics or no token, returns empty urls and source ``fleet`` so
    callers fall back to the governed set as the universe.
    """
    if not github_orgs and not github_topics:
        return (), "fleet", "No github_orgs/github_topics configured — eligible set equals fleet."
    if not token:
        return (
            (),
            "fleet",
            "GitHub token not configured — eligible set equals fleet. "
            "Set REPAVE_GITHUB_TOKEN or App credentials to scan orgs/topics.",
        )
    if search_fn is None:
        from repave_engine.github_inventory import search_github_repositories

        search_fn = search_github_repositories

    urls: list[str] = []
    seen: set[str] = set()
    queries: list[str] = []
    for org in github_orgs:
        queries.append(f"org:{org}")
    for topic in github_topics:
        queries.append(f"topic:{topic}")
    per_query = max(1, min(search_limit, 100))
    for query in queries:
        try:
            found = search_fn(query, token, limit=per_query)
        except (GitHubInventoryError, OSError, RuntimeError, ValueError) as exc:
            return (
                (),
                "fleet",
                f"GitHub search failed ({exc}); eligible set equals fleet.",
            )
        for url in found:
            key = normalize_repo_url(url)
            if key in seen:
                continue
            seen.add(key)
            urls.append(url)
            if len(urls) >= search_limit:
                break
        if len(urls) >= search_limit:
            break
    return tuple(urls), "github_search", ""
