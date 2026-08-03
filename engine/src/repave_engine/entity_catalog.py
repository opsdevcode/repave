"""Developer portal catalog: fleet + modules_root entities and scorecards."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.blueprint import artifact_family
from repave_engine.cost_actuals import CostActualsSummary, tag_coverage_for_fields
from repave_engine.environment_record import EnvironmentRecord
from repave_engine.fleet import FleetEntry, normalize_repo_url
from repave_engine.fleet_operator_status import FleetOperatorStatus
from repave_engine.fleet_view import build_fleet_rows
from repave_engine.yaml_util import load_yaml_mapping_soft

ScoreLevel = Literal["pass", "warn", "fail", "unknown"]

CATALOG_FILENAME = "catalog-info.yaml"
README_FILENAME = "README.md"
RUNBOOK_CANDIDATES = ("RUNBOOK.md", "docs/runbook.md", "docs/operations/README.md")
UPGRADE_CANDIDATES = ("UPGRADE.md", "docs/UPGRADE.md", "docs/upgrade-notes.md")
REMOTE_DOC_PATHS = (
    CATALOG_FILENAME,
    README_FILENAME,
    "repave.yaml",
    *RUNBOOK_CANDIDATES,
    *UPGRADE_CANDIDATES,
)


@dataclass(frozen=True)
class ScorecardDimension:
    key: str
    label: str
    level: ScoreLevel
    detail: str


@dataclass(frozen=True)
class ScorecardRollupCell:
    key: str
    label: str
    pass_count: int
    warn_count: int
    fail_count: int
    unknown_count: int

    @property
    def total(self) -> int:
        return self.pass_count + self.warn_count + self.fail_count + self.unknown_count

    @property
    def worst_level(self) -> ScoreLevel:
        if self.fail_count:
            return "fail"
        if self.warn_count:
            return "warn"
        if self.pass_count:
            return "pass"
        return "unknown"


_LEVEL_RANK: tuple[ScoreLevel, ...] = ("fail", "warn", "unknown", "pass")


@dataclass(frozen=True)
class FleetScorecardRollup:
    entity_count: int
    dimensions: tuple[ScorecardRollupCell, ...]

    @property
    def overall_level(self) -> ScoreLevel:
        if not self.dimensions:
            return "unknown"
        return min(
            self.dimensions,
            key=lambda cell: _LEVEL_RANK.index(cell.worst_level),
        ).worst_level


def rollup_fleet_scorecard(entities: Sequence[CatalogEntity]) -> FleetScorecardRollup:
    if not entities:
        return FleetScorecardRollup(entity_count=0, dimensions=())
    keys: list[tuple[str, str]] = []
    seen: set[str] = set()
    for entity in entities:
        for dim in entity.scorecard:
            if dim.key not in seen:
                seen.add(dim.key)
                keys.append((dim.key, dim.label))
    cells: list[ScorecardRollupCell] = []
    for key, label in keys:
        pass_count = warn_count = fail_count = unknown_count = 0
        for entity in entities:
            match = next((dim for dim in entity.scorecard if dim.key == key), None)
            if match is None:
                unknown_count += 1
                continue
            if match.level == "pass":
                pass_count += 1
            elif match.level == "warn":
                warn_count += 1
            elif match.level == "fail":
                fail_count += 1
            else:
                unknown_count += 1
        cells.append(
            ScorecardRollupCell(
                key=key,
                label=label,
                pass_count=pass_count,
                warn_count=warn_count,
                fail_count=fail_count,
                unknown_count=unknown_count,
            )
        )
    return FleetScorecardRollup(entity_count=len(entities), dimensions=tuple(cells))


@dataclass(frozen=True)
class CatalogEntity:
    entity_id: str
    display_name: str
    repo_url: str | None
    local_path: Path | None
    owner: str
    blueprint_name: str
    blueprint_version: str
    standard_source: str
    standard_version: str
    component_type: str
    lifecycle: str
    operator_phase: str
    operator_message: str
    remediation_pr_url: str
    manifest_name: str
    manifest_namespace: str
    source: str
    scorecard: tuple[ScorecardDimension, ...] = field(default_factory=tuple)
    cost_badge: str = ""
    cost_badge_detail: str = ""
    readme_preview: str = ""
    last_generation_at: str = ""
    last_generation_outcome: str = ""
    cloud_provider: str = ""
    environment_tier: str = ""
    env_class: str = ""
    gitops_repo: str = ""
    gitops_path: str = ""
    expires_at: str = ""
    vend_status: str = ""
    vend_run_id: str = ""
    pull_request_url: str = ""
    source_entity_id: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "entity_id": self.entity_id,
            "display_name": self.display_name,
            "repo_url": self.repo_url,
            "local_path": str(self.local_path) if self.local_path else None,
            "owner": self.owner,
            "blueprint_name": self.blueprint_name,
            "blueprint_version": self.blueprint_version,
            "standard_source": self.standard_source,
            "standard_version": self.standard_version,
            "component_type": self.component_type,
            "lifecycle": self.lifecycle,
            "operator_phase": self.operator_phase,
            "source": self.source,
            "last_generation_at": self.last_generation_at,
            "last_generation_outcome": self.last_generation_outcome,
            "cost_badge": self.cost_badge,
            "cost_badge_detail": self.cost_badge_detail,
            "scorecard": [
                {"key": dim.key, "label": dim.label, "level": dim.level, "detail": dim.detail}
                for dim in self.scorecard
            ],
        }
        if self.source == "environment":
            payload["environment"] = {
                "cloud_provider": self.cloud_provider,
                "tier": self.environment_tier,
                "class": self.env_class,
                "gitops_repo": self.gitops_repo,
                "gitops_path": self.gitops_path,
                "expires_at": self.expires_at,
                "status": self.vend_status,
                "run_id": self.vend_run_id,
                "pull_request_url": self.pull_request_url,
                "source_entity_id": self.source_entity_id,
            }
        return payload


def entity_id_for_repo_url(repo_url: str) -> str:
    normalized = normalize_repo_url(repo_url)
    slug = normalized.replace("https://github.com/", "").strip("/")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-").lower()
    if slug:
        return slug[:120]
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"entity-{digest}"


def _catalog_metadata(repo_dir: Path) -> dict[str, str]:
    doc = load_yaml_mapping_soft(repo_dir / CATALOG_FILENAME)
    if doc is None:
        return {}
    metadata = doc.get("metadata")
    spec = doc.get("spec")
    out: dict[str, str] = {}
    if isinstance(metadata, dict):
        out["display_name"] = str(metadata.get("name", "")).strip()
        out["description"] = str(metadata.get("description", "")).strip()
        annotations = metadata.get("annotations")
        if isinstance(annotations, dict):
            out["blueprint"] = str(annotations.get("repave.dev/blueprint", "")).strip()
    if isinstance(spec, dict):
        out["component_type"] = str(spec.get("type", "")).strip()
        out["lifecycle"] = str(spec.get("lifecycle", "")).strip()
        out["owner"] = str(spec.get("owner", "")).strip()
    return out


def _repave_spec(repo_dir: Path) -> dict[str, Any] | None:
    doc = load_yaml_mapping_soft(repo_dir / "repave.yaml")
    if doc is None:
        return None
    spec = doc.get("spec")
    return spec if isinstance(spec, dict) else None


def _readme_excerpt(repo_dir: Path, *, limit: int = 4000) -> str:
    path = repo_dir / README_FILENAME
    if not path.is_file():
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n\n…"


def _has_runbook(repo_dir: Path) -> bool:
    return any((repo_dir / candidate).is_file() for candidate in RUNBOOK_CANDIDATES)


def _latest_audit_for_name(
    entries: tuple[AuditHistoryEntry, ...],
    *,
    names: set[str],
) -> AuditHistoryEntry | None:
    for entry in entries:
        if entry.module_name in names or entry.blueprint_name in names:
            return entry
    return None


def _cost_scorecard_dimension(
    *,
    owner: str,
    display_name: str,
    cost_actuals: CostActualsSummary | None,
    cost_actuals_configured: bool,
) -> ScorecardDimension:
    if cost_actuals is not None:
        cost_level: ScoreLevel = "pass" if cost_actuals.tag_coverage == "complete" else "warn"
        as_of = cost_actuals.as_of[:19] if cost_actuals.as_of else "unknown"
        cost_detail = f"L30D {cost_actuals.currency} {cost_actuals.amount_30d} as of {as_of}"
    elif cost_actuals_configured:
        coverage, cov_detail = tag_coverage_for_fields(owner, display_name)
        if coverage == "missing":
            cost_level = "warn"
            cost_detail = cov_detail
        else:
            cost_level = "unknown"
            cost_detail = "Cost reader configured; open entity for spend fetch"
    else:
        cost_level = "unknown"
        cost_detail = "Configure portal.cost_reader or cost_actuals_url for cloud spend"
    return ScorecardDimension("cost", "Cloud spend", cost_level, cost_detail)


def apply_cost_to_scorecard(
    scorecard: tuple[ScorecardDimension, ...],
    *,
    owner: str,
    display_name: str,
    cost_actuals: CostActualsSummary | None,
    cost_actuals_configured: bool,
) -> tuple[ScorecardDimension, ...]:
    base = tuple(dim for dim in scorecard if dim.key != "cost")
    return (
        *base,
        _cost_scorecard_dimension(
            owner=owner,
            display_name=display_name,
            cost_actuals=cost_actuals,
            cost_actuals_configured=cost_actuals_configured,
        ),
    )


def build_scorecard(
    *,
    repo_dir: Path | None,
    fleet_entry: FleetEntry | None,
    operator: FleetOperatorStatus | None,
    audit: AuditHistoryEntry | None,
    owner: str = "",
    display_name: str = "",
    cost_actuals: CostActualsSummary | None = None,
    cost_actuals_configured: bool = False,
) -> tuple[ScorecardDimension, ...]:
    dims: list[ScorecardDimension] = []

    if fleet_entry and fleet_entry.blueprint_version and fleet_entry.standard_version:
        pin_level: ScoreLevel = "pass"
        pin_detail = "Blueprint and standard pins recorded in fleet registry"
    elif fleet_entry and fleet_entry.blueprint_name:
        pin_level = "warn"
        pin_detail = "Missing blueprint or standard version on fleet entry"
    else:
        pin_level = "unknown"
        pin_detail = "No fleet registration"
    dims.append(ScorecardDimension("pins", "Pin freshness", pin_level, pin_detail))

    if operator is None or not operator.phase:
        op_level: ScoreLevel = "unknown"
        op_detail = "Operator status not configured"
    elif operator.phase == "Ready":
        op_level = "pass"
        op_detail = operator.message or "In sync with declared pins"
    elif operator.phase == "OutOfDate":
        op_level = "warn"
        op_detail = operator.message or "Drift detected"
    elif operator.phase == "Error":
        op_level = "fail"
        op_detail = operator.message or "Operator error"
    else:
        op_level = "warn"
        op_detail = operator.message or operator.phase
    dims.append(ScorecardDimension("operator", "Operator drift", op_level, op_detail))

    if repo_dir is None:
        prov_level: ScoreLevel = "unknown"
        prov_detail = "No local checkout under modules_root"
    elif _repave_spec(repo_dir) is not None:
        prov_level = "pass"
        prov_detail = "repave.yaml present in local tree"
    else:
        prov_level = "warn"
        prov_detail = "Local tree missing repave.yaml"
    dims.append(ScorecardDimension("provenance", "Provenance file", prov_level, prov_detail))

    if repo_dir is None:
        rb_level: ScoreLevel = "unknown"
        rb_detail = "No local checkout"
    elif _has_runbook(repo_dir):
        rb_level = "pass"
        rb_detail = "Runbook markdown found"
    else:
        rb_level = "warn"
        rb_detail = "No RUNBOOK.md or docs/operations runbook"
    dims.append(ScorecardDimension("runbook", "Runbook", rb_level, rb_detail))

    if audit is None:
        gate_level: ScoreLevel = "unknown"
        gate_detail = "No recent generation in audit log"
    elif audit.gates_outcome == "passed":
        gate_level = "pass"
        gate_detail = f"Last generation passed ({audit.timestamp[:19]})"
    else:
        gate_level = "fail"
        gate_detail = f"Last generation {audit.gates_outcome} ({audit.timestamp[:19]})"
    dims.append(ScorecardDimension("gates", "Last generation", gate_level, gate_detail))

    dims.append(
        _cost_scorecard_dimension(
            owner=owner,
            display_name=display_name,
            cost_actuals=cost_actuals,
            cost_actuals_configured=cost_actuals_configured,
        )
    )

    return tuple(dims)


def _ttl_scorecard_dimension(*, expires_at: str) -> ScorecardDimension:
    if not expires_at.strip():
        return ScorecardDimension("ttl", "TTL", "unknown", "No expiry configured")
    try:
        deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError:
        return ScorecardDimension("ttl", "TTL", "unknown", f"Invalid expiry {expires_at}")
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if deadline <= now:
        return ScorecardDimension("ttl", "TTL", "fail", f"Expired {expires_at[:19]}")
    remaining = deadline - now
    if remaining <= timedelta(hours=24):
        return ScorecardDimension(
            "ttl",
            "TTL",
            "warn",
            f"Expires {expires_at[:19]} ({int(remaining.total_seconds() // 3600)}h left)",
        )
    return ScorecardDimension("ttl", "TTL", "pass", f"Expires {expires_at[:19]}")


def build_environment_scorecard(
    record: EnvironmentRecord,
    *,
    cost_actuals_configured: bool,
    owner: str = "",
    display_name: str = "",
) -> tuple[ScorecardDimension, ...]:
    pin_level: ScoreLevel = "pass" if record.blueprint_version else "warn"
    pin_detail = f"{record.blueprint_name}@{record.blueprint_version or 'unknown'}"
    gate_level: ScoreLevel = "pass" if record.gates_outcome == "passed" else "fail"
    return (
        ScorecardDimension("pins", "Blueprint", pin_level, pin_detail),
        _ttl_scorecard_dimension(expires_at=record.expires_at),
        ScorecardDimension("gates", "Vend gates", gate_level, record.gates_outcome or "unknown"),
        _cost_scorecard_dimension(
            owner=owner or record.owner,
            display_name=display_name or record.stack_name,
            cost_actuals=None,
            cost_actuals_configured=cost_actuals_configured,
        ),
    )


def _entity_from_environment_record(
    record: EnvironmentRecord,
    *,
    cost_actuals_configured: bool = False,
) -> CatalogEntity:
    display = record.stack_name
    return CatalogEntity(
        entity_id=record.entity_id,
        display_name=display,
        repo_url=None,
        local_path=None,
        owner=record.owner,
        blueprint_name=record.blueprint_name,
        blueprint_version=record.blueprint_version,
        standard_source="",
        standard_version="",
        component_type="environment",
        lifecycle=record.environment_tier,
        operator_phase="",
        operator_message="",
        remediation_pr_url="",
        manifest_name=record.stack_name,
        manifest_namespace=record.gitops_path,
        source="environment",
        scorecard=build_environment_scorecard(
            record,
            cost_actuals_configured=cost_actuals_configured,
            owner=record.owner,
            display_name=display,
        ),
        last_generation_at=record.vended_at[:19] if record.vended_at else "",
        last_generation_outcome=record.gates_outcome,
        cloud_provider=record.cloud_provider,
        environment_tier=record.environment_tier,
        env_class=record.env_class,
        gitops_repo=record.gitops_repo,
        gitops_path=record.gitops_path,
        expires_at=record.expires_at,
        vend_status=record.status,
        vend_run_id=record.run_id,
        pull_request_url=record.pull_request_url,
        source_entity_id=record.source_entity_id,
    )


def build_catalog_from_environments(
    records: tuple[EnvironmentRecord, ...] | list[EnvironmentRecord],
    *,
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    return [
        _entity_from_environment_record(item, cost_actuals_configured=cost_actuals_configured)
        for item in records
    ]


def merge_catalog_entities(
    base: list[CatalogEntity],
    extra: list[CatalogEntity],
) -> list[CatalogEntity]:
    seen = {item.entity_id for item in base}
    merged = list(base)
    for item in extra:
        if item.entity_id in seen:
            continue
        merged.append(item)
        seen.add(item.entity_id)
    return merged


def _match_local_dir(modules_root: Path, repo_url: str) -> Path | None:
    if not repo_url or not modules_root.is_dir():
        return None
    tail = normalize_repo_url(repo_url).split("/")[-1]
    direct = modules_root / tail
    if direct.is_dir():
        return direct
    for child in modules_root.iterdir():
        if child.is_dir() and child.name == tail:
            return child
    return None


def _entity_from_fleet_row(
    row: dict[str, Any],
    *,
    repo_dir: Path | None,
    operator: FleetOperatorStatus | None,
    audit: AuditHistoryEntry | None,
    cost_actuals_configured: bool = False,
) -> CatalogEntity:
    repo_url = str(row.get("repo_url", "")).strip() or None
    entity_id = entity_id_for_repo_url(repo_url) if repo_url else "unknown"
    meta = _catalog_metadata(repo_dir) if repo_dir else {}
    display = meta.get("display_name") or (repo_dir.name if repo_dir else entity_id)
    names = {display, str(row.get("blueprint_name", "")), repo_dir.name if repo_dir else ""}
    names = {n for n in names if n}
    fleet_entry = None
    if repo_url:
        fleet_entry = FleetEntry(
            repo_url=repo_url,
            blueprint_name=str(row.get("blueprint_name", "")).strip(),
            blueprint_version=str(row.get("blueprint_version", "")).strip(),
            standard_source=str(row.get("standard_source", "")).strip(),
            standard_version=str(row.get("standard_version", "")).strip(),
            owner=str(row.get("owner", "")).strip(),
            registered_by=str(row.get("registered_by", "")).strip(),
            registered_at=str(row.get("registered_at", "")).strip(),
        )
    return CatalogEntity(
        entity_id=entity_id,
        display_name=display,
        repo_url=repo_url,
        local_path=repo_dir,
        owner=str(row.get("owner") or meta.get("owner", "")).strip(),
        blueprint_name=str(row.get("blueprint_name", "")).strip(),
        blueprint_version=str(row.get("blueprint_version", "")).strip(),
        standard_source=str(row.get("standard_source", "")).strip(),
        standard_version=str(row.get("standard_version", "")).strip(),
        component_type=meta.get("component_type", "component"),
        lifecycle=meta.get("lifecycle", ""),
        operator_phase=str(row.get("operator_phase", "")).strip(),
        operator_message=str(row.get("operator_message", "")).strip(),
        remediation_pr_url=str(row.get("remediation_pr_url", "")).strip(),
        manifest_name=str(row.get("manifest_name", "")).strip(),
        manifest_namespace=str(row.get("manifest_namespace", "default")).strip(),
        source="fleet",
        scorecard=build_scorecard(
            repo_dir=repo_dir,
            fleet_entry=fleet_entry,
            operator=operator,
            audit=audit,
            owner=str(row.get("owner") or meta.get("owner", "")).strip(),
            display_name=display,
            cost_actuals_configured=cost_actuals_configured,
        ),
        readme_preview=_readme_excerpt(repo_dir) if repo_dir else "",
        last_generation_at=audit.timestamp[:19] if audit else "",
        last_generation_outcome=audit.gates_outcome if audit else "",
    )


def _discover_local_entities(
    modules_root: Path,
    *,
    known_urls: set[str],
    skip_dir_names: set[str] | None = None,
    audit_entries: tuple[AuditHistoryEntry, ...],
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    found: list[CatalogEntity] = []
    if not modules_root.is_dir():
        return found
    skip = skip_dir_names or set()
    for entry in sorted(modules_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in skip:
            continue
        spec = _repave_spec(entry)
        if spec is None:
            continue
        meta = _catalog_metadata(entry)
        blueprint = spec.get("blueprint")
        blueprint_map = blueprint if isinstance(blueprint, dict) else {}
        bp_name = str(blueprint_map.get("name", meta.get("blueprint", entry.name))).strip()
        bp_version = str(blueprint_map.get("version", "")).strip()
        standard = spec.get("standard")
        standard_map = standard if isinstance(standard, dict) else {}
        display = meta.get("display_name") or entry.name
        pseudo_url = f"local://{entry.name}"
        if pseudo_url in known_urls:
            continue
        audit = _latest_audit_for_name(audit_entries, names={display, entry.name, bp_name})
        entity = CatalogEntity(
            entity_id=f"local-{entry.name}",
            display_name=display,
            repo_url=None,
            local_path=entry,
            owner=meta.get("owner", ""),
            blueprint_name=bp_name,
            blueprint_version=bp_version,
            standard_source=str(standard_map.get("source", "")).strip(),
            standard_version=str(standard_map.get("version", "")).strip(),
            component_type=meta.get("component_type", "component"),
            lifecycle=meta.get("lifecycle", ""),
            operator_phase="",
            operator_message="",
            remediation_pr_url="",
            manifest_name=entry.name,
            manifest_namespace="local",
            source="modules_root",
            scorecard=build_scorecard(
                repo_dir=entry,
                fleet_entry=None,
                operator=None,
                audit=audit,
                owner=meta.get("owner", ""),
                display_name=display,
                cost_actuals_configured=cost_actuals_configured,
            ),
            readme_preview=_readme_excerpt(entry),
            last_generation_at=audit.timestamp[:19] if audit else "",
            last_generation_outcome=audit.gates_outcome if audit else "",
        )
        found.append(entity)
    return found


def build_catalog_entities(
    *,
    fleet_rows: list[dict[str, Any]],
    modules_root: Path,
    operator_by_url: dict[str, FleetOperatorStatus] | None,
    audit_entries: tuple[AuditHistoryEntry, ...] = (),
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    """Merge fleet registry rows with modules_root discoveries."""
    lookup = operator_by_url or {}
    entities: list[CatalogEntity] = []
    known_urls: set[str] = set()
    linked_dir_names: set[str] = set()

    for row in fleet_rows:
        repo_url = str(row.get("repo_url", "")).strip()
        if repo_url:
            known_urls.add(repo_url)
            linked_dir_names.add(normalize_repo_url(repo_url).split("/")[-1])
        repo_dir = _match_local_dir(modules_root, repo_url) if repo_url else None
        operator = lookup.get(repo_url) if repo_url else None
        meta = _catalog_metadata(repo_dir) if repo_dir else {}
        display = meta.get("display_name") or (repo_dir.name if repo_dir else "")
        names = {
            display,
            str(row.get("blueprint_name", "")),
            repo_dir.name if repo_dir else "",
        }
        audit = _latest_audit_for_name(audit_entries, names={n for n in names if n})
        entities.append(
            _entity_from_fleet_row(
                row,
                repo_dir=repo_dir,
                operator=operator,
                audit=audit,
                cost_actuals_configured=cost_actuals_configured,
            )
        )

    entities.extend(
        _discover_local_entities(
            modules_root,
            known_urls=known_urls,
            skip_dir_names=linked_dir_names,
            audit_entries=audit_entries,
            cost_actuals_configured=cost_actuals_configured,
        )
    )
    return sorted(entities, key=lambda item: item.display_name.lower())


def observability_embed_url(template: str, entity: CatalogEntity) -> str | None:
    raw = template.strip()
    if not raw:
        return None
    try:
        return raw.format(
            name=entity.display_name,
            service=entity.display_name,
            entity_id=entity.entity_id,
        )
    except KeyError:
        return raw.format(name=entity.display_name)


def build_catalog_from_fleet(
    entries: tuple[FleetEntry, ...] | list[FleetEntry],
    *,
    modules_root: Path,
    operator_by_url: dict[str, FleetOperatorStatus] | None = None,
    namespace: str = "default",
    audit_entries: tuple[AuditHistoryEntry, ...] = (),
    cost_actuals_configured: bool = False,
) -> list[CatalogEntity]:
    rows = build_fleet_rows(entries, operator_by_url=operator_by_url, namespace=namespace)
    return build_catalog_entities(
        fleet_rows=rows,
        modules_root=modules_root,
        operator_by_url=operator_by_url,
        audit_entries=audit_entries,
        cost_actuals_configured=cost_actuals_configured,
    )


def find_catalog_entity(
    entities: list[CatalogEntity],
    entity_id: str,
) -> CatalogEntity | None:
    for item in entities:
        if item.entity_id == entity_id:
            return item
    return None


def filter_entities_by_owner(
    entities: Sequence[CatalogEntity],
    owner: str,
) -> list[CatalogEntity]:
    needle = owner.strip().lower()
    if not needle:
        return list(entities)
    return [item for item in entities if needle in item.owner.lower()]


def read_entity_docs(repo_dir: Path) -> dict[str, str]:
    """Load README, runbook, upgrade notes, and provenance from a local entity checkout."""
    out: dict[str, str] = {}
    readme = repo_dir / README_FILENAME
    if readme.is_file():
        with suppress(OSError):
            out["readme"] = readme.read_text(encoding="utf-8", errors="replace")
    for candidate in RUNBOOK_CANDIDATES:
        path = repo_dir / candidate
        if not path.is_file():
            continue
        with suppress(OSError):
            out["runbook"] = path.read_text(encoding="utf-8", errors="replace")
            out["runbook_label"] = candidate
        break
    for candidate in UPGRADE_CANDIDATES:
        path = repo_dir / candidate
        if not path.is_file():
            continue
        with suppress(OSError):
            out["upgrade"] = path.read_text(encoding="utf-8", errors="replace")
            out["upgrade_label"] = candidate
        break
    provenance = repo_dir / "repave.yaml"
    if provenance.is_file():
        with suppress(OSError):
            out["provenance"] = provenance.read_text(encoding="utf-8", errors="replace")
    return out


def fetch_remote_entity_docs(repo_url: str, token: str) -> dict[str, str]:
    """Fetch catalog, docs, and provenance from GitHub when no local checkout exists."""
    from repave_engine.github_inventory import (
        GitHubInventoryError,
        fetch_github_file_text,
        parse_github_repository,
    )

    try:
        owner, repo = parse_github_repository(repo_url)
    except GitHubInventoryError:
        return {}
    out: dict[str, str] = {}
    for rel_path in REMOTE_DOC_PATHS:
        text = fetch_github_file_text(owner, repo, rel_path, token)
        if not text.strip():
            continue
        if rel_path == README_FILENAME:
            out["readme"] = text
        elif rel_path == "repave.yaml":
            out["provenance"] = text
        elif rel_path in UPGRADE_CANDIDATES:
            if "upgrade" not in out:
                out["upgrade"] = text
                out["upgrade_label"] = rel_path
        elif rel_path in RUNBOOK_CANDIDATES:
            if "runbook" not in out:
                out["runbook"] = text
                out["runbook_label"] = rel_path
        elif rel_path == CATALOG_FILENAME:
            out["catalog_info"] = text
    return out


@dataclass(frozen=True)
class EntityLibraryGroup:
    family: str
    title: str
    subtitle: str
    entities: tuple[CatalogEntity, ...]


_LIBRARY_FAMILY_META: dict[str, tuple[str, str]] = {
    "terraform": ("Terraform", "Modules and environment stacks under governance"),
    "ansible": ("Ansible", "Roles, collections, and automation projects"),
    "policy": ("Policy", "Checkov, OPA, and Azure Policy repositories"),
    "observability": ("Observability", "Dashboards, monitors, and telemetry repos"),
    "helm": ("Kubernetes / Helm", "Charts and cluster delivery artifacts"),
    "gitops": ("GitOps delivery", "Argo CD and Flux manifests pinned to a chart version"),
    "app": ("Application services", "Service repos with catalog metadata"),
    "other": ("Other", "Registered or local artifacts"),
}
_LIBRARY_FAMILY_ORDER: tuple[str, ...] = (
    "terraform",
    "ansible",
    "helm",
    "gitops",
    "app",
    "policy",
    "observability",
    "other",
)


def infer_entity_family(
    entity: CatalogEntity,
    blueprint_artifact_types: Mapping[str, str],
) -> str:
    artifact_type = blueprint_artifact_types.get(entity.blueprint_name, "")
    if artifact_type:
        return artifact_family(artifact_type)
    name = (entity.blueprint_name or "").lower()
    if "terraform" in name or name.startswith("tf-"):
        return "terraform"
    if "ansible" in name:
        return "ansible"
    if "opa" in name or "checkov" in name or "policy" in name:
        return "policy"
    if "observ" in name or "monitor" in name or "dashboard" in name:
        return "observability"
    if "gitops" in name:
        return "gitops"
    if "helm" in name:
        return "helm"
    component_type = (entity.component_type or "").lower()
    if component_type in ("service", "website", "library"):
        return "app"
    return "other"


def group_catalog_entities(
    entities: Sequence[CatalogEntity],
    *,
    blueprint_artifact_types: Mapping[str, str] | None = None,
) -> list[EntityLibraryGroup]:
    """Group created artifacts for the portal library (fleet + modules_root)."""
    types = blueprint_artifact_types or {}
    buckets: dict[str, list[CatalogEntity]] = {}
    for entity in entities:
        family = infer_entity_family(entity, types)
        buckets.setdefault(family, []).append(entity)

    groups: list[EntityLibraryGroup] = []
    for family in _LIBRARY_FAMILY_ORDER:
        items = buckets.get(family)
        if not items:
            continue
        title, subtitle = _LIBRARY_FAMILY_META.get(
            family,
            (family.replace("-", " ").title(), "Governed repositories"),
        )
        sorted_items = sorted(items, key=lambda item: item.display_name.lower())
        groups.append(
            EntityLibraryGroup(
                family=family,
                title=title,
                subtitle=subtitle,
                entities=tuple(sorted_items),
            )
        )
    return groups
