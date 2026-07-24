# Portal visual design and UX

Planning document for the repave web portal (Jinja templates under
`engine/src/repave_engine/templates/`). The [roadmap](roadmap.md) tracks release
labels; this file holds **visual layout**, **component patterns**, and
**acceptance signals** for portal work, primarily **v1.18**.

**Current UI:** three server-rendered pages with inline CSS — functional wireframe
aesthetic (`system-ui`, gray panels, minimal hierarchy). No shared design system or
artifact-type visual language.

**Target:** a coherent product surface without mandating a SPA rewrite — shared
static assets, CSS tokens, and a base layout template.

---

## How this relates to the roadmap

| Roadmap item | Visual / UX home |
| --- | --- |
| v1.18 Portal and UX hardening | Phases 1–4 below (foundation through results) |
| v1.18 functional items (search, presets, gate excerpts, grouping) | Implemented inside the same layouts and components |
| v1.22 Generation provenance and version visibility | Governance card on the blueprint form (Phase 3) |
| Parking lot: standards diff in portal | Phase 5 — needs cards and side panels from Phase 1–2 |
| v2.0 conversational generation | Second entry point in the same app shell (Phase 5) |

Suggested delivery slices on **v1.18** (separate PRs if helpful):

```text
v1.18-foundation   base layout + tokens + shell + core components
v1.18-catalog      home cards + artifact grouping + gate/standard chips
v1.18-form         governance card + scope visual refresh + functional UX
v1.18-results      gate dashboard + repo card + file preview layout
```

---

## Current state

| Page | Template | Visual state |
| --- | --- | --- |
| Home | `index.html` | Plain list of blueprint links in one card |
| Blueprint form | `blueprint_form.html` | Long vertical form; scope in nested gray boxes; no steps |
| Generation result | `result.html` | Colored text for gates; files in `<details>`; no run summary |

Implementation notes:

- Styles are duplicated per page; change accent or spacing in three places today.
- Terraform provider scope UI is dense but unguided; Ansible forms are short.
- Result page is diagnosable for experts, not scannable for occasional users.

---

## Phase 1 — Visual foundation

**Goal:** One coherent repave surface across all routes.

### Shared assets and layout

- Add `engine/src/repave_engine/static/repave.css` (and minimal `repave.js` if
  needed for copy buttons or theme toggle).
- Introduce `base.html` with blocks for title, content, and optional scripts;
  extend from `index.html`, `blueprint_form.html`, and `result.html`.
- Wire static files in the FastAPI app (existing pattern or `StaticFiles` mount).

### Design tokens (CSS custom properties)

Define at `:root` (and `[data-theme="dark"]` if dark mode ships in Phase 5):

- **Color:** `--bg`, `--surface`, `--border`, `--text`, `--text-muted`, `--accent`,
  `--success`, `--warning`, `--error`, `--skip`
- **Layout:** `--radius`, `--space-1` … `--space-6`, `--content-max-width`
- **Type:** `--font-sans`, `--font-mono` (system stack acceptable initially)

### App shell

- Top bar: wordmark, primary nav (“Golden paths”), optional environment badge
  (for example `local` when running under Docker Compose).
- Content area: consistent max width and horizontal padding; mobile single column.
- Breadcrumb or back link styled consistently (not bare `<a>` above `<h1>`).

### Core components (CSS-first)

Reusable classes (names illustrative):

- **Actions:** `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--ghost`
- **Surfaces:** `.card`, `.card__header`, `.card__body`
- **Status:** `.badge`, `.badge--terraform`, `.badge--ansible`, `.alert`
- **Forms:** `.field`, `.label`, `.hint`, `.input`, `.select`, `.checkbox-grid`

**Done when:** All three pages share one stylesheet and shell; accent and radius
change in a single file.

---

## Phase 2 — Catalog (home)

**Goal:** Golden paths read as a **catalog**, not a README list.

### Grouping

- Group blueprints by **artifact type** (Terraform, Ansible; later Helm, app
  service, observability) — aligns with roadmap v1.18.
- Section title + one-line subtitle per group.

### Blueprint cards

Replace the flat `<ul>` with a responsive card grid. Each card includes:

- Blueprint name + **version badge**
- Description (one line, truncated with ellipsis if needed)
- **Chip row:** key gates or gate count (for example `checkov`, `ansible-lint`)
- Footer: pinned standard path and version (muted)
- **Artifact accent:** color stripe or icon treatment per `artifactType` (palette
  only — avoid heavy illustration)

### Empty state

Styled empty state when no blueprints are loaded (message + hint path
`blueprints/`).

**Done when:** A screenshot of home communicates artifact types without reading
repo docs.

---

## Phase 3 — Blueprint form

**Goal:** Long Terraform flows feel guided; Ansible flows stay simple but polished.

### Governance card (feeds v1.22)

Promote the gray meta block into a **governance card**:

- Standard source and version
- Policy packs (Checkov, ansible-lint) when pinned on the blueprint
- Gates as **badges**, not a comma-separated string
- Optional: generation timestamp placeholder for “last run” when history lands

### Layout patterns

- **Wide viewports:** two columns — sticky governance summary left, inputs right;
  **or** a **stepper** for Terraform-only long paths:
  1. Identity (module/role name, provider, namespace)
  2. Cloud and services
  3. Per-service scope
  4. Publish options
- **Ansible role blueprint:** single column; no forced stepper.

### Provider catalog and scope (visual + v1.18 functional)

- Filter field with **selected count** and clearer selected vs unselected styling.
- **Preset chips** when presets are implemented (roadmap: common service bundles).
- Scope **segmented control** for scope mode radios (basic / basic+additional /
  custom-only).
- Scope cards: service header, dividers between resource sections, consistent
  checkbox grid from Phase 1.

### Publish and submit

- Dry-run vs publish as an explicit **toggle** or segmented control (not a lone
  checkbox below the fold).
- Primary **Generate** CTA — full width or sticky footer on long forms.

**Done when:** Pins and gates are scannable; Terraform scope panels are visually
distinct per service; Ansible form matches the same tokens without extra steps.

---

## Phase 4 — Generation result

**Goal:** Run output reads as a **summary dashboard**, not a log wall.

### Status hero

- Large pass / fail / partial summary (counts of passed, failed, skipped gates).
- Blueprint name and version; banner for dry-run vs published.

### Gates

- Table or timeline: Gate | Status | Message | (Duration when available from
  engine).
- Failed rows expand to **stderr excerpt** (roadmap v1.18) in a monospace panel
  with **copy** control.
- Use token colors for PASS / FAIL / SKIP consistently with badges.

### Repository block

When publish succeeds, a card with:

- Repository name
- GitHub (or remote) link as primary button
- Local path with copy affordance

### Generated files

- Prefer **tree + preview** on wide screens: path list left, content right.
- Narrow screens: styled `<details>` with code panel (optional syntax highlighting
  later — Prism or highlight.js).
- Truncation called out with badge, not inline prose only.

### Publish plan

- Collapsible “PR description preview” using monospace or preformatted block;
  future: light markdown rendering.

**Done when:** One glance shows overall outcome; a failed gate surfaces excerpt in
at most two interactions.

---

## Phase 5 — Polish and extensions

Pick based on audience and hosting model (v1.25+).

| Enhancement | Notes |
| --- | --- |
| **Dark mode** | `prefers-color-scheme` default + shell toggle; tokens make this cheap |
| **Motion** | Expand/collapse on scope and gate rows; honor `prefers-reduced-motion` |
| **Generation progress** | If generation becomes async, use shell + step list or spinner |
| **Backstage-adjacent density** | Neutral cards suitable beside developer portals (v1.32); do not clone Backstage |
| **White-label** | Optional logo URL and accent override via `repave.config.yaml` |
| **Standards diff** | Side-by-side or accordion diff before generate (parking lot); uses Phase 1–2 panels |
| **History / last run** | Roadmap v1.18 — sidebar or footer on form and home from server-side session or audit sink (v1.30) |
| **Conversational UI (v2)** | Chat entry in same shell; results reuse Phase 4 dashboard |

---

## Non-goals (early)

- Full React/Vite portal unless multi-user real-time or heavy client state requires it.
- Custom theme per blueprint — use **artifact-type** accents only.
- Brand illustration pass before tokens and catalog cards — foundation first.

---

## Acceptance signals (visual)

1. **Home:** Grouped blueprint cards; artifact type obvious at a glance.
2. **Form:** Standard, policy packs, and gates readable without parsing raw field
   names; Terraform scope scannable per service.
3. **Result:** Overall pass/fail obvious; failed gate shows stderr excerpt quickly.
4. **Consistency:** Same nav, spacing, and colors on all routes; usable on mobile
   (single column, touch-friendly targets).
5. **Accessibility:** Focus states on controls; labels associated with inputs;
   `aria-live` retained for dynamic scope panels.

---

## Implementation pointers

| Area | Location today |
| --- | --- |
| Templates | `engine/src/repave_engine/templates/` |
| Form logic | Inline script in `blueprint_form.html` (provider catalog) |
| API routes | Engine FastAPI app (serves HTML responses) |

When implementing Phase 1, add tests only where behavior changes (for example route
still returns 200, critical form fields present). Visual regression tests are
optional; snapshot HTML only if the team wants guardrails against template drift.

---

## Related docs

- [Roadmap — v1.18](roadmap.md#v118--portal-and-ux-hardening)
- [Concepts — golden path and governance](concepts.md)
- [Engine README](../engine/README.md) — local portal URL
