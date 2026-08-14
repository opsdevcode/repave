# Repave brand

v3 identity on `main` ([ADR 009](../adr/009-v3-product-identity.md)): **repave**
wordmark, isometric **platform-layer** mark, tagline *The intelligent platform layer*.
Wire names stay `repave`.

Repave is the intelligent platform layer: self-service by design, AI-powered,
governed by design. Gold (`#F59E0B`) marks the golden path and must stay scarce —
it is brand, not a general status color.

Concept board: [reference/repave-v3-brand-direction.png](reference/repave-v3-brand-direction.png)
(v2 Converge board: [reference/repave-brand-direction.png](reference/repave-brand-direction.png)).

## Canonical assets

| Role | Path |
| --- | --- |
| **Canonical SVG source** | [`assets/svg/`](assets/svg/) |
| Raster exports | [`assets/png/`](assets/png/) |
| Favicons | [`assets/favicon/`](assets/favicon/) |
| Social / avatars | [`assets/social/`](assets/social/) |
| Portal runtime copies | [`../../engine/src/repave_engine/static/brand/`](../../engine/src/repave_engine/static/brand/) |

Edit SVGs under `assets/svg/` first, then regenerate PNG/favicon exports and refresh
the portal `static/brand/` copies. Do not embed the concept-board raster into SVG.

### Primary mark

- `repave-mark.svg` — platform-layer mark on light surfaces (navy slabs)
- `repave-mark-dark.svg` — platform-layer mark on dark surfaces (slate slabs)
- `repave-mark-light.svg` — alias of the light-surface mark
- `repave-mark-monochrome.svg` — `currentColor` for flexible reuse
- `repave-mark-favicon*.svg` — two-slab simplification for 16–32px

### Wordmark lockups

- `repave-logo.svg` / `repave-logo-light.svg` / `repave-logo-dark.svg` — mark +
  **repave** + amber **v3** + amber rule + `THE INTELLIGENT PLATFORM LAYER`
- `repave-logo-compact.svg` / `repave-logo-compact-dark.svg` — mark + **repave** +
  **v3** (editable source). GitHub and many markdown previews sanitize SVG
  `<text>`, so the wordmark can render as garbage. The root README uses the
  raster lockups (`assets/png/repave-logo-compact.png` and `-dark.png`) via
  `<picture>` so dark mode still swaps correctly.

### Secondary mark

- `repave-secondary-mark.svg` — v2 Converge/Ascend hybrid. Do not use on v3 chrome.

### Avatars

- `repave-avatar-light.svg` / `.png` — light circular field
- `repave-avatar-dark.svg` / `.png` — deep navy circular field (preferred GitHub avatar)

## Palette

| Token idea | Hex | Role |
| --- | --- | --- |
| Deep Navy | `#0F172A` | Primary background / foundation |
| Slate | `#64748B` | Secondary surfaces / text |
| Cool Gray | `#94A3B8` | Secondary UI |
| Light Gray | `#E2E8F0` | Light surfaces / text |
| Amber / Gold | `#F59E0B` | Repave / golden path / primary action |

Also keep semantic UI colors distinct:

| Role | Guidance |
| --- | --- |
| Success | Green — healthy, pass, created |
| Warning | Orange — caution (not brand gold) |
| Error | Rose/red — fail, blocked |
| Info | Cool/neutral — informational chrome |

### Semantic vs brand

- **Brand amber** = identity, golden-path emphasis, primary branded actions,
  active nav accent.
- **Do not** use amber for success, warning, error, or every interactive state.
- Status meaning must remain readable without color alone (labels, icons, badges).

## Typography

- Product UI: **Inter** (UI + wordmark) and IBM Plex Mono (CLI / code).
- Brand wordmark: Inter; no new paid fonts.
- Supporting line: small caps / tracked uppercase; omit below ~120px wide lockups.

## Logo spacing and minimum size

- Clear space around the mark ≈ the height of one slab on all sides.
- Minimum mark size: **32px** digital for the full platform-layer mark; **16px**
  for the simplified favicon mark.
- Prefer the compact lockup (no tagline) under ~280px wide.
- Never stretch, outline, recolor the golden path to green/red, or place the mark
  on busy photography without a solid scrim.

## Light / dark / mono

| Surface | Use |
| --- | --- |
| Light UI, docs on white | `repave-mark.svg`, `repave-logo-light.svg` |
| Night-ops portal, dark docs header | `repave-mark-dark.svg`, `repave-logo-dark.svg` |
| Single-color print / engraving | `repave-mark-monochrome.svg` |

## Favicons

Portal serves dark-friendly favicons from `/static/brand/`:

- `favicon.svg`
- `favicon-16x16.png`, `favicon-32x32.png`
- `apple-touch-icon.png`

At 16px the mark is **simplified** (two slabs, golden path, three signal lines). Do
not force the full-detail mark into a favicon.

## Social and GitHub avatar

Canonical files:

| Asset | Path |
| --- | --- |
| Dark GitHub avatar (preferred) | [`assets/social/github-avatar.png`](assets/social/github-avatar.png) |
| Light GitHub avatar | [`assets/social/github-avatar-light.png`](assets/social/github-avatar-light.png) |
| Open Graph / social card | [`assets/social/repave-social-card.png`](assets/social/repave-social-card.png) |

Portal also serves copies at `/static/brand/social/` for Open Graph meta tags on every
page (`og:image`, `twitter:card`).

### Apply the GitHub organization avatar

1. Open the org **Settings → Profile**.
2. Upload `docs/brand/assets/social/github-avatar.png` (dark navy circle + platform-layer mark).
3. Optionally set the social preview / website image to `repave-social-card.png`.

This cannot be automated from the monorepo without org-admin credentials; keep the
files in `docs/brand/assets/social/` as the source of truth.

## Portal white-label

Optional overrides in `repave.config.yaml` (empty = v3 platform-layer defaults):

```yaml
portal:
  logo_url: "/static/brand/custom-mark.svg"   # or https://cdn.example.com/mark.svg
  accent_color: "#F59E0B"                     # #RGB or #RRGGBB
```

Env overrides: `REPAVE_PORTAL_LOGO_URL`, `REPAVE_PORTAL_ACCENT_COLOR`.

Helm: `repave.portal.logoUrl`, `repave.portal.accentColor`.

Rules:

- `logo_url` must be `http(s)://…` or a root-relative path (`/…`). `javascript:` / `data:` rejected.
- Accent overrides brand CTAs/nav emphasis only — do not treat it as success/warning/error.
- Prefer scarce accents; semantic status colors stay green / orange / rose.

## Product UI accent rules

Night-ops console stays dark and calm. Brand evolves the shell; it does not rewrite
layout or IA.

- Primary actions (Create / Generate / Apply golden path / New…): brand amber with
  dark foreground for contrast.
- Active nav: thin amber indicator or muted amber wash — not a full amber bar.
- Links in body copy: cool/neutral link tokens, not blanket amber.
- Atmosphere/glow: keep low; prefer hierarchy over decoration.
- Artifact-family badge colors stay independent of brand amber (observability uses
  teal, not gold).

## CLI guidance

- Keep output script-friendly; never require color to understand status.
- Honor `NO_COLOR` / non-TTY (no ANSI when disabled).
- Amber may highlight Repave headings or `--golden-path` style emphasis only.
- Success/fail remain semantic (green/red) or plain text labels (`PASS` / `FAIL`).
- No ASCII-art banners.

## Incorrect usage

- Replacing every teal/accent with amber indiscriminately
- Using amber for “Healthy” / success badges
- Cropping pieces out of the concept-board PNG as production art
- Adding construction, cloud, gear, or Kubernetes-like marks
- Putting `THE INTELLIGENT PLATFORM LAYER` in the product sidebar
- Glow-heavy / glassmorphic marketing chrome inside the operations console

## Messaging

Preferred product line (marketing / README / brand surfaces):

> The intelligent platform layer — golden paths for many, not just the few.

Supporting line for lockups:

> THE INTELLIGENT PLATFORM LAYER

Canonical product naming thesis remains in the root [README](../../README.md)
(`## Why "repave"?`) and [concepts](../concepts.md) — do not replace that thesis
with marketing-only copy.
