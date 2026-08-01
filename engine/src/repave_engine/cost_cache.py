"""In-process TTL cache for cloud cost actuals (server-side, read-only)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TypeVar

from repave_engine.cost_actuals import CostActualsSummary

T = TypeVar("T")

DEFAULT_TTL_SECONDS = 3600.0

_cache: dict[str, _CacheEntry] = {}


@dataclass(frozen=True)
class _CacheEntry:
    summary: CostActualsSummary
    expires_at: float


def cache_get(key: str) -> CostActualsSummary | None:
    entry = _cache.get(key)
    if entry is None:
        return None
    if time.monotonic() >= entry.expires_at:
        _cache.pop(key, None)
        return None
    return entry.summary


def cache_set(
    key: str, summary: CostActualsSummary, *, ttl_seconds: float = DEFAULT_TTL_SECONDS
) -> None:
    _cache[key] = _CacheEntry(summary=summary, expires_at=time.monotonic() + ttl_seconds)


def cache_clear() -> None:
    _cache.clear()
