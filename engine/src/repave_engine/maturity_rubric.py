"""OpsLevel-style maturity levels over catalog scorecard dimensions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from repave_engine.entity_catalog import CatalogEntity, ScoreLevel
from repave_engine.yaml_util import load_yaml_mapping_soft

ScoreRequirement = Literal["pass", "warn", "fail", "unknown"]

# Higher index = better outcome (same ordering spirit as entity_catalog._LEVEL_RANK).
_OUTCOME_RANK: tuple[ScoreLevel, ...] = ("fail", "unknown", "warn", "pass")


@dataclass(frozen=True)
class MaturityRule:
    """One requirement for a maturity level."""

    key: str
    require: ScoreRequirement = "pass"
    kind: str = "scorecard"  # scorecard | has_oncall | has_dependencies | custom


@dataclass(frozen=True)
class MaturityLevelDef:
    level: int
    label: str
    rules: tuple[MaturityRule, ...]


@dataclass(frozen=True)
class MaturityRubric:
    levels: tuple[MaturityLevelDef, ...]

    def level_for(self, level: int) -> MaturityLevelDef | None:
        for item in self.levels:
            if item.level == level:
                return item
        return None


@dataclass(frozen=True)
class MaturityRuleResult:
    key: str
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class MaturityResult:
    level: int
    label: str
    passing: int
    total: int
    rules: tuple[MaturityRuleResult, ...]

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "label": self.label,
            "passing_rules": self.passing,
            "total_rules": self.total,
            "rules": [
                {
                    "key": item.key,
                    "label": item.label,
                    "passed": item.passed,
                    "detail": item.detail,
                }
                for item in self.rules
            ],
        }


def _default_rubric() -> MaturityRubric:
    return MaturityRubric(
        levels=(
            MaturityLevelDef(
                level=1,
                label="Registered",
                rules=(MaturityRule(key="provenance", require="pass"),),
            ),
            MaturityLevelDef(
                level=2,
                label="Governed",
                rules=(
                    MaturityRule(key="provenance", require="pass"),
                    MaturityRule(key="pins", require="warn"),
                ),
            ),
            MaturityLevelDef(
                level=3,
                label="Operable",
                rules=(
                    MaturityRule(key="provenance", require="pass"),
                    MaturityRule(key="pins", require="pass"),
                    MaturityRule(key="has-runbook", require="pass"),
                ),
            ),
            MaturityLevelDef(
                level=4,
                label="Reliable",
                rules=(
                    MaturityRule(key="provenance", require="pass"),
                    MaturityRule(key="pins", require="pass"),
                    MaturityRule(key="has-runbook", require="pass"),
                    MaturityRule(key="has-slo", require="pass"),
                    MaturityRule(key="gates", require="pass"),
                ),
            ),
            MaturityLevelDef(
                level=5,
                label="Production-ready",
                rules=(
                    MaturityRule(key="provenance", require="pass"),
                    MaturityRule(key="pins", require="pass"),
                    MaturityRule(key="has-runbook", require="pass"),
                    MaturityRule(key="has-slo", require="pass"),
                    MaturityRule(key="gates", require="pass"),
                    MaturityRule(key="deployment", require="pass"),
                    MaturityRule(key="cost", require="warn"),
                ),
            ),
        )
    )


def _parse_rule(raw: Any) -> MaturityRule | None:
    if isinstance(raw, str):
        key = raw.strip()
        if not key:
            return None
        return MaturityRule(key=key, require="pass", kind="scorecard")
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key", "")).strip()
    if not key:
        return None
    require_raw = str(raw.get("require", "pass")).strip().lower() or "pass"
    if require_raw not in ("pass", "warn", "fail", "unknown"):
        require_raw = "pass"
    kind = str(raw.get("kind", "scorecard")).strip() or "scorecard"
    return MaturityRule(key=key, require=require_raw, kind=kind)  # type: ignore[arg-type]


def load_maturity_rubric(path: Path | None) -> MaturityRubric:
    """Load rubric YAML or return the built-in default."""
    if path is None or not path.is_file():
        return _default_rubric()
    doc = load_yaml_mapping_soft(path)
    if doc is None:
        return _default_rubric()
    levels_raw = doc.get("levels")
    if not isinstance(levels_raw, list):
        return _default_rubric()
    levels: list[MaturityLevelDef] = []
    for item in levels_raw:
        if not isinstance(item, dict):
            continue
        try:
            level_num = int(item.get("level", 0))
        except (TypeError, ValueError):
            continue
        if level_num < 1:
            continue
        label = str(item.get("label", f"Level {level_num}")).strip() or f"Level {level_num}"
        rules_raw = item.get("rules", [])
        if not isinstance(rules_raw, list):
            continue
        rules = tuple(rule for raw in rules_raw if (rule := _parse_rule(raw)) is not None)
        if not rules:
            continue
        levels.append(MaturityLevelDef(level=level_num, label=label, rules=rules))
    if not levels:
        return _default_rubric()
    levels.sort(key=lambda item: item.level)
    return MaturityRubric(levels=tuple(levels))


def _scorecard_level(entity: CatalogEntity, key: str) -> ScoreLevel | None:
    for dim in entity.scorecard:
        if dim.key == key:
            return dim.level
    return None


def _meets_requirement(actual: ScoreLevel | None, require: ScoreRequirement) -> bool:
    if actual is None:
        return False
    return _OUTCOME_RANK.index(actual) >= _OUTCOME_RANK.index(require)


def _evaluate_rule(entity: CatalogEntity, rule: MaturityRule) -> MaturityRuleResult:
    if rule.kind == "has_oncall":
        passed = bool(entity.oncall.strip())
        return MaturityRuleResult(
            key=rule.key,
            label="On-call",
            passed=passed,
            detail=entity.oncall if passed else "No on-call annotation",
        )
    if rule.kind == "has_dependencies":
        passed = bool(entity.dependencies)
        return MaturityRuleResult(
            key=rule.key,
            label="Dependencies",
            passed=passed,
            detail=f"{len(entity.dependencies)} declared" if passed else "No dependsOn",
        )
    actual = _scorecard_level(entity, rule.key)
    label = next((dim.label for dim in entity.scorecard if dim.key == rule.key), rule.key)
    passed = _meets_requirement(actual, rule.require)
    detail = (
        f"{actual} (need ≥ {rule.require})"
        if actual is not None
        else f"missing dimension (need ≥ {rule.require})"
    )
    return MaturityRuleResult(key=rule.key, label=label, passed=passed, detail=detail)


def evaluate_maturity(entity: CatalogEntity, rubric: MaturityRubric) -> MaturityResult:
    """Return the highest level whose rules all pass (0 if none)."""
    best = MaturityResult(level=0, label="Unscored", passing=0, total=0, rules=())
    for level_def in sorted(rubric.levels, key=lambda item: item.level):
        results = tuple(_evaluate_rule(entity, rule) for rule in level_def.rules)
        passing = sum(1 for item in results if item.passed)
        total = len(results)
        if passing == total and total > 0:
            best = MaturityResult(
                level=level_def.level,
                label=level_def.label,
                passing=passing,
                total=total,
                rules=results,
            )
        else:
            if best.level == 0 and total:
                best = MaturityResult(
                    level=0,
                    label="Unscored",
                    passing=passing,
                    total=total,
                    rules=results,
                )
            break
    return best
