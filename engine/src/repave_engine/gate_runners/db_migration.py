from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

from repave_engine.gate_registry import GateContext, GateResult

_DESTRUCTIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+COLUMN\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+DATABASE\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+SCHEMA\b", re.IGNORECASE),
    re.compile(r"\bDROP\s+VIEW\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\b", re.IGNORECASE),
    re.compile(r"\bRENAME\s+(TABLE|COLUMN)\b", re.IGNORECASE),
    re.compile(r"\bop\.drop_table\b"),
    re.compile(r"\bop\.drop_column\b"),
)
_FLYWAY_VERSION = re.compile(r"^V(\d+)__", re.IGNORECASE)
_COMMENT_LINE = re.compile(r"^\s*(#|--)")
_ALEMBIC_UPGRADE = re.compile(r"def upgrade\b.*?:(.*?)(?=\ndef |\Z)", re.DOTALL)


@dataclass(frozen=True)
class DestructiveWaiver:
    path: str
    reason: str
    expires_at: date


def _strip_comments(text: str) -> str:
    lines = [line for line in text.splitlines() if not _COMMENT_LINE.match(line)]
    return "\n".join(lines)


def _detect_tool(output_dir: Path, ctx: GateContext) -> str:
    configured = ctx.config("migration-policy").get("tool") or ctx.config("migration-rollback").get(
        "tool"
    )
    raw = str(configured or "").strip().lower()
    if raw in {"alembic", "flyway", "atlas"}:
        return raw
    if any((output_dir / "alembic" / "versions").glob("*.py")):
        return "alembic"
    if any((output_dir / "sql").glob("V*.sql")):
        return "flyway"
    migrations = output_dir / "migrations"
    if migrations.is_dir() and any(
        path.is_file() and not path.name.endswith(".down.sql") for path in migrations.glob("*.sql")
    ):
        return "atlas"
    return ""


def _forward_files(output_dir: Path, tool: str) -> list[Path]:
    if tool == "alembic":
        root = output_dir / "alembic" / "versions"
        return sorted(path for path in root.glob("*.py") if path.is_file()) if root.is_dir() else []
    if tool == "flyway":
        root = output_dir / "sql"
        return (
            sorted(path for path in root.glob("V*.sql") if path.is_file()) if root.is_dir() else []
        )
    if tool == "atlas":
        root = output_dir / "migrations"
        if not root.is_dir():
            return []
        return sorted(
            path
            for path in root.glob("*.sql")
            if path.is_file() and not path.name.endswith(".down.sql")
        )
    return []


def _rel(output_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(output_dir.resolve()))
    except ValueError:
        return str(path)


def _load_waivers(output_dir: Path, ctx: GateContext) -> tuple[DestructiveWaiver, ...]:
    raw_path = str(ctx.config("migration-policy").get("waivers_file", "waivers/destructive.yaml"))
    waiver_file = output_dir / raw_path.strip()
    if not waiver_file.is_file():
        return ()
    loaded = yaml.safe_load(waiver_file.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return ()
    rows = loaded.get("waivers")
    if not isinstance(rows, list):
        return ()
    parsed: list[DestructiveWaiver] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path", "")).strip()
        reason = str(item.get("reason", "")).strip()
        expires_raw = str(item.get("expires_at", "")).strip()
        if not path or not reason or not expires_raw:
            continue
        try:
            expires_at = date.fromisoformat(expires_raw)
        except ValueError:
            continue
        parsed.append(DestructiveWaiver(path=path, reason=reason, expires_at=expires_at))
    return tuple(parsed)


def _waiver_for(rel_path: str, waivers: tuple[DestructiveWaiver, ...]) -> DestructiveWaiver | None:
    for waiver in waivers:
        if rel_path == waiver.path or rel_path.endswith(waiver.path):
            return waiver
    return None


def _forward_source(tool: str, text: str) -> str:
    if tool != "alembic":
        return text
    match = _ALEMBIC_UPGRADE.search(text)
    return match.group(1) if match else text


def _destructive_hits(text: str) -> tuple[str, ...]:
    scanned = _strip_comments(text)
    found: list[str] = []
    for pattern in _DESTRUCTIVE_PATTERNS:
        match = pattern.search(scanned)
        if match and match.group(0) not in found:
            found.append(match.group(0))
    return tuple(found)


def run_migration_policy(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "db-migration":
        return GateResult(
            "migration-policy", True, True, "migration-policy gate not applicable; skipped"
        )
    tool = _detect_tool(output_dir, ctx)
    forwards = _forward_files(output_dir, tool)
    if not forwards:
        return GateResult(
            "migration-policy",
            False,
            False,
            "no forward migrations found; add alembic/versions, sql/V*.sql, or "
            "migrations/*.sql (set gate_config.migration-policy.tool)",
        )
    waivers = _load_waivers(output_dir, ctx)
    today = date.today()
    problems: list[str] = []
    for path in forwards:
        rel = _rel(output_dir, path)
        hits = _destructive_hits(_forward_source(tool, path.read_text(encoding="utf-8")))
        if not hits:
            continue
        waiver = _waiver_for(rel, waivers)
        if waiver is None:
            problems.append(
                f"{rel}: destructive DDL {', '.join(hits)}; add path/reason/expires_at "
                "in waivers/destructive.yaml"
            )
            continue
        if waiver.expires_at < today:
            problems.append(
                f"{rel}: waiver expired {waiver.expires_at.isoformat()}; "
                "extend expires_at or restore the objects"
            )
    if problems:
        return GateResult("migration-policy", False, False, "; ".join(problems))
    return GateResult("migration-policy", True, False, "no unwaived destructive DDL")


def _flyway_undo(output_dir: Path, version: str) -> bool:
    root = output_dir / "sql"
    if not root.is_dir():
        return False
    return any(path.name.upper().startswith(f"U{version}__") for path in root.glob("U*.sql"))


def run_migration_rollback(ctx: GateContext) -> GateResult:
    output_dir = ctx.output_dir
    if ctx.blueprint is not None and ctx.blueprint.artifact_type != "db-migration":
        return GateResult(
            "migration-rollback", True, True, "migration-rollback gate not applicable; skipped"
        )
    tool = _detect_tool(output_dir, ctx)
    forwards = _forward_files(output_dir, tool)
    if not forwards:
        return GateResult(
            "migration-rollback",
            False,
            False,
            "no forward migrations found; add alembic/versions, sql/V*.sql, or "
            "migrations/*.sql (set gate_config.migration-rollback.tool)",
        )
    missing: list[str] = []
    for path in forwards:
        rel = _rel(output_dir, path)
        if tool == "alembic":
            text = path.read_text(encoding="utf-8")
            if "def downgrade" not in text:
                missing.append(f"{rel}: add def downgrade")
        elif tool == "flyway":
            match = _FLYWAY_VERSION.match(path.name)
            if match is None or not _flyway_undo(output_dir, match.group(1)):
                missing.append(f"{rel}: add sql/U{match.group(1) if match else '?'}__*.sql")
        elif tool == "atlas":
            down = path.with_name(f"{path.stem}.down.sql")
            if not down.is_file():
                missing.append(f"{rel}: add {down.name}")
    if missing:
        return GateResult("migration-rollback", False, False, "; ".join(missing))
    return GateResult("migration-rollback", True, False, "every forward migration has a rollback")
