"""CSAT and friction capture for platform-as-product feedback loops.

Pure, framework-free core. Handlers append events; this module builds frozen
rollup objects from already-loaded event sequences.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

VALID_SURFACES = frozenset({"result", "run_console", "backstage"})
VALID_FRICTION_TAGS = frozenset(
    {
        "slow",
        "confusing-form",
        "unclear-errors",
        "missing-docs",
        "gates-heavy",
        "other",
    }
)


@dataclass(frozen=True)
class FeedbackEvent:
    submitted_at: str
    csat: int
    friction_tags: tuple[str, ...]
    comment: str
    blueprint_name: str
    blueprint_version: str
    dry_run: bool
    gates_outcome: str
    acting_user: str
    run_id: str
    surface: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "submitted_at": self.submitted_at,
            "csat": self.csat,
            "friction_tags": list(self.friction_tags),
            "comment": self.comment,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "dry_run": self.dry_run,
            "gates_outcome": self.gates_outcome,
            "acting_user": self.acting_user,
            "run_id": self.run_id,
            "surface": self.surface,
        }


@dataclass(frozen=True)
class FrictionTagCount:
    tag: str
    count: int


@dataclass(frozen=True)
class BlueprintFeedbackSummary:
    blueprint_name: str
    blueprint_version: str
    event_count: int
    csat_average: float | None


@dataclass(frozen=True)
class FeedbackRollup:
    event_count: int
    csat_average: float | None
    csat_counts: tuple[tuple[int, int], ...]
    friction_tags: tuple[FrictionTagCount, ...]
    by_blueprint: tuple[BlueprintFeedbackSummary, ...]
    by_surface: tuple[tuple[str, int], ...]
    by_gates_outcome: tuple[tuple[str, int], ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "event_count": self.event_count,
            "csat_average": self.csat_average,
            "csat_counts": {str(score): count for score, count in self.csat_counts},
            "friction_tags": [
                {"tag": item.tag, "count": item.count} for item in self.friction_tags
            ],
            "by_blueprint": [
                {
                    "blueprint_name": item.blueprint_name,
                    "blueprint_version": item.blueprint_version,
                    "event_count": item.event_count,
                    "csat_average": item.csat_average,
                }
                for item in self.by_blueprint
            ],
            "by_surface": {surface: count for surface, count in self.by_surface},
            "by_gates_outcome": {outcome: count for outcome, count in self.by_gates_outcome},
        }


def validate_csat(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str, float)):
        raise ValueError("csat must be an integer from 1 to 5")
    try:
        score = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("csat must be an integer from 1 to 5") from exc
    if score < 1 or score > 5:
        raise ValueError("csat must be an integer from 1 to 5")
    return score


def normalize_friction_tags(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("friction_tags must be a list of strings")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("friction_tags must be a list of strings")
        tag = item.strip()
        if not tag or tag in seen:
            continue
        if tag not in VALID_FRICTION_TAGS:
            raise ValueError(
                f"unknown friction tag {tag!r}; allowed: {', '.join(sorted(VALID_FRICTION_TAGS))}"
            )
        seen.add(tag)
        tags.append(tag)
    return tuple(tags)


def _surface_choices() -> str:
    return ", ".join(sorted(VALID_SURFACES))


def normalize_surface(raw: object) -> str:
    if not isinstance(raw, str):
        raise ValueError(f"surface must be one of: {_surface_choices()}")
    surface = raw.strip()
    if surface not in VALID_SURFACES:
        raise ValueError(f"surface must be one of: {_surface_choices()}")
    return surface


def build_feedback_event(
    *,
    submitted_at: str,
    csat: int,
    friction_tags: Sequence[str] = (),
    comment: str = "",
    blueprint_name: str,
    blueprint_version: str,
    dry_run: bool,
    gates_outcome: str,
    acting_user: str,
    run_id: str = "",
    surface: str,
) -> FeedbackEvent:
    return FeedbackEvent(
        submitted_at=submitted_at,
        csat=validate_csat(csat),
        friction_tags=tuple(friction_tags),
        comment=comment.strip(),
        blueprint_name=blueprint_name.strip(),
        blueprint_version=blueprint_version.strip(),
        dry_run=dry_run,
        gates_outcome=gates_outcome.strip() or "empty",
        acting_user=acting_user.strip() or "unknown",
        run_id=run_id.strip(),
        surface=normalize_surface(surface),
    )


def build_feedback_rollup(events: Sequence[FeedbackEvent]) -> FeedbackRollup:
    if not events:
        return FeedbackRollup(
            event_count=0,
            csat_average=None,
            csat_counts=(),
            friction_tags=(),
            by_blueprint=(),
            by_surface=(),
            by_gates_outcome=(),
        )

    csat_counter: Counter[int] = Counter()
    friction_counter: Counter[str] = Counter()
    surface_counter: Counter[str] = Counter()
    outcome_counter: Counter[str] = Counter()
    blueprint_stats: dict[tuple[str, str], list[int]] = {}

    for event in events:
        csat_counter[event.csat] += 1
        friction_counter.update(event.friction_tags)
        surface_counter[event.surface] += 1
        outcome_counter[event.gates_outcome] += 1
        key = (event.blueprint_name, event.blueprint_version)
        blueprint_stats.setdefault(key, []).append(event.csat)

    total = len(events)
    csat_average = round(sum(event.csat for event in events) / total, 2)
    csat_counts = tuple(sorted(csat_counter.items()))
    friction_tags = tuple(
        FrictionTagCount(tag=tag, count=count) for tag, count in friction_counter.most_common()
    )
    by_blueprint = tuple(
        sorted(
            (
                BlueprintFeedbackSummary(
                    blueprint_name=name,
                    blueprint_version=version,
                    event_count=len(scores),
                    csat_average=round(sum(scores) / len(scores), 2),
                )
                for (name, version), scores in blueprint_stats.items()
            ),
            key=lambda item: (-item.event_count, item.blueprint_name, item.blueprint_version),
        )
    )
    by_surface = tuple(surface_counter.most_common())
    by_gates_outcome = tuple(outcome_counter.most_common())
    return FeedbackRollup(
        event_count=total,
        csat_average=csat_average,
        csat_counts=csat_counts,
        friction_tags=friction_tags,
        by_blueprint=by_blueprint,
        by_surface=by_surface,
        by_gates_outcome=by_gates_outcome,
    )
