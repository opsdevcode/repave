# Portal visual design and UX

Planning document for the repave web portal (Jinja templates under
`engine/src/repave_engine/templates/`). The [roadmap](roadmap.md) tracks release
labels; this file holds **visual layout**, **component patterns**, and
**acceptance signals** for portal work shipped under the **v1.18 theme**
(engine tags through **v2.30.0**).

**Current UI (shipped):** night-ops console — shared `base.html`, `/static/repave.css`,
`/static/repave.js`, sticky shell with optional environment badge.

| Route | Template | Highlights |
| --- | --- | --- |
| Home | `index.html` | Visual v2 hero, catalog grouped by artifact type, blueprint cards |
| Blueprint form | `blueprint_form.html` | Governance card; Terraform/Ansible stepper where applicable; sticky **Plan preview** + Delivery plan/apply; scope filter, presets, validation |
| Generation result | `result.html` | Status hero, lineage + policy rules, gate table, repo card, file tree + preview, Backstage callout when present |

**Last run:** After generate, the result page stores a summary in **sessionStorage**
and the shell shows a “Last run in this browser” snippet on home and form routes.
Fleet-wide history is available via the JSONL audit sink, portal `/activity`, and hosted
`/runs` when durability SQL is configured (roadmap v1.30 — shipped).

**Deferred (Phase 5+):** white-label accents, standards diff UI, light theme,
Backstage-adjacent density, conversational entry — see
[Phase 5](#phase-5--polish-and-extensions).

**Target:** a coherent product surface without mandating a SPA rewrite — shared
static assets, CSS tokens, and a base layout template.

---

## How this relates to the roadmap

| Roadmap item | Visual / UX home |
| --- | --- |
| v1.18 Portal and UX hardening | **Complete** — Phases 1–4 + visual v2 + scope UX (see [Shipped](roadmap.md#shipped)) |
| v1.18 functional items | Catalog grouping, scope search/presets/validation, gate excerpts, Ansible platform/version dropdowns, **Plan preview** on all forms |
| v1.22 Generation provenance and version visibility | Governance card on the blueprint form (Phase 3) |
| v1.30 Operability and audit | **Shipped** — audit sink, `/activity`, hosted `/runs`; browser last-run remains a local convenience |
| Cost visibility (shipped) | Library cost badges, Cloud spend scorecard, result-page estimates — see [`docs/finops.md`](finops.md) |
| FinOps enablement (v1.90–v1.94) | Tags + estimate policy shipped (v1.90–v1.91); planned: entity sparklines + `/platform/finops` rollup ([roadmap](roadmap.md#finops-enablement-v2x)) |
| Parking lot: standards diff in portal | **Partial:** Update repo preview shows pin table (observed vs catalog); blueprint form shows git standard drift when available (Phase 5 for full side-by-side) |
| v3.0 conversational generation | Second entry point in the same app shell (Phase 5) |

Delivery slices (all landed on `main`):

```text
v1.18-foundation   base layout + tokens + shell + core components
v1.18-catalog      home cards + artifact grouping + gate/standard chips
v1.18-form         governance card + scope visual refresh + functional UX
v1.18-results      gate dashboard + repo card + file preview layout
v1.18-polish       home hero, scope presets, browser last-run snippet
```

---

## Phase 1 — Visual foundation

**Status:** Shipped.

**Goal:** One coherent repave surface across all routes.

### Shared assets and layout

- Add `engine/src/repave_engine/static/repave.css` (and minimal `repave.js` if
  needed for copy buttons or theme toggle).
- Introduce `base.html` with blocks for title, content, and optional scripts;
  extend from `index.html`, `blueprint_form.html`, and `result.html`.
- Wire static files in the FastAPI app (existing pattern or `StaticFiles` mount).

### Design tokens (CSS custom properties)

Default theme is **night-ops** (`color-scheme: dark` on `:root`):

- **Color:** charcoal `--bg` / `--surface`, light `--text`, electric teal
  `--accent`, crisp `--success` / `--warning` / `--error` / `--skip`
- **Atmosphere:** vignette + fine grid overlay (`.shell__atmosphere`); scan
  hairline on the sticky bar
- **Type:** Fraunces (display), Source Sans 3, IBM Plex Mono
- **Layout:** `--radius`, `--space-1` … `--space-6`, `--content-max-width`
- Optional light theme / toggle remains Phase 5 polish if needed

### App shell

- Top bar: wordmark, primary nav (Catalog, Library, …), optional environment badge
  (for example `local` when running under Docker Compose).
- Content area: consistent max width and horizontal padding; mobile single column.
- Breadcrumb or back link styled consistently (not bare `<a>` above `<h1>`).

### Core components (CSS-first)

Reusable classes (names illustrative):

- **Actions:** `.btn`, `.btn--primary`, `.btn--secondary`, `.btn--ghost`
- **Surfaces:** `.card`, `.card__header`, `.card__body`
- **Status:** `.badge`, `.badge--terraform`, `.badge--ansible`, `.alert`
- **Forms:** `.field`, `.label`, `.hint`, `.input`, `.select`, `.checkbox-grid`

**Done when:** All three portal routes share one shell, tokens, and component
vocabulary; `/static/repave.css` is the single source of styling truth.

---

## Phase 2 — Catalog (home)

**Status:** Shipped (including visual v2 home hero).

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

**Status:** Shipped (governance card, split layout for Terraform, publish toggle,
segmented scope mode, scope presets and inline validation, Ansible enum inputs).

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

**Status:** Shipped.

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

**Status:** Partial — home hero, catalog hover, browser last-run snippet, copy
feedback, generate/update busy states, sticky generate bar, skip link, upgrade
diff styling, Terraform stepper, scope/gate motion, audit-backed recent activity,
standards drift diff, staged generate labels, catalog search, resume chip,
**`/activity`** page, standards drift two-pane layout, form draft restore, result
gate filters, and update busy stages shipped. Unused home quick-nav sidebar was
**removed** (sunset). **Platform adoption** (`/platform/adoption`) ships outcome
metrics for golden-path adoption — see [`platform-metrics.md`](platform-metrics.md).
**Portal polish pass (2026-08):** semantic CSS token aliases (estate map, diff
viewer, tables), `badge--warn`, live-plan result hero, entity live-plan preflight +
busy overlay, command palette shell button, relative timestamps, sortable `/runs`
table; `engine/tests/test_portal_css_tokens.py` guards undefined `var()` references.
White-label / compact density and light theme remain optional. **Compact density**
(`portal.density: compact`) ships for Backstage-adjacent layouts; **white-label**
accents move to v2.

Pick based on audience and hosting model (v1.25+).

### Visual v2 (shipped)

- Home hero: oversized **repave** wordmark, one line, CTAs; catalog below fold
- Console-native catalog card hover (respects `prefers-reduced-motion`)
- Form/results use Phase 3–4 markup (governance rail, status hero)

Further craft (illustration, stepper) is optional.

Primary nav shows Catalog / Upgrade / Verify; Fleet, Services, Estate, and Activity live under **More** in the shell.

| Enhancement | Notes |
| --- | --- |
| **Visual v2 follow-ups** | Optional stepper, illustration — not required for v1.18 close-out |
| **Dark mode** | Night-ops is default; light theme / toggle only if needed later |
| **Motion** | Expand/collapse on scope and gate rows; honor `prefers-reduced-motion` |
| **Gate table** | Sticky header, scrollable body, expandable long skip/fail messages; toolchain alert on result |
| **Command palette** | Cmd/Ctrl-K plus shell **Jump to…** button with platform shortcut hint |
| **Async runs index** | Client-side column sort on `/runs`; relative `<time>` labels portal-wide |
| **Live plan surfaces** | Entity preflight panel, busy overlay on submit, result hero with resource counts |
| **Blueprint form** | Collapsible gate list on governance card; step progress text; mobile-first sticky actions |
| **Generation progress** | If generation becomes async, use shell + step list or spinner |
| **Backstage-adjacent density** | Neutral cards suitable beside developer portals (v1.32); do not clone Backstage |
| **White-label** | Deferred to **v2** — optional logo URL and accent override (not v1.18 scope) |
| **Standards diff** | Side-by-side or accordion diff before generate (parking lot); uses Phase 1–2 panels |
| **History / last run** | **Browser session** snippet shipped (`repave.js` + sessionStorage); fleet-wide history needs audit sink (v1.30) |
| **Conversational UI (v2)** | Chat entry in same shell; results reuse Phase 4 dashboard |

---

## Phase 6 — Live governance surfaces

**Status:** Tier 1 shipped (live run console, command palette). Tier 2 items 3–8 are in
[roadmap — Portal live governance surfaces](roadmap.md#portal-live-governance-surfaces).

**Goal:** Make governance visible while it runs — not only on the result page.

| Item | Status |
| --- | --- |
| Live run console (`/runs/{id}`, SSE gate events) | Shipped |
| Command palette (Cmd/Ctrl-K) | Shipped |
| Estate map, diff viewer, annotations, preflight, bundle graph, presenter mode | Shipped |

**Done when:** Users who enable “Live run console” on the blueprint form watch gates complete in
real time; any route exposes Cmd/Ctrl-K navigation without a SPA rewrite.

---

## Copy and voice

Portal strings are **product copy**, not engine documentation.

- **Show:** pinned standard, policy profile, gate names, `repave.yaml` as the
  lineage file, Backstage `catalog-info.yaml` and `repave.dev/*` annotations.
- **Hide:** README section titles (`## Provenance`), “synced on generate”, render
  pipeline steps, the word “receipt”, and other implementation details that belong
  in `docs/` or code comments only.
- **Plan / Apply:** validate-only mode is **Plan** (CTA **Plan preview**); write
  mode is **Apply**. Keep wire fields `dry_run` / `data-dry-run-*` unchanged.

Governance rail **Lineage** row: engine version + `repave.yaml` — same terms as
the result page lineage card. Cursor rule: `.cursor/rules/portal-ux-copy.mdc`.

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
| Static assets | `engine/src/repave_engine/static/repave.css`, `repave.js` |
| Form logic | Inline script in `blueprint_form.html` (provider catalog) |
| API routes | Engine FastAPI app (serves HTML responses) |

When implementing Phase 1, add tests only where behavior changes (for example route
still returns 200, critical form fields present). Visual regression tests are
optional; snapshot HTML only if the team wants guardrails against template drift.

---

## Related docs

- [Roadmap — shipped portal UX](roadmap.md#v118--portal-ux-theme)
- [FinOps enablement](roadmap.md#finops-enablement-v2x) — showback / budgets / FOCUS surfaces ([operator guide](finops.md))
- [Concepts — golden path and governance](concepts.md)
- [Engine README](../engine/README.md) — local portal URL
