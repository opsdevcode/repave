"""Safe markdown rendering for portal entity documentation."""

from __future__ import annotations

import html


def render_portal_markdown(text: str) -> str:
    """Render markdown for in-portal docs; falls back to escaped preformatted text."""
    raw = text.strip()
    if not raw:
        return ""
    try:
        from markdown_it import MarkdownIt

        return str(MarkdownIt("commonmark", {"html": False}).render(raw))
    except ImportError:
        escaped = html.escape(text)
        return f'<pre class="panel-code entity-docs__pre">{escaped}</pre>'
