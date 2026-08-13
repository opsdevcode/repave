# ADR 009: v3 product identity

**Status:** Accepted — display vs wire split; public display name filled before the first
asset PR.
**Date:** 2026-08-13
**Scope:** v3 public identity (display name, mark, portal/CLI chrome) on `next/v3`.
Does not rename CLI, PyPI, Helm charts, GitHub repos, `repave.yaml`, or CRDs.
**Related:** [ADR 008](008-v3-branching-release-and-testing.md) (branching),
[ADR 007](007-v3-multi-repo-decomposition.md) (extract-repos),
[`docs/brand/README.md`](../brand/README.md) (v2 Converge),
[`docs/brand/v3.md`](../brand/v3.md) (v3 asset track),
[`docs/portal-design.md`](../portal-design.md) (Visual v2 / Visual v3),
[beyond v2.0.0](../roadmap.md#beyond-v200--autonomous-estate-and-lifecycle-control-plane)

## Context

v2 identity is **repave** (product, CLI, packages) plus the **Converge** mark
([`docs/brand/README.md`](../brand/README.md), README “Why repave?”). That pairing shipped
on `main` with white-label overlays (`portal.logo_url` / `portal.accent_color`).

v3 is a year-long major ([ADR 008](008-v3-branching-release-and-testing.md)): control plane,
autonomous remediation, conversational generation. Converge still describes the *engine*
(fragmented inputs → one governed path). It no longer describes the *product* operators
will live in for the next major.

Continuing to recapture v2 README screenshots and polish Converge chrome on `main` would
throw that work away when v3 identity lands. Brand therefore goes **first** on `next/v3`,
before developer lab, extract-repos, or autonomous-estate UI.

White-label stays for tenant overlays. It is not a product identity.

## Decision

**v3 ships a new public identity on `next/v3`. Wire names stay `repave` until a later,
explicit rename (not this ADR).**

v2 `main` keeps Converge until v3 merge-back.

### Surfaces

| Surface | v2 (`main`) | v3 (`next/v3`) |
| --- | --- | --- |
| Public product name + wordmark | repave + Converge | **New display name** (owner fills this cell before the first mark PR) |
| Mark / lockups / social / favicon | Converge set under `docs/brand/assets/` | New v3 set; process in [`docs/brand/v3.md`](../brand/v3.md) |
| Portal + CLI chrome | Converge tokens, scarce amber | New tokens on `next/v3`; semantic green / orange / rose unchanged |
| CLI binary, PyPI, Helm chart, GitHub repo | `repave` | **Keep `repave`** so ADR 007 extract and CI do not move with the mark |
| `repave.yaml`, `repave.dev/*` annotations, CRDs | contracts | **Keep** — contracts, not brand |
| White-label `portal.logo_url` / `accent_color` | Converge defaults | Still valid; defaults become the v3 identity on `next/v3` |

A CLI/package rename in the same major is a **second** decision (breaking: `cli/`, charts,
`versions.lock`). Do not bury it in an asset or CSS PR.

### Branching

Identity work is `feat/v3-*` → `next/v3` ([ADR 008](008-v3-branching-release-and-testing.md)).
Nothing identity-related merges to `main` except the final v3 merge-back.

Asset PRs start only after the display-name cell above has a string.

## Why not the alternatives

**Keep evolving Converge on `main` and recapture screenshots each time.** v2 polish
(library drawers, fleet tiles, platform console, motion) is enough for the 2.x line.
Further screenshot churn is discarded at v3 identity.

**Rebrand only via white-label config.** White-label is a tenant overlay. Product identity
is the default chrome, README lockup, and social card.

**Rename GitHub / PyPI / CLI in the same commit as the mark.** Unreviewable; fights
[ADR 007](007-v3-multi-repo-decomposition.md). Wire names stay `repave` in this ADR.

**Promote Converge from mark to product name.** Rejected as the default: v3 is a new
public identity, not a promotion of the v2 mark. If product later chooses “Converge” as
the display string, write it into the table — that is still a display-name fill, not a
wire rename.

## Consequences

- `docs/brand/` is dual-track: Converge remains canonical on `main` until merge-back;
  [`docs/brand/v3.md`](../brand/v3.md) is source of truth for v3 assets on `next/v3`.
- Portal-design **Visual v2** stays shipped history. **Visual v3** points here.
- No v2 screenshot refresh for current chrome.
- Developer lab, extract-repos, and autonomous-estate UI wait until v3 identity is the
  default on `next/v3`, so those surfaces are not born in a brand that will be replaced.
- An uncommitted local draft that numbered fine-grained authorization as “ADR 009” must
  land as **ADR 010** (or later). This file owns 009.

## Follow-up PRs (same `next/v3` line)

1. Fill the display-name cell in this ADR if it is still empty.
2. SVG source under `docs/brand/assets/svg/`, regenerate PNG / favicon / social, copy into
   `engine/src/repave_engine/static/brand/` — do not crop concept-board rasters.
3. Night-ops tokens in `repave.css`: new accent; family drawer colors stay independent of
   brand gold/amber; status colors stay semantic.
4. README “Why repave?” / lockup on `next/v3` only; portal copy stays builder-facing.
5. Recapture README portal screenshots **once** against the v3 shell.
