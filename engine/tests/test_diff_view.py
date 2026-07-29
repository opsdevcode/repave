from __future__ import annotations

from repave_engine.diff_view import parse_unified_patch, render_diff_file_html
from repave_engine.standards_diff import StandardsDiffFile


def test_parse_unified_patch_classifies_lines() -> None:
    patch = """diff --git a/foo b/foo
--- a/foo
+++ b/foo
@@ -1 +1 @@
-old
+new
 context
"""
    lines = parse_unified_patch(patch)
    kinds = [line.kind for line in lines]
    assert "meta" in kinds
    assert "hunk" in kinds
    assert "add" in kinds
    assert "remove" in kinds


def test_render_diff_file_html_escapes_body() -> None:
    diff = StandardsDiffFile(path="standards/x.md", patch="--- a/x\n+++ b/x\n@@\n+<script>\n")
    html = render_diff_file_html(diff)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
