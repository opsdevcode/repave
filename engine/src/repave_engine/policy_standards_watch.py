from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

STANDARDS_WATCH_REL = Path("policy/standards-watch.json")
STANDARDS_SNAPSHOT_REL = Path("policy/standards-watch.snapshot.json")
STANDARDS_REPORT_REL = Path("policy/standards-watch.report.md")

USER_AGENT = "repave-policy-standards-watch/1.0 (+https://github.com/opsdevcode/repave)"


@dataclass(frozen=True)
class WatchSource:
    id: str
    url: str
    kind: str
    notes: str
    json_path: str | None = None


@dataclass(frozen=True)
class SourceSnapshot:
    sha256: str
    extracted: str | None
    http_status: int
    error: str | None = None


def load_watch_config(repo_root: Path) -> tuple[str, tuple[WatchSource, ...]]:
    path = repo_root / STANDARDS_WATCH_REL
    data = json.loads(path.read_text(encoding="utf-8"))
    version = str(data.get("version", "1.0.0"))
    sources: list[WatchSource] = []
    for raw in data.get("sources", []):
        if not isinstance(raw, dict):
            continue
        sources.append(
            WatchSource(
                id=str(raw["id"]),
                url=str(raw["url"]),
                kind=str(raw.get("kind", "text")),
                notes=str(raw.get("notes", "")),
                json_path=str(raw["json_path"]) if raw.get("json_path") else None,
            )
        )
    return version, tuple(sources)


def load_snapshot(repo_root: Path) -> dict[str, Any]:
    path = repo_root / STANDARDS_SNAPSHOT_REL
    if not path.is_file():
        return {"version": "1.0.0", "sources": {}}
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _fetch(url: str) -> tuple[int, bytes, str | None]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        return 0, b"", f"URL must use https: {url!r}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:  # nosec B310
            body = response.read()
            return int(response.status), body, None
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read() if exc.fp else b"", str(exc)
    except urllib.error.URLError as exc:
        return 0, b"", str(exc.reason)


def _extract_value(kind: str, body: bytes, json_path: str | None) -> str | None:
    if kind == "json" and json_path:
        try:
            payload = json.loads(body.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None
        current: Any = payload
        for part in json_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return None
            current = current[part]
        return str(current)
    if kind == "html":
        text = body.decode("utf-8", errors="replace")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:512]
    text = body.decode("utf-8", errors="replace")
    return text[:512]


def snapshot_source(source: WatchSource) -> SourceSnapshot:
    status, body, error = _fetch(source.url)
    digest = hashlib.sha256(body).hexdigest()
    extracted = _extract_value(source.kind, body, source.json_path) if body else None
    return SourceSnapshot(
        sha256=digest,
        extracted=extracted,
        http_status=status,
        error=error,
    )


def check_standards_watch(
    repo_root: Path,
    *,
    update: bool = False,
) -> tuple[bool, str]:
    """Return (changed, report_markdown)."""
    _, sources = load_watch_config(repo_root)
    previous = load_snapshot(repo_root)
    prev_sources = previous.get("sources", {})
    if not isinstance(prev_sources, dict):
        prev_sources = {}

    now = datetime.now(tz=timezone.utc).isoformat()
    next_sources: dict[str, Any] = {}
    changes: list[str] = []

    for source in sources:
        snap = snapshot_source(source)
        prev = prev_sources.get(source.id, {})
        prev_hash = str(prev.get("sha256", "")) if isinstance(prev, dict) else ""
        changed = bool(prev_hash and prev_hash != snap.sha256)
        if prev_hash and changed:
            changes.append(source.id)
        next_sources[source.id] = {
            "url": source.url,
            "sha256": snap.sha256,
            "http_status": snap.http_status,
            "extracted": snap.extracted,
            "error": snap.error,
            "checked_at": now,
            "notes": source.notes,
        }

    first_run = not prev_sources
    changed_any = bool(changes) or first_run

    report_lines = [
        "# Policy standards watch report",
        "",
        f"Checked at: {now}",
        "",
    ]
    if first_run and update:
        report_lines.append("Initial snapshot written (no drift comparison yet).")
    elif changes:
        report_lines.append("## Changed sources")
        report_lines.append("")
        for source_id in changes:
            report_lines.append(f"- `{source_id}`")
        report_lines.append("")
        report_lines.append(
            "Review upstream guidance and update `policy/catalog.json`, packs, "
            "and blueprint pins as needed."
        )
    else:
        report_lines.append("No drift detected since the last snapshot.")

    report_lines.extend(["", "## Sources", ""])
    for source in sources:
        entry = next_sources[source.id]
        report_lines.append(f"### `{source.id}`")
        report_lines.append(f"- URL: {source.url}")
        if entry.get("extracted"):
            report_lines.append(f"- Extracted: `{entry['extracted']}`")
        report_lines.append(f"- SHA-256: `{entry['sha256']}`")
        if entry.get("error"):
            report_lines.append(f"- Fetch error: {entry['error']}")
        report_lines.append("")

    report = "\n".join(report_lines).rstrip() + "\n"

    if update:
        snapshot_payload = {
            "version": "1.0.0",
            "updated_at": now,
            "sources": next_sources,
        }
        snapshot_path = repo_root / STANDARDS_SNAPSHOT_REL
        snapshot_path.write_text(json.dumps(snapshot_payload, indent=2) + "\n", encoding="utf-8")
        report_path = repo_root / STANDARDS_REPORT_REL
        report_path.write_text(report, encoding="utf-8")

    return changed_any and bool(changes), report
