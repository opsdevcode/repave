"""Cortex-style improvement initiatives over catalog maturity rules."""

from __future__ import annotations

import fcntl
import json
import logging
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from repave_engine.entity_catalog import CatalogEntity
from repave_engine.jsonl_lock import append_jsonl_line
from repave_engine.maturity_rubric import MaturityResult, MaturityRubric, evaluate_maturity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Initiative:
    id: str
    title: str
    description: str = ""
    owning_team: str = ""
    due_date: str = ""
    target_level: int = 0
    target_rule_keys: tuple[str, ...] = ()
    active: bool = True

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "owning_team": self.owning_team,
            "due_date": self.due_date,
            "target_level": self.target_level,
            "target_rule_keys": list(self.target_rule_keys),
            "active": self.active,
        }


@dataclass(frozen=True)
class InitiativeEntityStatus:
    initiative_id: str
    title: str
    passed: bool
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "initiative_id": self.initiative_id,
            "title": self.title,
            "passed": self.passed,
            "detail": self.detail,
        }


def _parse_initiative(raw: dict[str, Any]) -> Initiative | None:
    initiative_id = str(raw.get("id", "")).strip()
    title = str(raw.get("title", "")).strip()
    if not initiative_id or not title:
        return None
    rules_raw = raw.get("target_rule_keys", [])
    rules: tuple[str, ...] = ()
    if isinstance(rules_raw, list):
        rules = tuple(str(item).strip() for item in rules_raw if str(item).strip())
    try:
        target_level = int(raw.get("target_level", 0) or 0)
    except (TypeError, ValueError):
        target_level = 0
    active_raw = raw.get("active", True)
    active = True if not isinstance(active_raw, bool) else active_raw
    return Initiative(
        id=initiative_id,
        title=title,
        description=str(raw.get("description", "")).strip(),
        owning_team=str(raw.get("owning_team", "")).strip(),
        due_date=str(raw.get("due_date", "")).strip(),
        target_level=max(0, target_level),
        target_rule_keys=rules,
        active=active,
    )


def _truthy(value: object, *, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def read_initiatives(path: Path) -> tuple[Initiative, ...]:
    """Load initiatives; last line wins when the same id appears more than once."""
    if not path.is_file():
        return ()
    by_id: dict[str, Initiative] = {}
    order: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("unable to read initiatives file %s: %s", path, exc)
        return ()
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            raw = json.loads(stripped)
        except json.JSONDecodeError:
            logger.warning("skip invalid initiatives JSON on line %s of %s", line_no, path)
            continue
        if not isinstance(raw, dict):
            continue
        parsed = _parse_initiative(raw)
        if parsed is None:
            continue
        if parsed.id not in by_id:
            order.append(parsed.id)
        by_id[parsed.id] = parsed
    return tuple(by_id[item_id] for item_id in order)


def write_initiatives(path: Path, initiatives: tuple[Initiative, ...]) -> None:
    """Rewrite the initiatives JSONL under an exclusive lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item.to_public_dict(), sort_keys=True) + "\n" for item in initiatives]
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.seek(0)
            handle.truncate()
            handle.writelines(lines)
            handle.flush()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_initiative(path: Path, initiative: Initiative) -> None:
    append_jsonl_line(
        path,
        json.dumps(initiative.to_public_dict(), sort_keys=True),
        store="initiatives",
    )


def get_initiative(path: Path, initiative_id: str) -> Initiative | None:
    needle = initiative_id.strip()
    if not needle:
        return None
    for item in read_initiatives(path):
        if item.id == needle:
            return item
    return None


def upsert_initiative(path: Path, initiative: Initiative) -> Initiative:
    """Replace an existing id or append a new row; rewrites the store for a clean file."""
    current = list(read_initiatives(path))
    replaced = False
    next_items: list[Initiative] = []
    for item in current:
        if item.id == initiative.id:
            next_items.append(initiative)
            replaced = True
        else:
            next_items.append(item)
    if not replaced:
        next_items.append(initiative)
    write_initiatives(path, tuple(next_items))
    return initiative


def deactivate_initiative(path: Path, initiative_id: str) -> Initiative:
    existing = get_initiative(path, initiative_id)
    if existing is None:
        raise ValueError(f"initiative not found: {initiative_id}")
    if not existing.active:
        return existing
    return upsert_initiative(path, replace(existing, active=False))


def apply_initiative_patch(existing: Initiative, patch: dict[str, Any]) -> Initiative:
    """Apply a partial update. Raises ValueError when fields are invalid."""
    title = existing.title
    if "title" in patch:
        title = str(patch.get("title", "")).strip()
        if not title:
            raise ValueError("title is required")
    description = (
        str(patch.get("description", "")).strip()
        if "description" in patch
        else existing.description
    )
    owning_team = (
        str(patch.get("owning_team", "")).strip()
        if "owning_team" in patch
        else existing.owning_team
    )
    due_date = str(patch.get("due_date", "")).strip() if "due_date" in patch else existing.due_date
    target_level = existing.target_level
    if "target_level" in patch:
        try:
            target_level = max(0, int(patch.get("target_level", 0) or 0))
        except (TypeError, ValueError) as exc:
            raise ValueError("target_level must be an integer") from exc
    rules = existing.target_rule_keys
    if "target_rule_keys" in patch:
        rules_raw = patch.get("target_rule_keys", "")
        if isinstance(rules_raw, str):
            rules = tuple(part.strip() for part in rules_raw.split(",") if part.strip())
        elif isinstance(rules_raw, list):
            rules = tuple(str(item).strip() for item in rules_raw if str(item).strip())
        else:
            raise ValueError("target_rule_keys must be a string or list")
    active = existing.active
    if "active" in patch:
        active = _truthy(patch.get("active"), default=existing.active)
    return replace(
        existing,
        title=title,
        description=description,
        owning_team=owning_team,
        due_date=due_date,
        target_level=target_level,
        target_rule_keys=rules,
        active=active,
    )


def build_initiative_from_form(payload: dict[str, Any]) -> Initiative:
    title = str(payload.get("title", "")).strip()
    if not title:
        raise ValueError("title is required")
    initiative_id = str(payload.get("id", "")).strip() or f"init-{uuid4().hex[:10]}"
    rules_raw = payload.get("target_rule_keys", "")
    if isinstance(rules_raw, str):
        rules = tuple(part.strip() for part in rules_raw.split(",") if part.strip())
    elif isinstance(rules_raw, list):
        rules = tuple(str(item).strip() for item in rules_raw if str(item).strip())
    else:
        rules = ()
    try:
        target_level = int(payload.get("target_level", 0) or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("target_level must be an integer") from exc
    return Initiative(
        id=initiative_id,
        title=title,
        description=str(payload.get("description", "")).strip(),
        owning_team=str(payload.get("owning_team", "")).strip(),
        due_date=str(payload.get("due_date", "")).strip(),
        target_level=max(0, target_level),
        target_rule_keys=rules,
        active=_truthy(payload.get("active", True), default=True),
    )


def evaluate_initiative_for_entity(
    initiative: Initiative,
    entity: CatalogEntity,
    *,
    maturity: MaturityResult | None = None,
    rubric: MaturityRubric | None = None,
) -> InitiativeEntityStatus:
    result = maturity
    if result is None and rubric is not None:
        result = evaluate_maturity(entity, rubric)
    if result is None:
        return InitiativeEntityStatus(
            initiative_id=initiative.id,
            title=initiative.title,
            passed=False,
            detail="Maturity not evaluated",
        )
    if initiative.target_level > 0 and result.level < initiative.target_level:
        return InitiativeEntityStatus(
            initiative_id=initiative.id,
            title=initiative.title,
            passed=False,
            detail=f"Maturity L{result.level} < target L{initiative.target_level}",
        )
    if initiative.target_rule_keys:
        by_key = {item.key: item for item in result.rules}
        missing = [key for key in initiative.target_rule_keys if key not in by_key]
        failing = [
            key for key in initiative.target_rule_keys if key in by_key and not by_key[key].passed
        ]
        if missing or failing:
            parts = []
            if failing:
                parts.append("failing: " + ", ".join(failing))
            if missing:
                parts.append("missing: " + ", ".join(missing))
            return InitiativeEntityStatus(
                initiative_id=initiative.id,
                title=initiative.title,
                passed=False,
                detail="; ".join(parts),
            )
    if initiative.target_level <= 0 and not initiative.target_rule_keys:
        return InitiativeEntityStatus(
            initiative_id=initiative.id,
            title=initiative.title,
            passed=result.level > 0,
            detail=f"Maturity L{result.level} ({result.label})",
        )
    return InitiativeEntityStatus(
        initiative_id=initiative.id,
        title=initiative.title,
        passed=True,
        detail=f"Meets L{result.level} ({result.label})",
    )


def initiative_progress(
    initiative: Initiative,
    entities: list[CatalogEntity],
    rubric: MaturityRubric,
) -> dict[str, Any]:
    statuses = [
        evaluate_initiative_for_entity(
            initiative,
            entity,
            rubric=rubric,
        )
        for entity in entities
    ]
    passed = sum(1 for item in statuses if item.passed)
    total = len(statuses)
    overdue = False
    if initiative.due_date:
        try:
            due = date.fromisoformat(initiative.due_date)
            overdue = due < datetime.now(timezone.utc).date() and passed < total
        except ValueError:
            overdue = False
    return {
        "initiative": initiative.to_public_dict(),
        "passed": passed,
        "total": total,
        "ratio": (passed / total) if total else 0.0,
        "overdue": overdue,
        "statuses": [item.to_public_dict() for item in statuses],
    }
