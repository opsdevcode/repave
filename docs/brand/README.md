# Repave brand

Repave turns fragmented platform approaches into governed, repeatable golden paths.

The primary identity is **Converge**: fragmented inputs → standardized paths →
convergence → one governed forward path. Gold (`#F59E0B`) marks the golden path
and must stay scarce — it is brand, not a general status color.

Concept board: [reference/repave-brand-direction.png](reference/repave-brand-direction.png)

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

- `repave-mark.svg` — Converge on light surfaces (navy artwork)
- `repave-mark-dark.svg` — Converge on dark surfaces (light artwork)
- `repave-mark-light.svg` — alias of the light-surface mark
- `repave-mark-monochrome.svg` — `currentColor` for flexible reuse
- `repave-mark-favicon*.svg` — intentionally simplified for 16–32px

### Wordmark lockups

- `repave-logo.svg` / `repave-logo-light.svg` / `repave-logo-dark.svg` — mark +
  **repave** + amber rule + `FROM FRAGMENTED TO GOVERNED`
- `repave-logo-compact.svg` / `repave-logo-compact-dark.svg` — mark + wordmark only
  (product shell, README header)

### Secondary mark

- `repave-secondary-mark.svg` — Converge/Ascend hybrid (notched arrow)

Use only when a secondary lockup is needed. Do not compete with the primary mark
in the same view.

### Avatars

- `repave-avatar-light.svg` / `.png` — light circular field
- `repave-avatar-dark.svg` / `.png` — deep navy circular field (preferred GitHub avatar)

## Palette

| Token idea | Hex | Role |
| --- | --- | --- |
| Deep Navy | `#0F172A` | Dark surfaces, dark mark elements |
| Slate | `#64748B` | Secondary structure |
| Cool Gray | `#94A3B8` | Paths, muted text |
| Light Gray | `#E2E8F0` | Light mark elements, primary text on dark |
| Amber / Gold | `#F59E0B` | Golden path, brand CTAs, scarce accents |

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

- Product UI: existing portal stacks (Source Sans 3, IBM Plex Mono; Fraunces may
  remain for limited display moments).
- Brand wordmark: clean modern sans (system / open-source stacks — no new paid fonts).
- Supporting line: small caps / tracked uppercase; omit below ~120px wide lockups.

## Logo spacing and minimum size

- Clear space around the mark ≈ height of the arrowhead on all sides.
- Minimum mark width: **96px** digital for the full Converge mark; **24px** for the
  simplified favicon mark.
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

At 16px the mark is **simplified** (three fragments, three strokes, arrow). Do not
force the full-detail mark into a favicon.

## Product UI accent rules

Night-ops console stays dark and calm. Brand evolves the shell; it does not rewrite
layout or IA.

- Primary actions (Create / Generate / Apply golden path / New…): brand amber with
  dark foreground for contrast.
- Active nav: thin amber indicator or muted amber wash — not a full amber bar.
- Links in body copy: cool/neutral link tokens, not blanket amber.
- Atmosphere/glow: keep low; prefer hierarchy over decoration.
- Artifact-family badge colors stay independent of brand amber.

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
- Putting `FROM FRAGMENTED TO GOVERNED` in the product sidebar
- Glow-heavy / glassmorphic marketing chrome inside the operations console

## Messaging

Preferred product line (marketing / README / brand surfaces):

> Governed, repeatable platform engineering — golden paths for many, not just the few.

Supporting line for lockups:

> FROM FRAGMENTED TO GOVERNED

Canonical product naming thesis remains in the root [README](../../README.md)
(`## Why "repave"?`) and [concepts](../concepts.md) — do not replace that thesis
with marketing-only copy.
