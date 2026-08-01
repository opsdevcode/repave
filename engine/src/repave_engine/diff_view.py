"""HTML rendering for unified diffs in the portal."""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from repave_engine.standards_diff import StandardsDiffFile, StandardsDiffResult


@dataclass(frozen=True)
class DiffLine:
    kind: str  # context, add, remove, hunk, meta
    text: str
    old_no: int | None = None
    new_no: int | None = None


def _classify_diff_line(line: str) -> str:
    if line.startswith("+++") or line.startswith("---") or line.startswith("diff --git"):
        return "meta"
    if line.startswith("@@"):
        return "hunk"
    if line.startswith("+"):
        return "add"
    if line.startswith("-"):
        return "remove"
    return "context"


def parse_unified_patch(patch: str) -> tuple[DiffLine, ...]:
    lines: list[DiffLine] = []
    old_no = 0
    new_no = 0
    for raw in patch.splitlines():
        kind = _classify_diff_line(raw)
        if kind == "hunk":
            lines.append(DiffLine(kind=kind, text=raw))
            continue
        if kind == "add":
            new_no += 1
            lines.append(DiffLine(kind=kind, text=raw[1:], new_no=new_no))
            continue
        if kind == "remove":
            old_no += 1
            lines.append(DiffLine(kind=kind, text=raw[1:], old_no=old_no))
            continue
        if kind == "context" and raw.startswith(" "):
            old_no += 1
            new_no += 1
            lines.append(DiffLine(kind=kind, text=raw[1:], old_no=old_no, new_no=new_no))
            continue
        lines.append(DiffLine(kind=kind, text=raw))
    return tuple(lines)


def render_diff_file_html(diff_file: StandardsDiffFile) -> str:
    rows: list[str] = []
    for line in parse_unified_patch(diff_file.patch):
        css = f"diff-line diff-line--{line.kind}"
        old_gutter = str(line.old_no) if line.old_no is not None else ""
        new_gutter = str(line.new_no) if line.new_no is not None else ""
        body = escape(line.text)
        rows.append(
            f'<div class="{css}">'
            f'<span class="diff-line__gutter diff-line__gutter--old">{old_gutter}</span>'
            f'<span class="diff-line__gutter diff-line__gutter--new">{new_gutter}</span>'
            f'<code class="diff-line__text">{body}</code></div>'
        )
    return "\n".join(rows)


def diff_view_models(result: StandardsDiffResult) -> list[dict[str, str]]:
    if not result.available or not result.has_changes:
        return []
    return diff_view_models_from_files(result.files)


def diff_view_models_from_files(files: tuple[StandardsDiffFile, ...]) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    for item in files:
        if not item.patch.strip():
            continue
        models.append({"path": item.path, "html": render_diff_file_html(item)})
    return models
