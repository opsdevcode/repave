"""Fill golden-path name and description from Guided selections."""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from typing import Any

_PLACEHOLDER = re.compile(r"\{([a-z][a-z0-9_]*)\}")
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_UNDERSCORE_NAME_FIELDS = frozenset(
    {"role_name", "collection_name", "sample_role_name", "namespace"}
)


def slugify_identity(value: str, *, separator: str = "-") -> str:
    """Turn a selection (or comma-separated list) into a repo-safe slug."""
    text = str(value).strip().lower().rstrip("/")
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    parts = [part.strip() for part in text.replace(",", " ").split() if part.strip()]
    slugs: list[str] = []
    for part in parts:
        slug = _NON_SLUG.sub(separator, part).strip(separator)
        slug = re.sub(rf"{re.escape(separator)}{{2,}}", separator, slug)
        if slug:
            slugs.append(slug)
    return separator.join(slugs)


def humanize_identity(value: str) -> str:
    """Readable phrase for description templates."""
    text = str(value).strip()
    if not text:
        return ""
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(parts) > 1:
        return ", ".join(parts)
    return text.replace("_", " ").replace("-", " ")


def render_guided_from(
    template: str,
    values: Mapping[str, Any],
    *,
    slug: bool,
    separator: str = "-",
) -> str:
    """Render a guided_from template. Empty when any placeholder is unset."""
    text = str(template).strip()
    if not text:
        return ""
    rendered_parts: list[str] = []
    cursor = 0
    for match in _PLACEHOLDER.finditer(text):
        key = match.group(1)
        raw = str(values.get(key, "")).strip()
        if not raw:
            return ""
        rendered_parts.append(text[cursor : match.start()])
        if slug:
            rendered_parts.append(slugify_identity(raw, separator=separator))
        else:
            rendered_parts.append(humanize_identity(raw))
        cursor = match.end()
    rendered_parts.append(text[cursor:])
    rendered = "".join(rendered_parts).strip()
    if not rendered:
        return ""
    if slug:
        return slugify_identity(rendered, separator=separator)
    return re.sub(r"\s+", " ", rendered)


def apply_guided_identity(blueprint: Any, values: MutableMapping[str, Any]) -> None:
    """Fill empty identity fields from each input's guided_from template.

    Two passes so a later field can reference a name filled in the first pass
    (for example Helm ``app_name`` from ``chart_name``).
    """
    inputs = getattr(blueprint, "inputs", ())
    for _ in range(2):
        for field in inputs:
            template = str(getattr(field, "guided_from", "") or "").strip()
            if not template:
                continue
            if not bool(getattr(field, "required", False)):
                continue
            current = str(values.get(field.name, "")).strip()
            if current:
                continue
            separator = "_" if field.name in _UNDERSCORE_NAME_FIELDS else "-"
            slug = field.name != "description"
            rendered = render_guided_from(
                template,
                values,
                slug=slug,
                separator=separator,
            )
            if rendered:
                values[field.name] = rendered
