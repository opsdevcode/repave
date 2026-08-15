"""v3 breaking-change registry — single source for sunset dates and migration links."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import format_datetime
from typing import Final

# RFC 7231 IMF-fixdate for HTTP Sunset headers (see sunset_http_date).


@dataclass(frozen=True)
class DeprecationEntry:
    """One scheduled v3 removal with operator-facing migration guidance."""

    deprecation_id: str
    summary: str
    sunset: date
    migration_doc: str
    successor_link: str | None = None


def _entry(
    deprecation_id: str,
    summary: str,
    *,
    year: int,
    month: int,
    day: int,
    migration_doc: str,
    successor_link: str | None = None,
) -> DeprecationEntry:
    return DeprecationEntry(
        deprecation_id=deprecation_id,
        summary=summary,
        sunset=date(year, month, day),
        migration_doc=migration_doc,
        successor_link=successor_link,
    )


V3_DEPRECATIONS: Final[tuple[DeprecationEntry, ...]] = (
    _entry(
        "html_portal_removal",
        "Remove FastAPI HTML portal templates after the hosted Backstage sunset",
        year=2027,
        month=2,
        day=14,
        migration_doc="docs/backstage.md",
        successor_link='</docs/backstage>; rel="successor-version"',
    ),
    _entry(
        "api_v1_removal",
        "Remove legacy /api/v1 JSON surface",
        year=2027,
        month=8,
        day=1,
        migration_doc="docs/api-v1-migration.md",
        successor_link='</docs/api-v2>; rel="successor-version"',
    ),
    _entry(
        "crd_v1alpha1_removal",
        "Remove repave.dev/v1alpha1 CRDs after v1 promotion",
        year=2027,
        month=8,
        day=1,
        migration_doc="docs/roadmap.md#breaking-at-v300",
    ),
    _entry(
        "mandatory_policy_tier",
        "Policy gates cannot be disabled on regulated blueprint families",
        year=2027,
        month=8,
        day=1,
        migration_doc="docs/roadmap.md#breaking-at-v300",
    ),
    _entry(
        "blueprint_schema_v2",
        "Blueprint JSON schema v2 becomes required",
        year=2027,
        month=8,
        day=1,
        migration_doc="docs/blueprint-versioning.md",
    ),
)


def deprecation_by_id(deprecation_id: str) -> DeprecationEntry | None:
    for entry in V3_DEPRECATIONS:
        if entry.deprecation_id == deprecation_id:
            return entry
    return None


def sunset_http_date(entry: DeprecationEntry) -> str:
    instant = datetime(
        entry.sunset.year,
        entry.sunset.month,
        entry.sunset.day,
        tzinfo=timezone.utc,
    )
    return format_datetime(instant, usegmt=True)


def http_deprecation_headers(
    deprecation_id: str,
    *,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    """Build Deprecation/Sunset/Link headers for a registered removal."""
    entry = deprecation_by_id(deprecation_id)
    if entry is None:
        raise KeyError(
            f"unknown deprecation_id {deprecation_id!r}; "
            "add it to V3_DEPRECATIONS in deprecations.py"
        )
    headers: dict[str, str] = {
        "Deprecation": "true",
        "Sunset": sunset_http_date(entry),
    }
    if entry.successor_link:
        headers["Link"] = entry.successor_link
    if extra:
        headers.update(extra)
    return headers
