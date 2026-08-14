"""One-shot renderer for v3 platform-layer SVG marks. Not imported at runtime."""

from __future__ import annotations

import math
from pathlib import Path

COS = math.sqrt(3) / 2
SIN = 0.5
ROOT = Path(__file__).resolve().parent
SVG = ROOT / "assets" / "svg"
FAV = ROOT / "assets" / "favicon"


def iso(x: float, y: float, z: float) -> tuple[float, float]:
    return (x - y) * COS, (x + y) * SIN - z


def _poly(points: list[tuple[float, float]], ox: float, oy: float) -> str:
    return " ".join(f"{ox + x:.2f},{oy + y:.2f}" for x, y in points)


def _box(
    ox: float, oy: float, oz: float, w: float, d: float, h: float
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], list[tuple[float, float]]]:
    top = [
        iso(ox, oy, oz + h),
        iso(ox + w, oy, oz + h),
        iso(ox + w, oy + d, oz + h),
        iso(ox, oy + d, oz + h),
    ]
    east = [
        iso(ox + w, oy, oz + h),
        iso(ox + w, oy + d, oz + h),
        iso(ox + w, oy + d, oz),
        iso(ox + w, oy, oz),
    ]
    south = [
        iso(ox, oy + d, oz + h),
        iso(ox + w, oy + d, oz + h),
        iso(ox + w, oy + d, oz),
        iso(ox, oy + d, oz),
    ]
    return top, east, south


def _path_d(points: list[tuple[float, float]], ox: float, oy: float) -> str:
    start, *rest = points
    parts = [f"M {ox + start[0]:.2f} {oy + start[1]:.2f}"]
    i = 0
    while i < len(rest):
        if i + 2 < len(rest):
            c1, c2, end = rest[i], rest[i + 1], rest[i + 2]
            parts.append(
                f"C {ox + c1[0]:.2f} {oy + c1[1]:.2f}, "
                f"{ox + c2[0]:.2f} {oy + c2[1]:.2f}, "
                f"{ox + end[0]:.2f} {oy + end[1]:.2f}"
            )
            i += 3
        else:
            p = rest[i]
            parts.append(f"L {ox + p[0]:.2f} {oy + p[1]:.2f}")
            i += 1
    return " ".join(parts)


W, D, H, GAP = 26.0, 20.0, 4.6, 3.4
POSTS = (
    (6.0, 5.0, 5.5),
    (11.0, 4.0, 9.0),
    (16.0, 7.0, 6.5),
    (8.0, 12.0, 4.0),
    (19.0, 11.0, 11.0),
    (13.0, 15.0, 7.5),
    (22.0, 8.0, 5.0),
)
PATH_XY = (
    (3.5, 4.0),
    (9.0, 5.5),
    (14.0, 7.0),
    (12.0, 11.5),
    (10.5, 14.0),
    (16.0, 15.5),
    (22.5, 16.5),
)


def _geometry() -> dict[str, object]:
    slabs = []
    z = 0.0
    for _ in range(3):
        slabs.append(_box(0.0, 0.0, z, W, D, H))
        z += H + GAP
    z_top = 2 * (H + GAP) + H
    path_pts = [iso(x, y, z_top) for x, y in PATH_XY]
    posts = [(iso(x, y, z_top), iso(x, y, z_top + height)) for x, y, height in POSTS]
    pts: list[tuple[float, float]] = []
    for top, east, south in slabs:
        pts.extend(top + east + south)
    for a, b in posts:
        pts.extend((a, b))
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ox = 40.0 - (min(xs) + max(xs)) / 2
    oy = 42.0 - (min(ys) + max(ys)) / 2
    return {"slabs": slabs, "path": path_pts, "posts": posts, "ox": ox, "oy": oy}


PALETTES = {
    "light": {
        "top": ("#334155", "#1E293B", "#0F172A"),
        "east": ("#64748B", "#475569", "#334155"),
        "south": ("#0F172A", "#020617", "#020617"),
        "path": "#F59E0B",
        "glow": "#F59E0B",
        "post": "#94A3B8",
        "edge": "#0F172A",
    },
    "dark": {
        "top": ("#64748B", "#475569", "#334155"),
        "east": ("#94A3B8", "#64748B", "#475569"),
        "south": ("#1E293B", "#0F172A", "#020617"),
        "path": "#F59E0B",
        "glow": "#FBBF24",
        "post": "#E2E8F0",
        "edge": "#0F172A",
    },
}


def _mark_inner(kind: str, *, mono: bool = False) -> str:
    geo = _geometry()
    ox, oy = float(geo["ox"]), float(geo["oy"])
    slabs = geo["slabs"]
    pal = PALETTES["dark" if kind == "dark" else "light"]
    parts: list[str] = []
    for index, (top, east, south) in enumerate(slabs):
        if mono:
            south_fill, east_fill, top_fill = "currentColor", "currentColor", "currentColor"
            south_op, east_op, top_op = "0.45", "0.7", "1"
        else:
            south_fill, east_fill, top_fill = pal["south"][index], pal["east"][index], pal["top"][index]
            south_op = east_op = top_op = "1"
        parts.append(
            f'<polygon points="{_poly(south, ox, oy)}" fill="{south_fill}" opacity="{south_op}"/>'
        )
        parts.append(
            f'<polygon points="{_poly(east, ox, oy)}" fill="{east_fill}" opacity="{east_op}"/>'
        )
        parts.append(
            f'<polygon points="{_poly(top, ox, oy)}" fill="{top_fill}" opacity="{top_op}"/>'
        )
    path_d = _path_d(list(geo["path"]), ox, oy)
    if mono:
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="currentColor" stroke-width="2.4" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        for a, b in geo["posts"]:
            parts.append(
                f'<line x1="{ox + a[0]:.2f}" y1="{oy + a[1]:.2f}" '
                f'x2="{ox + b[0]:.2f}" y2="{oy + b[1]:.2f}" stroke="currentColor" '
                'stroke-width="1.15" stroke-linecap="round" stroke-dasharray="0.4 1.7" opacity="0.85"/>'
            )
    else:
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{pal["glow"]}" stroke-width="5.2" '
            'stroke-linecap="round" stroke-linejoin="round" opacity="0.28"/>'
        )
        parts.append(
            f'<path d="{path_d}" fill="none" stroke="{pal["path"]}" stroke-width="2.35" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
        for a, b in geo["posts"]:
            parts.append(
                f'<line x1="{ox + a[0]:.2f}" y1="{oy + a[1]:.2f}" '
                f'x2="{ox + b[0]:.2f}" y2="{oy + b[1]:.2f}" stroke="{pal["post"]}" '
                'stroke-width="1.2" stroke-linecap="round" stroke-dasharray="0.45 1.8"/>'
            )
    return "\n  ".join(parts)


def _svg(view: str, title: str, desc: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" '
        'role="img" aria-labelledby="title desc">\n'
        f'  <title id="title">{title}</title>\n'
        f'  <desc id="desc">{desc}</desc>\n'
        f"  {body}\n"
        "</svg>\n"
    )


def _favicon_body(kind: str, *, mono: bool = False) -> str:
    """Framed two-slab mark — readable at 16px. No dashed posts (they read as noise)."""
    w, d, h, gap = 15.5, 12.0, 4.4, 3.4
    slabs = [_box(0, 0, 0, w, d, h), _box(0, 0, h + gap, w, d, h)]
    z_top = h + gap + h
    path_xy = ((1.8, 2.4), (6.2, 4.0), (8.8, 7.2), (13.2, 9.0))
    path_pts = [iso(x, y, z_top) for x, y in path_xy]
    pts: list[tuple[float, float]] = []
    for top, east, south in slabs:
        pts.extend(top + east + south)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ox = 16.0 - (min(xs) + max(xs)) / 2
    oy = 16.4 - (min(ys) + max(ys)) / 2
    pal = PALETTES["dark" if kind == "dark" else "light"]
    if mono:
        parts = [
            '<rect x="1.4" y="1.4" width="29.2" height="29.2" rx="7" fill="none" '
            'stroke="currentColor" stroke-width="1.8"/>'
        ]
    else:
        field = "#0F172A" if kind == "dark" else "#E2E8F0"
        parts = [
            f'<rect x="1.4" y="1.4" width="29.2" height="29.2" rx="7" fill="{field}" '
            f'stroke="{pal["path"]}" stroke-width="1.6"/>'
        ]
    for index, (top, east, south) in enumerate(slabs):
        if mono:
            parts.append(
                f'<polygon points="{_poly(south, ox, oy)}" fill="currentColor" opacity="0.45"/>'
            )
            parts.append(
                f'<polygon points="{_poly(east, ox, oy)}" fill="currentColor" opacity="0.7"/>'
            )
            parts.append(f'<polygon points="{_poly(top, ox, oy)}" fill="currentColor"/>')
        else:
            parts.append(f'<polygon points="{_poly(south, ox, oy)}" fill="{pal["south"][index]}"/>')
            parts.append(f'<polygon points="{_poly(east, ox, oy)}" fill="{pal["east"][index]}"/>')
            parts.append(f'<polygon points="{_poly(top, ox, oy)}" fill="{pal["top"][index]}"/>')
    path_d = _path_d(path_pts, ox, oy)
    stroke = "currentColor" if mono else pal["path"]
    parts.append(
        f'<path d="{path_d}" fill="none" stroke="{stroke}" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
    )
    return "\n  ".join(parts)


def _write(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")


def main() -> None:
    desc = (
        "Three isometric platform slabs with a golden path on the top layer "
        "and dotted signal lines — the intelligent platform layer."
    )
    light = _mark_inner("light")
    dark = _mark_inner("dark")
    mono = _mark_inner("light", mono=True)

    _write(
        SVG / "repave-mark.svg",
        _svg("0 0 80 80", "Repave mark", desc, light),
    )
    _write(
        SVG / "repave-mark-light.svg",
        _svg("0 0 80 80", "Repave mark", desc, light),
    )
    _write(
        SVG / "repave-mark-dark.svg",
        _svg("0 0 80 80", "Repave mark (dark surfaces)", desc, dark),
    )
    _write(
        SVG / "repave-mark-monochrome.svg",
        _svg("0 0 80 80", "Repave mark (monochrome)", desc, mono),
    )

    fav_light = _favicon_body("light")
    fav_dark = _favicon_body("dark")
    fav_mono = _favicon_body("light", mono=True)
    _write(
        SVG / "repave-mark-favicon.svg",
        _svg("0 0 32 32", "Repave favicon", "Framed two-slab mark for small sizes.", fav_light),
    )
    _write(
        SVG / "repave-mark-favicon-dark.svg",
        _svg(
            "0 0 32 32",
            "Repave favicon (dark)",
            "Framed two-slab mark for dark browser chrome.",
            fav_dark,
        ),
    )
    _write(
        SVG / "repave-mark-favicon-mono.svg",
        _svg("0 0 32 32", "Repave favicon (mono)", "Monochrome framed two-slab mark.", fav_mono),
    )
    _write(
        FAV / "favicon.svg",
        _svg(
            "0 0 32 32",
            "Repave favicon (dark)",
            "Framed two-slab mark for dark browser chrome.",
            fav_dark,
        ),
    )

    mark_nested_light = (
        f'<svg x="0" y="4" width="40" height="40" viewBox="0 0 80 80">\n  {light}\n  </svg>'
    )
    mark_nested_dark = (
        f'<svg x="0" y="4" width="40" height="40" viewBox="0 0 80 80">\n  {dark}\n  </svg>'
    )
    font = "system-ui, -apple-system, 'Segoe UI', sans-serif"

    compact_light = (
        f"{mark_nested_light}\n"
        f'  <text x="48" y="30" font-family="{font}" font-size="22" font-weight="700" '
        'fill="#0F172A" letter-spacing="-0.03em">repave</text>\n'
        f'  <text x="132" y="30" font-family="{font}" font-size="16" font-weight="600" '
        'fill="#F59E0B">v3</text>'
    )
    compact_dark = (
        f"{mark_nested_dark}\n"
        f'  <text x="48" y="30" font-family="{font}" font-size="22" font-weight="700" '
        'fill="#E2E8F0" letter-spacing="-0.03em">repave</text>\n'
        f'  <text x="132" y="30" font-family="{font}" font-size="16" font-weight="600" '
        'fill="#F59E0B">v3</text>'
    )
    _write(
        SVG / "repave-logo-compact.svg",
        _svg("0 0 168 48", "Repave", "Platform-layer mark with repave v3 wordmark (compact).", compact_light),
    )
    _write(
        SVG / "repave-logo-compact-dark.svg",
        _svg(
            "0 0 168 48",
            "Repave",
            "Platform-layer mark with repave v3 wordmark for dark backgrounds (compact).",
            compact_dark,
        ),
    )

    full_light = (
        f'<svg x="0" y="16" width="48" height="48" viewBox="0 0 80 80">\n  {light}\n  </svg>\n'
        f'  <text x="56" y="42" font-family="{font}" font-size="26" font-weight="700" '
        'fill="#0F172A" letter-spacing="-0.03em">repave</text>\n'
        f'  <text x="154" y="42" font-family="{font}" font-size="18" font-weight="600" '
        'fill="#F59E0B">v3</text>\n'
        '  <line x1="56" y1="50" x2="200" y2="50" stroke="#F59E0B" stroke-width="1.5"/>\n'
        f'  <text x="56" y="64" font-family="{font}" font-size="8" font-weight="600" '
        'fill="#64748B" letter-spacing="0.14em">THE INTELLIGENT PLATFORM LAYER</text>'
    )
    full_dark = (
        f'<svg x="0" y="16" width="48" height="48" viewBox="0 0 80 80">\n  {dark}\n  </svg>\n'
        f'  <text x="56" y="42" font-family="{font}" font-size="26" font-weight="700" '
        'fill="#E2E8F0" letter-spacing="-0.03em">repave</text>\n'
        f'  <text x="154" y="42" font-family="{font}" font-size="18" font-weight="600" '
        'fill="#F59E0B">v3</text>\n'
        '  <line x1="56" y1="50" x2="220" y2="50" stroke="#F59E0B" stroke-width="1.5"/>\n'
        f'  <text x="56" y="64" font-family="{font}" font-size="8" font-weight="600" '
        'fill="#94A3B8" letter-spacing="0.14em">THE INTELLIGENT PLATFORM LAYER</text>'
    )
    _write(
        SVG / "repave-logo.svg",
        _svg("0 0 300 80", "Repave", "Platform-layer mark, repave v3 wordmark, and tagline.", full_light),
    )
    _write(
        SVG / "repave-logo-light.svg",
        _svg("0 0 300 80", "Repave", "Platform-layer mark, repave v3 wordmark, and tagline.", full_light),
    )
    _write(
        SVG / "repave-logo-dark.svg",
        _svg(
            "0 0 300 80",
            "Repave (dark surfaces)",
            "Platform-layer mark, repave v3 wordmark, and tagline for dark backgrounds.",
            full_dark,
        ),
    )

    avatar_dark = (
        '<circle cx="64" cy="64" r="64" fill="#0F172A"/>\n'
        f'  <svg x="16" y="16" width="96" height="96" viewBox="0 0 80 80">\n  {dark}\n  </svg>'
    )
    avatar_light = (
        '<circle cx="64" cy="64" r="64" fill="#E2E8F0"/>\n'
        f'  <svg x="16" y="16" width="96" height="96" viewBox="0 0 80 80">\n  {light}\n  </svg>'
    )
    _write(
        SVG / "repave-avatar-dark.svg",
        _svg("0 0 128 128", "Repave avatar (dark)", "Platform-layer mark on a deep navy circle.", avatar_dark),
    )
    _write(
        SVG / "repave-avatar-light.svg",
        _svg("0 0 128 128", "Repave avatar (light)", "Platform-layer mark on a light gray circle.", avatar_light),
    )

    social = (
        '<rect width="1200" height="630" fill="#0F172A"/>\n'
        '  <rect x="0" y="0" width="1200" height="6" fill="#F59E0B"/>\n'
        f'  <svg x="72" y="175" width="220" height="220" viewBox="0 0 80 80">\n  {dark}\n  </svg>\n'
        f'  <text x="320" y="270" font-family="{font}" font-size="92" font-weight="700" '
        'fill="#E2E8F0" letter-spacing="-0.03em">repave</text>\n'
        f'  <text x="680" y="270" font-family="{font}" font-size="64" font-weight="600" '
        'fill="#F59E0B">v3</text>\n'
        '  <line x1="320" y1="300" x2="900" y2="300" stroke="#F59E0B" stroke-width="4"/>\n'
        f'  <text x="320" y="355" font-family="{font}" font-size="26" font-weight="600" '
        'fill="#94A3B8" letter-spacing="0.16em">THE INTELLIGENT PLATFORM LAYER</text>\n'
        f'  <text x="72" y="520" font-family="{font}" font-size="30" font-weight="400" '
        'fill="#CBD5E1">Self-service by design. AI-powered. Governed by design.</text>\n'
        f'  <text x="72" y="565" font-family="{font}" font-size="30" font-weight="400" '
        'fill="#CBD5E1">Golden paths for many, not just the few.</text>'
    )
    _write(
        SVG / "repave-social-card.svg",
        _svg("0 0 1200 630", "Repave social card", "Open Graph card: navy field, platform-layer mark, v3 lockup.", social),
    )
    print("wrote SVG marks")


if __name__ == "__main__":
    main()
