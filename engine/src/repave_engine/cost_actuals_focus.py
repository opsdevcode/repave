"""Thin FOCUS-shaped billing ingest for portal cost actuals (v1.93)."""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from repave_engine.cost_actuals import CostActualsSummary, CostEntity, entity_tag_coverage
from repave_engine.cost_cache import cache_get, cache_set

if TYPE_CHECKING:
    from repave_engine.settings import CostFocusConfig

logger = logging.getLogger(__name__)

FOCUS_SUPPORTED_COLUMNS: frozenset[str] = frozenset(
    {
        "BilledCost",
        "BillingCurrency",
        "BillingPeriodStart",
        "BillingPeriodEnd",
        "ChargePeriodStart",
        "ChargePeriodEnd",
        "ServiceName",
        "Tags",
    }
)


@dataclass(frozen=True)
class FocusRow:
    billed_cost: float
    currency: str
    period_start: datetime | None
    period_end: datetime | None
    service_name: str
    tags: dict[str, str]


@dataclass(frozen=True)
class _FocusSourceCache:
    source: str
    fingerprint: int
    rows: tuple[FocusRow, ...]


_focus_source_cache: _FocusSourceCache | None = None


def _field(record: dict[str, Any], *names: str) -> Any:
    lowered = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def parse_focus_tags(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, list):
        tags: dict[str, str] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            key = str(item.get("Key", item.get("key", ""))).strip()
            value = str(item.get("Value", item.get("value", ""))).strip()
            if key:
                tags[key] = value
        return tags
    if isinstance(raw, dict):
        return {
            str(key).strip(): str(value).strip() for key, value in raw.items() if str(key).strip()
        }
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, dict):
            return parse_focus_tags(parsed)
        if isinstance(parsed, list):
            return parse_focus_tags(parsed)
    return {}


def _parse_focus_datetime(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def parse_focus_row(record: Any) -> FocusRow | None:
    if not isinstance(record, dict):
        return None
    amount_raw = _field(record, "BilledCost", "billed_cost")
    if amount_raw is None:
        return None
    try:
        billed_cost = float(str(amount_raw).strip())
    except ValueError:
        return None
    currency = str(_field(record, "BillingCurrency", "billing_currency") or "USD").strip() or "USD"
    period_start = _parse_focus_datetime(
        _field(record, "ChargePeriodStart", "charge_period_start", "BillingPeriodStart")
    )
    period_end = _parse_focus_datetime(
        _field(record, "ChargePeriodEnd", "charge_period_end", "BillingPeriodEnd")
    )
    service_name = str(_field(record, "ServiceName", "service_name") or "").strip()
    tags = parse_focus_tags(_field(record, "Tags", "tags"))
    return FocusRow(
        billed_cost=billed_cost,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        service_name=service_name,
        tags=tags,
    )


def _parse_focus_payload(payload: Any) -> list[FocusRow]:
    records: list[Any]
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        nested = payload.get("rows", payload.get("data", payload.get("records")))
        records = nested if isinstance(nested, list) else [payload]
    else:
        return []
    rows: list[FocusRow] = []
    for record in records:
        parsed = parse_focus_row(record)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _read_focus_file(path: Path) -> list[FocusRow]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows: list[FocusRow] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = parse_focus_row(payload)
            if parsed is not None:
                rows.append(parsed)
        return rows
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("FOCUS file is not valid JSON: %s", path)
        return []
    return _parse_focus_payload(payload)


def _fetch_focus_url(url: str, *, timeout: float) -> list[FocusRow]:
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("FOCUS URL fetch failed (%s): %s", url, exc)
        return []
    content_type = response.headers.get("content-type", "").lower()
    body = response.text
    if "jsonl" in content_type or url.rstrip("/").endswith(".jsonl"):
        rows: list[FocusRow] = []
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            parsed = parse_focus_row(payload)
            if parsed is not None:
                rows.append(parsed)
        return rows
    try:
        payload = response.json()
    except ValueError:
        logger.warning("FOCUS URL response is not JSON: %s", url)
        return []
    return _parse_focus_payload(payload)


def _resolve_focus_source(config: CostFocusConfig, repo_root: Path | None) -> str:
    raw = config.file.strip()
    if raw.startswith(("http://", "https://")):
        return raw
    path = Path(raw).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    if repo_root is None:
        return str(path)
    return str((repo_root / path).resolve())


def _source_fingerprint(source: str) -> int:
    if source.startswith(("http://", "https://")):
        return hash(source)
    path = Path(source)
    if not path.is_file():
        return -1
    stat = path.stat()
    return hash((stat.st_mtime_ns, stat.st_size))


def clear_focus_source_cache() -> None:
    global _focus_source_cache
    _focus_source_cache = None


def load_focus_rows(
    config: CostFocusConfig,
    *,
    repo_root: Path | None = None,
    timeout: float = 8.0,
) -> tuple[FocusRow, ...]:
    global _focus_source_cache
    source = _resolve_focus_source(config, repo_root)
    if not source:
        return ()
    fingerprint = _source_fingerprint(source)
    if (
        _focus_source_cache is not None
        and _focus_source_cache.source == source
        and _focus_source_cache.fingerprint == fingerprint
    ):
        return _focus_source_cache.rows
    if source.startswith(("http://", "https://")):
        rows = tuple(_fetch_focus_url(source, timeout=timeout))
    else:
        path = Path(source)
        if not path.is_file():
            logger.warning("FOCUS file not found: %s", path)
            rows = ()
        else:
            rows = tuple(_read_focus_file(path))
    _focus_source_cache = _FocusSourceCache(source=source, fingerprint=fingerprint, rows=rows)
    return rows


def _tag_value(tags: dict[str, str], key: str) -> str:
    if not key:
        return ""
    direct = tags.get(key, "").strip()
    if direct:
        return direct
    lowered = key.lower()
    for tag_key, tag_value in tags.items():
        if tag_key.lower() == lowered:
            return tag_value.strip()
    return ""


def _row_matches_entity(
    row: FocusRow,
    entity: CostEntity,
    *,
    tag_key_owner: str,
    tag_key_service: str,
    coverage: str,
) -> bool:
    owner = entity.owner.strip()
    service = entity.display_name.strip()
    tag_owner = _tag_value(row.tags, tag_key_owner)
    tag_service = _tag_value(row.tags, tag_key_service)
    service_name_match = bool(service) and row.service_name.casefold() == service.casefold()
    if coverage == "complete":
        owner_ok = bool(owner) and tag_owner.casefold() == owner.casefold()
        service_ok = (bool(service) and tag_service.casefold() == service.casefold()) or (
            service_name_match and not tag_service
        )
        return owner_ok and service_ok
    if coverage == "partial":
        if owner and tag_owner.casefold() == owner.casefold():
            return True
        if service and (tag_service.casefold() == service.casefold() or service_name_match):
            return True
    return False


def _row_in_lookback(row: FocusRow, *, lookback_days: int, now: datetime) -> bool:
    if lookback_days <= 0:
        return True
    cutoff = now - timedelta(days=lookback_days)
    anchor = row.period_start or row.period_end
    if anchor is None:
        return True
    return anchor >= cutoff


def aggregate_focus_actuals(
    rows: Sequence[FocusRow],
    entity: CostEntity,
    config: CostFocusConfig,
) -> CostActualsSummary | None:
    coverage, cov_detail = entity_tag_coverage(entity)
    if coverage == "missing":
        return None
    now = datetime.now(tz=timezone.utc)
    amount = 0.0
    currency = config.currency.strip() or "USD"
    latest_end: datetime | None = None
    matched = 0
    for row in rows:
        if not _row_in_lookback(row, lookback_days=config.lookback_days, now=now):
            continue
        if not _row_matches_entity(
            row,
            entity,
            tag_key_owner=config.tag_key_owner,
            tag_key_service=config.tag_key_service,
            coverage=coverage,
        ):
            continue
        amount += row.billed_cost
        matched += 1
        if row.currency:
            currency = row.currency
        anchor = row.period_end or row.period_start
        if anchor is not None and (latest_end is None or anchor > latest_end):
            latest_end = anchor
    if matched == 0:
        return None
    as_of = (latest_end or now).replace(microsecond=0).isoformat()
    source = _resolve_focus_source(config, repo_root=None)
    detail = f"FOCUS ingest L{config.lookback_days}D ({cov_detail}; {matched} row(s))"
    return CostActualsSummary(
        currency=currency,
        amount_30d=f"{amount:.2f}",
        as_of=as_of,
        detail=detail,
        tag_coverage=coverage,
        source_url=source,
    )


def fetch_entity_cost_actuals_focus(
    config: CostFocusConfig,
    entity: CostEntity,
    *,
    repo_root: Path | None = None,
) -> CostActualsSummary | None:
    if not config.file.strip():
        return None
    cache_key = f"focus:{config.file}:{entity.entity_id}:{entity.owner}:{entity.display_name}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached
    rows = load_focus_rows(config, repo_root=repo_root)
    if not rows:
        return None
    summary = aggregate_focus_actuals(rows, entity, config)
    if summary is not None:
        cache_set(cache_key, summary)
    return summary
