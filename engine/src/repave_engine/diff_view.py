"""HTML rendering for unified diffs in the portal."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from html import escape
from pathlib import Path

from repave_engine.standards_diff import (
    StandardsDiffFile,
    StandardsDiffResult,
    read_standard_file_pair,
)


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


@dataclass(frozen=True)
class SplitDiffRow:
    left: str
    right: str
    kind: str


def build_split_rows(before: str, after: str) -> tuple[SplitDiffRow, ...]:
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    rows: list[SplitDiffRow] = []
    matcher = difflib.SequenceMatcher(None, before_lines, after_lines)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in before_lines[i1:i2]:
                rows.append(SplitDiffRow(left=line, right=line, kind="context"))
            continue
        if tag == "delete":
            for line in before_lines[i1:i2]:
                rows.append(SplitDiffRow(left=line, right="", kind="remove"))
            continue
        if tag == "insert":
            for line in after_lines[j1:j2]:
                rows.append(SplitDiffRow(left="", right=line, kind="add"))
            continue
        old_chunk = before_lines[i1:i2]
        new_chunk = after_lines[j1:j2]
        span = max(len(old_chunk), len(new_chunk))
        for index in range(span):
            left = old_chunk[index] if index < len(old_chunk) else ""
            right = new_chunk[index] if index < len(new_chunk) else ""
            if left and right:
                kind = "change"
            elif left:
                kind = "remove"
            else:
                kind = "add"
            rows.append(SplitDiffRow(left=left, right=right, kind=kind))
    return tuple(rows)


def render_split_diff_html(
    rows: tuple[SplitDiffRow, ...],
    *,
    left_label: str,
    right_label: str,
) -> str:
    body_rows: list[str] = []
    for row in rows:
        left_class = f"diff-split__cell diff-split__cell--{row.kind}"
        right_class = f"diff-split__cell diff-split__cell--{row.kind}"
        left_text = escape(row.left) if row.left else ""
        right_text = escape(row.right) if row.right else ""
        body_rows.append(
            f'<div class="diff-split__row diff-split__row--{row.kind}">'
            f'<code class="{left_class}">{left_text}</code>'
            f'<code class="{right_class}">{right_text}</code>'
            "</div>"
        )
    return (
        '<div class="diff-split">'
        f'<div class="diff-split__header">'
        f'<span class="diff-split__label">{escape(left_label)}</span>'
        f'<span class="diff-split__label">{escape(right_label)}</span>'
        "</div>"
        f'<div class="diff-split__body">{"".join(body_rows)}</div>'
        "</div>"
    )


def split_diff_view_models(
    repo_root: Path,
    result: StandardsDiffResult,
    *,
    max_lines: int = 400,
) -> list[dict[str, str]]:
    if not result.available or not result.has_changes:
        return []
    left_label = f"Pinned @ {result.pinned_version}"
    right_label = "Platform HEAD"
    models: list[dict[str, str]] = []
    for item in result.files:
        if not item.patch.strip():
            continue
        before, after = read_standard_file_pair(repo_root, result, item)
        if not before.strip() and not after.strip():
            continue
        rows = build_split_rows(before, after)
        if len(rows) > max_lines:
            rows = rows[:max_lines]
        if not rows:
            continue
        models.append(
            {
                "path": item.path,
                "html": render_split_diff_html(
                    rows,
                    left_label=left_label,
                    right_label=right_label,
                ),
            }
        )
    return models
