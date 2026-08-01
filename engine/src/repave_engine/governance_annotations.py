"""Governance annotations: file preview with policy and standard gutter markers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from repave_engine.policy_catalog import PolicyRule
from repave_engine.standards_diff import StandardsDiffFile, StandardsDiffResult

_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_WORD = re.compile(r"[a-z0-9]{4,}")


@dataclass(frozen=True)
class LineMarker:
    kind: str  # policy | standard
    label: str
    detail: str


@dataclass(frozen=True)
class AnnotatedLine:
    number: int
    text: str
    syntax: str
    markers: tuple[LineMarker, ...]


@dataclass(frozen=True)
class GovernancePreview:
    path: str
    html: str
    annotation_count: int

    def to_public_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "annotation_count": self.annotation_count,
        }


def _keywords(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def _rules_for_path(relative_path: str, rules: tuple[PolicyRule, ...]) -> tuple[PolicyRule, ...]:
    normalized = relative_path.replace("\\", "/").lstrip("/")
    matched: list[PolicyRule] = []
    for rule in rules:
        for attr in (rule.rego_file, rule.definition_file):
            if not attr:
                continue
            candidate = attr.replace("\\", "/").lstrip("/")
            if normalized.endswith(candidate) or candidate.endswith(normalized):
                matched.append(rule)
                break
    return tuple(matched)


def _match_rules_to_line(line: str, rules: tuple[PolicyRule, ...]) -> tuple[PolicyRule, ...]:
    lower = line.lower()
    if not lower.strip():
        return ()
    hits: list[PolicyRule] = []
    for rule in rules:
        keys = _keywords(rule.title)
        if not keys:
            continue
        overlap = sum(1 for key in keys if key in lower)
        if overlap >= 2 or (len(keys) == 1 and overlap == 1):
            hits.append(rule)
    return tuple(hits[:2])


def _syntax_class(line: str, *, in_fence: bool) -> str:
    if in_fence:
        return "code"
    stripped = line.strip()
    if not stripped:
        return "blank"
    heading = _HEADING.match(stripped)
    if heading:
        level = len(heading.group(1))
        return f"heading heading--{level}"
    if stripped.startswith(("- ", "* ", "1. ")):
        return "list"
    if stripped.startswith("```"):
        return "fence"
    return "text"


def annotate_file_lines(
    text: str,
    *,
    relative_path: str,
    policy_rules: tuple[PolicyRule, ...],
) -> tuple[AnnotatedLine, ...]:
    path_rules = _rules_for_path(relative_path, policy_rules)
    lines = text.splitlines()
    annotated: list[AnnotatedLine] = []
    section_title = ""
    in_fence = False
    for index, raw in enumerate(lines, start=1):
        syntax = _syntax_class(raw, in_fence=in_fence)
        if syntax == "fence":
            in_fence = not in_fence
        heading = _HEADING.match(raw.strip())
        if heading:
            section_title = heading.group(2).strip()
        markers: list[LineMarker] = []
        if section_title and syntax in ("text", "list"):
            markers.append(
                LineMarker(
                    kind="standard",
                    label="std",
                    detail=f"Section: {section_title}",
                )
            )
        for rule in path_rules:
            markers.append(
                LineMarker(
                    kind="policy",
                    label=rule.id.split(":")[-1][:12],
                    detail=rule.title,
                )
            )
        for rule in _match_rules_to_line(raw, policy_rules):
            if any(item.detail == rule.title for item in markers):
                continue
            markers.append(
                LineMarker(
                    kind="policy",
                    label=rule.id.split(":")[-1][:12],
                    detail=rule.title,
                )
            )
        annotated.append(
            AnnotatedLine(
                number=index,
                text=raw,
                syntax=syntax,
                markers=tuple(markers[:3]),
            )
        )
    return tuple(annotated)


def render_annotated_lines_html(lines: tuple[AnnotatedLine, ...]) -> str:
    rows: list[str] = []
    for line in lines:
        marker_html = ""
        if line.markers:
            badges = []
            for marker in line.markers:
                css = "gov-marker gov-marker--policy"
                if marker.kind == "standard":
                    css = "gov-marker gov-marker--standard"
                badges.append(
                    f'<span class="{css}" title="{escape(marker.detail)}">'
                    f"{escape(marker.label)}</span>"
                )
            marker_html = "".join(badges)
        rows.append(
            f'<div class="gov-line gov-line--{line.syntax}">'
            f'<span class="gov-line__markers">{marker_html}</span>'
            f'<span class="gov-line__lineno">{line.number}</span>'
            f'<code class="gov-line__text">{escape(line.text)}</code>'
            f"</div>"
        )
    return "\n".join(rows)


def _previews_from_pinned_standard(
    repo_root: Path,
    standards: StandardsDiffResult,
    policy_rules: tuple[PolicyRule, ...],
    *,
    max_lines: int,
    max_files: int = 2,
) -> list[GovernancePreview]:
    standard_dir = repo_root / standards.standard_source.strip().strip("/")
    if not standard_dir.is_dir():
        return []
    previews: list[GovernancePreview] = []
    for path in sorted(standard_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".yaml", ".yml", ".rego"}:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not content.strip():
            continue
        relative = path.relative_to(repo_root).as_posix()
        truncated = content
        if len(content.splitlines()) > max_lines:
            truncated = "\n".join(content.splitlines()[:max_lines]) + "\n…"
        lines = annotate_file_lines(
            truncated,
            relative_path=relative,
            policy_rules=policy_rules,
        )
        count = sum(1 for line in lines if line.markers)
        previews.append(
            GovernancePreview(
                path=relative,
                html=render_annotated_lines_html(lines),
                annotation_count=count,
            )
        )
        if len(previews) >= max_files:
            break
    return previews


def _read_standard_file(
    repo_root: Path,
    standards: StandardsDiffResult,
    diff_file: StandardsDiffFile,
) -> str:
    rel = diff_file.path.strip().lstrip("/")
    candidates = [
        repo_root / rel,
        repo_root / standards.standard_source / Path(rel).name,
    ]
    for path in candidates:
        if path.is_file():
            try:
                return path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""
    return ""


def build_governance_previews(
    repo_root: Path,
    standards: StandardsDiffResult,
    policy_rules: tuple[PolicyRule, ...],
    *,
    max_lines: int = 220,
) -> list[GovernancePreview]:
    if not standards.available:
        return []
    if standards.has_changes:
        previews: list[GovernancePreview] = []
        for diff_file in standards.files:
            if not diff_file.patch.strip():
                continue
            content = _read_standard_file(repo_root, standards, diff_file)
            if not content.strip():
                continue
            truncated = content
            if len(content.splitlines()) > max_lines:
                truncated = "\n".join(content.splitlines()[:max_lines]) + "\n…"
            lines = annotate_file_lines(
                truncated,
                relative_path=diff_file.path,
                policy_rules=policy_rules,
            )
            count = sum(1 for line in lines if line.markers)
            previews.append(
                GovernancePreview(
                    path=diff_file.path,
                    html=render_annotated_lines_html(lines),
                    annotation_count=count,
                )
            )
        return previews
    return _previews_from_pinned_standard(
        repo_root,
        standards,
        policy_rules,
        max_lines=max_lines,
    )
