from __future__ import annotations

import re
from pathlib import Path

_CSS_PATH = Path(__file__).resolve().parents[1] / "src" / "repave_engine" / "static" / "repave.css"
_TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "src" / "repave_engine" / "templates"

_VAR_REF = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*(?:,|\))")
_CSS_DEF = re.compile(r"(?:^|[\s{;])(--[a-z0-9-]+)\s*:", re.MULTILINE)
_BADGE_CLASS = re.compile(r"badge--([a-z0-9-]+)")
_BADGE_RULE = re.compile(r"\.badge--([a-z0-9-]+)(?:[,\s{]|$)")


def _read_css() -> str:
    return _CSS_PATH.read_text(encoding="utf-8")


def _defined_tokens(css: str) -> dict[str, str]:
    defined: dict[str, str] = {}
    for match in _CSS_DEF.finditer(css):
        name = match.group(1)
        start = match.end()
        rest = css[start:]
        value_end = rest.find(";")
        if value_end == -1:
            continue
        defined[name] = rest[:value_end].strip()
    return defined


def _var_refs_without_fallback(css: str) -> set[str]:
    refs: set[str] = set()
    for match in _VAR_REF.finditer(css):
        if match.group(0).rstrip().endswith(")"):
            refs.add(match.group(1))
    return refs


def _resolve_token(name: str, defined: dict[str, str], *, seen: set[str] | None = None) -> bool:
    if name in (seen or set()):
        return False
    if name not in defined:
        return False
    value = defined[name].strip()
    chain = (seen or set()) | {name}
    for inner in _VAR_REF.finditer(value):
        if inner.group(0).rstrip().endswith(","):
            continue
        if not _resolve_token(inner.group(1), defined, seen=chain):
            return False
    return True


def test_root_defines_semantic_alias_tokens() -> None:
    css = _read_css()
    root_match = re.search(r":root\s*\{([^}]+)\}", css, re.DOTALL)
    assert root_match is not None
    root_names = set(_CSS_DEF.findall(root_match.group(1)))
    # Layout / type primitives stay on :root (tier 1).
    for token in ("--radius-lg", "--text-sm", "--dur-fast", "--teal-500"):
        assert token in root_names

    theme_match = re.search(r'\[data-theme="dark"\]\s*\{([^}]+)\}', css, re.DOTALL)
    assert theme_match is not None
    theme_names = set(_CSS_DEF.findall(theme_match.group(1)))
    # Semantic aliases live on the theme seam (tier 2).
    for token in (
        "--border-subtle",
        "--status-pass",
        "--status-fail",
        "--accent",
        "--brand-primary",
        "--brand-primary-hover",
        "--brand-primary-muted",
        "--link",
        "--warning",
        "--success",
        "--error",
    ):
        assert token in theme_names


def test_v3_board_palette_hexes() -> None:
    css = _read_css()
    defined = _defined_tokens(css)
    assert defined.get("--navy-950") == "#0f172a"
    assert defined.get("--slate-500") == "#64748b"
    assert defined.get("--cool-gray-400") == "#94a3b8"
    assert defined.get("--cool-gray-200") == "#e2e8f0"
    assert defined.get("--brand-amber-500") == "#f59e0b"
    assert defined.get("--green-500") == "#22c55e"
    assert defined.get("--rose-500") == "#ef4444"
    assert defined.get("--font-sans", "").startswith('"Inter"')


def test_brand_and_warning_remain_distinct() -> None:
    css = _read_css()
    defined = _defined_tokens(css)
    assert defined.get("--brand-amber-500") == "#f59e0b"
    assert defined.get("--orange-500") == "#f97316"
    # Theme maps brand accent to amber and warning to orange (not the same role).
    assert "var(--brand-primary)" in defined.get("--accent", "")
    assert "var(--orange-500)" in defined.get("--warning", "")


def test_var_refs_without_fallback_resolve_in_stylesheet() -> None:
    css = _read_css()
    defined = _defined_tokens(css)
    unresolved: list[str] = []
    for name in sorted(_var_refs_without_fallback(css)):
        if not _resolve_token(name, defined):
            unresolved.append(name)
    assert not unresolved, f"undefined CSS tokens (no fallback): {unresolved}"


def test_badge_variants_used_in_templates_have_css_rules() -> None:
    css = _read_css()
    rules = set(_BADGE_RULE.findall(css))
    used: set[str] = set()
    for path in _TEMPLATES_DIR.rglob("*.html"):
        used.update(_BADGE_CLASS.findall(path.read_text(encoding="utf-8")))
    missing = sorted(variant for variant in used if variant not in rules)
    assert not missing, f"badge variants used in templates but missing CSS: {missing}"


def test_badge_warn_rule_exists() -> None:
    css = _read_css()
    assert ".badge--warn" in css
