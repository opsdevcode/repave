"""Roadmap evidence loop — adoption citations and sunset candidates (v1.89)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from repave_engine.dx_metrics import BlueprintFunnel, DxMetricsSnapshot

EvidenceKind = Literal["fleet_adoption", "plan_apply", "blueprint_funnel"]


@dataclass(frozen=True)
class RoadmapThemeConfig:
    key: str
    title: str
    requesting_team: str
    blueprint_names: tuple[str, ...] = ()
    evidence_kind: EvidenceKind = "fleet_adoption"


DEFAULT_ROADMAP_THEMES: tuple[RoadmapThemeConfig, ...] = (
    RoadmapThemeConfig(
        key="v185-adoption",
        title="Golden path adoption and DX metrics (v1.85)",
        requesting_team="platform",
        evidence_kind="fleet_adoption",
    ),
    RoadmapThemeConfig(
        key="v186-feedback",
        title="Developer feedback loop (v1.86)",
        requesting_team="platform",
        evidence_kind="fleet_adoption",
    ),
    RoadmapThemeConfig(
        key="v87-stakeholders",
        title="Stakeholder interfaces (v1.87)",
        requesting_team="security",
        evidence_kind="plan_apply",
    ),
    RoadmapThemeConfig(
        key="v188-guided-forms",
        title="Cognitive load reduction — Guided / Advanced forms (v1.88)",
        requesting_team="portal",
        blueprint_names=("terraform-module-generic", "ansible-role-generic"),
        evidence_kind="blueprint_funnel",
    ),
)


@dataclass(frozen=True)
class RoadmapEvidenceSettings:
    sunset_conversion_threshold: float = 0.25
    sunset_min_plans: int = 1
    sunset_review_days: int = 90
    themes: tuple[RoadmapThemeConfig, ...] = DEFAULT_ROADMAP_THEMES


@dataclass(frozen=True)
class ThemeEvidenceRow:
    key: str
    title: str
    requesting_team: str
    evidence_kind: EvidenceKind
    evidence_summary: str
    evidence_detail: str
    meets_baseline: bool | None

    def to_public_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "requesting_team": self.requesting_team,
            "evidence_kind": self.evidence_kind,
            "evidence_summary": self.evidence_summary,
            "evidence_detail": self.evidence_detail,
            "meets_baseline": self.meets_baseline,
            "adoption_href": "/platform/adoption",
        }


@dataclass(frozen=True)
class SunsetCandidate:
    blueprint_name: str
    plans: int
    applies: int
    conversion_ratio: float
    review_by: str
    reason: str

    def to_public_dict(self) -> dict[str, object]:
        return {
            "blueprint_name": self.blueprint_name,
            "plans": self.plans,
            "applies": self.applies,
            "conversion_ratio": self.conversion_ratio,
            "review_by": self.review_by,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RoadmapEvidenceReport:
    captured_at: str
    themes: tuple[ThemeEvidenceRow, ...]
    sunset_candidates: tuple[SunsetCandidate, ...]

    def to_public_dict(self) -> dict[str, object]:
        return {
            "captured_at": self.captured_at,
            "themes": [row.to_public_dict() for row in self.themes],
            "sunset_candidates": [row.to_public_dict() for row in self.sunset_candidates],
        }


def _funnel_lookup(snapshot: DxMetricsSnapshot) -> dict[str, BlueprintFunnel]:
    return {row.blueprint_name: row for row in snapshot.funnels}


def _fleet_adoption_evidence(snapshot: DxMetricsSnapshot) -> tuple[str, str, bool | None]:
    if snapshot.adoption_ratio is None:
        return (
            "Fleet adoption unavailable",
            "Enable fleet registry and eligible-repo search to compute adoption ratio.",
            None,
        )
    pct = snapshot.adoption_ratio * 100.0
    summary = f"Adoption {pct:.0f}% ({snapshot.governed_count}/{snapshot.eligible_count} repos)"
    detail = (
        f"Captured {snapshot.captured_at} from /platform/adoption — "
        f"governed fleet vs eligible denominator ({snapshot.eligible_source})."
    )
    meets = None
    if snapshot.baseline_adoption_ratio is not None:
        meets = snapshot.adoption_ratio >= snapshot.baseline_adoption_ratio
    return summary, detail, meets


def _plan_apply_evidence(snapshot: DxMetricsSnapshot) -> tuple[str, str, bool | None]:
    if snapshot.plan_apply_ratio is None:
        return (
            "Plan→apply funnel unavailable",
            "Enable audit logging to compute plan vs apply conversion.",
            None,
        )
    pct = snapshot.plan_apply_ratio * 100.0
    summary = f"Plan→apply {pct:.0f}% ({snapshot.apply_count}/{snapshot.plan_count} runs)"
    detail = (
        f"Captured {snapshot.captured_at} from /platform/adoption audit funnel — "
        "dry-run plans vs non-dry-run applies."
    )
    meets = None
    if snapshot.baseline_plan_apply_ratio is not None:
        meets = snapshot.plan_apply_ratio >= snapshot.baseline_plan_apply_ratio
    return summary, detail, meets


def _blueprint_funnel_evidence(
    snapshot: DxMetricsSnapshot,
    blueprint_names: tuple[str, ...],
) -> tuple[str, str, bool | None]:
    lookup = _funnel_lookup(snapshot)
    if not blueprint_names:
        return _plan_apply_evidence(snapshot)
    rows = [lookup[name] for name in blueprint_names if name in lookup]
    if not rows:
        names = ", ".join(blueprint_names)
        return (
            f"No funnel data for {names}",
            "No audit plans recorded for configured blueprint names yet.",
            None,
        )
    conversions = [row.conversion_ratio for row in rows]
    avg = sum(conversions) / len(conversions)
    parts = [
        f"{row.blueprint_name} {row.conversion_ratio * 100:.0f}% ({row.applies}/{row.plans})"
        for row in rows
    ]
    summary = f"Avg plan→apply {avg * 100:.0f}% across {len(rows)} golden path(s)"
    detail = f"Captured {snapshot.captured_at} from /platform/adoption — " + "; ".join(parts) + "."
    meets = None
    if snapshot.baseline_plan_apply_ratio is not None:
        meets = avg >= snapshot.baseline_plan_apply_ratio
    return summary, detail, meets


def build_theme_evidence(
    snapshot: DxMetricsSnapshot,
    themes: tuple[RoadmapThemeConfig, ...],
) -> tuple[ThemeEvidenceRow, ...]:
    rows: list[ThemeEvidenceRow] = []
    for theme in themes:
        if theme.evidence_kind == "fleet_adoption":
            summary, detail, meets = _fleet_adoption_evidence(snapshot)
        elif theme.evidence_kind == "plan_apply":
            summary, detail, meets = _plan_apply_evidence(snapshot)
        else:
            summary, detail, meets = _blueprint_funnel_evidence(
                snapshot,
                theme.blueprint_names,
            )
        rows.append(
            ThemeEvidenceRow(
                key=theme.key,
                title=theme.title,
                requesting_team=theme.requesting_team,
                evidence_kind=theme.evidence_kind,
                evidence_summary=summary,
                evidence_detail=detail,
                meets_baseline=meets,
            )
        )
    return tuple(rows)


def build_sunset_candidates(
    snapshot: DxMetricsSnapshot,
    *,
    conversion_threshold: float,
    min_plans: int,
    review_days: int,
    now: datetime | None = None,
) -> tuple[SunsetCandidate, ...]:
    anchor = now or datetime.now(tz=timezone.utc)
    review_by = (anchor + timedelta(days=review_days)).date().isoformat()
    candidates: list[SunsetCandidate] = []
    for row in snapshot.funnels:
        if row.plans < min_plans:
            continue
        if row.conversion_ratio >= conversion_threshold:
            continue
        pct = row.conversion_ratio * 100.0
        threshold_pct = conversion_threshold * 100.0
        candidates.append(
            SunsetCandidate(
                blueprint_name=row.blueprint_name,
                plans=row.plans,
                applies=row.applies,
                conversion_ratio=row.conversion_ratio,
                review_by=review_by,
                reason=(
                    f"Plan→apply {pct:.0f}% is below {threshold_pct:.0f}% threshold "
                    f"({row.applies}/{row.plans} applies) — candidate for simplification "
                    f"or sunset by {review_by}."
                ),
            )
        )
    candidates.sort(key=lambda item: (item.conversion_ratio, item.plans))
    return tuple(candidates)


def build_roadmap_evidence_report(
    snapshot: DxMetricsSnapshot,
    settings: RoadmapEvidenceSettings,
    *,
    now: datetime | None = None,
) -> RoadmapEvidenceReport:
    return RoadmapEvidenceReport(
        captured_at=snapshot.captured_at,
        themes=build_theme_evidence(snapshot, settings.themes),
        sunset_candidates=build_sunset_candidates(
            snapshot,
            conversion_threshold=settings.sunset_conversion_threshold,
            min_plans=settings.sunset_min_plans,
            review_days=settings.sunset_review_days,
            now=now,
        ),
    )


def _parse_theme_config(raw: object) -> RoadmapThemeConfig | None:
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key", "")).strip()
    title = str(raw.get("title", "")).strip()
    team = str(raw.get("requesting_team", "")).strip()
    if not key or not title or not team:
        return None
    kind_raw = str(raw.get("evidence_kind", "fleet_adoption")).strip().lower()
    if kind_raw not in ("fleet_adoption", "plan_apply", "blueprint_funnel"):
        kind_raw = "fleet_adoption"
    names_raw = raw.get("blueprint_names", [])
    names: tuple[str, ...] = ()
    if isinstance(names_raw, list):
        names = tuple(str(item).strip() for item in names_raw if str(item).strip())
    return RoadmapThemeConfig(
        key=key,
        title=title,
        requesting_team=team,
        blueprint_names=names,
        evidence_kind=kind_raw,  # type: ignore[arg-type]
    )


def load_roadmap_evidence_settings(repo_root: Path) -> RoadmapEvidenceSettings | None:
    """Resolve roadmap evidence settings when platform_metrics is enabled."""
    from repave_engine.settings import _load_config_file, load_platform_metrics_config

    if load_platform_metrics_config(repo_root) is None:
        return None
    file_data = _load_config_file(repo_root / "repave.config.yaml")
    block = file_data.get("platform_metrics")
    if not isinstance(block, dict):
        return RoadmapEvidenceSettings()
    evidence_block = block.get("roadmap_evidence")
    if not isinstance(evidence_block, dict):
        return RoadmapEvidenceSettings()

    threshold_raw = evidence_block.get("sunset_conversion_threshold", 0.25)
    min_plans_raw = evidence_block.get("sunset_min_plans", 1)
    review_days_raw = evidence_block.get("sunset_review_days", 90)
    try:
        threshold = float(threshold_raw)
        min_plans = int(min_plans_raw)
        review_days = int(review_days_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("platform_metrics.roadmap_evidence thresholds must be numbers") from exc
    if not 0.0 <= threshold <= 1.0:
        raise ValueError(
            "platform_metrics.roadmap_evidence.sunset_conversion_threshold must be 0-1"
        )
    if min_plans < 0 or review_days < 1:
        raise ValueError("platform_metrics.roadmap_evidence sunset_min_plans/review_days invalid")

    themes_raw = evidence_block.get("themes")
    themes = DEFAULT_ROADMAP_THEMES
    if themes_raw is not None:
        if not isinstance(themes_raw, list):
            raise ValueError("platform_metrics.roadmap_evidence.themes must be a list")
        parsed = tuple(item for item in (_parse_theme_config(row) for row in themes_raw) if item)
        if parsed:
            themes = parsed

    return RoadmapEvidenceSettings(
        sunset_conversion_threshold=threshold,
        sunset_min_plans=min_plans,
        sunset_review_days=review_days,
        themes=themes,
    )
