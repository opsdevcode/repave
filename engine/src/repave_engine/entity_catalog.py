"""Developer portal catalog: fleet + modules_root entities and scorecards."""

from __future__ import annotations

import hashlib
import re
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from repave_engine.audit_history import AuditHistoryEntry
from repave_engine.fleet import FleetEntry, normalize_repo_url
from repave_engine.fleet_operator_status import FleetOperatorStatus
from repave_engine.fleet_view import build_fleet_rows

ScoreLevel = Literal["pass", "warn", "fail", "unknown"]

CATALOG_FILENAME = "catalog-info.yaml"
README_FILENAME = "README.md"
RUNBOOK_CANDIDATES = ("RUNBOOK.md", "docs/runbook.md", "docs/operations/README.md")


@dataclass(frozen=True)
class ScorecardDimension:
    key: str
    label: str
    level: ScoreLevel
    detail: str


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
    readme_preview: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        return {
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
            "scorecard": [
                {"key": dim.key, "label": dim.label, "level": dim.level, "detail": dim.detail}
                for dim in self.scorecard
            ],
        }


def entity_id_for_repo_url(repo_url: str) -> str:
    normalized = normalize_repo_url(repo_url)
    slug = normalized.replace("https://github.com/", "").strip("/")
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", slug).strip("-").lower()
    if slug:
        return slug[:120]
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:12]
    return f"entity-{digest}"


def _load_yaml_mapping(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _catalog_metadata(repo_dir: Path) -> dict[str, str]:
    doc = _load_yaml_mapping(repo_dir / CATALOG_FILENAME)
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
    doc = _load_yaml_mapping(repo_dir / "repave.yaml")
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


def build_scorecard(
    *,
    repo_dir: Path | None,
    fleet_entry: FleetEntry | None,
    operator: FleetOperatorStatus | None,
    audit: AuditHistoryEntry | None,
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

    return tuple(dims)


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
        ),
        readme_preview=_readme_excerpt(repo_dir) if repo_dir else "",
    )


def _discover_local_entities(
    modules_root: Path,
    *,
    known_urls: set[str],
    skip_dir_names: set[str] | None = None,
    audit_entries: tuple[AuditHistoryEntry, ...],
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
            ),
            readme_preview=_readme_excerpt(entry),
        )
        found.append(entity)
    return found


def build_catalog_entities(
    *,
    fleet_rows: list[dict[str, Any]],
    modules_root: Path,
    operator_by_url: dict[str, FleetOperatorStatus] | None,
    audit_entries: tuple[AuditHistoryEntry, ...] = (),
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
            _entity_from_fleet_row(row, repo_dir=repo_dir, operator=operator, audit=audit)
        )

    entities.extend(
        _discover_local_entities(
            modules_root,
            known_urls=known_urls,
            skip_dir_names=linked_dir_names,
            audit_entries=audit_entries,
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
) -> list[CatalogEntity]:
    rows = build_fleet_rows(entries, operator_by_url=operator_by_url, namespace=namespace)
    return build_catalog_entities(
        fleet_rows=rows,
        modules_root=modules_root,
        operator_by_url=operator_by_url,
        audit_entries=audit_entries,
    )


def find_catalog_entity(
    entities: list[CatalogEntity],
    entity_id: str,
) -> CatalogEntity | None:
    for item in entities:
        if item.entity_id == entity_id:
            return item
    return None


def read_entity_docs(repo_dir: Path) -> dict[str, str]:
    """Load README and runbook markdown from a local entity checkout."""
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
    return out
