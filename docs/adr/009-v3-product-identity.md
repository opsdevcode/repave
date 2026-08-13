# ADR 009: v3 product identity

**Status:** Accepted — display name **repave**; new platform-layer mark and tagline
on `next/v3`. Wire names stay `repave`.
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

v3 is the **primary product line**. The owner filled the identity from the v3 brand
board: keep the **repave** name, replace Converge with the isometric platform-layer
mark, and use the tagline **The intelligent platform layer**.

White-label stays for tenant overlays. It is not a product identity.

## Decision

**v3 ships a new public identity on `next/v3`. The display name stays `repave`. Wire
names stay `repave` until a later, explicit rename (not this ADR).**

v2 `main` keeps Converge until v3 merge-back. `next/v3` is the integration line for
new product work and is versioned as `3.0.0-rc.N`.

### Surfaces

| Surface | v2 (`main`) | v3 (`next/v3`) |
| --- | --- | --- |
| Public product name + wordmark | repave + Converge | **repave** + amber **v3**; tagline *The intelligent platform layer* |
| Mark / lockups / social / favicon | Converge set | Isometric platform slabs + golden path; process in [`docs/brand/v3.md`](../brand/v3.md) |
| Portal + CLI chrome | Converge tokens, scarce amber | Same five-color palette; platform-layer mark; amber stays scarce |
| CLI binary, PyPI, Helm chart, GitHub repo | `repave` | **Keep `repave`** so ADR 007 extract and CI do not move with the mark |
| `repave.yaml`, `repave.dev/*` annotations, CRDs | contracts | **Keep** — contracts, not brand |
| White-label `portal.logo_url` / `accent_color` | Converge defaults | Still valid; empty defaults are the v3 mark + `#F59E0B` |

### Palette (v3)

| Token | Hex | Role |
| --- | --- | --- |
| Deep Navy | `#0F172A` | Primary background / foundation |
| Slate | `#64748B` | Secondary surfaces / text |
| Cool Gray | `#94A3B8` | Secondary UI |
| Light Gray | `#E2E8F0` | Light surfaces / text |
| Amber / Gold | `#F59E0B` | Repave / golden path / primary action |

Semantic status stays distinct from brand amber (success green, warning **orange**,
error rose, info blue). Do not use `#F59E0B` for warning/error even if a board
swatch reused it.

A CLI/package rename in the same major is a **second** decision (breaking: `cli/`, charts,
`versions.lock`). Do not bury it in an asset or CSS PR.

### Branching

Identity policy and other v3 features are `feat/v3-*` → `next/v3`
([ADR 008](008-v3-branching-release-and-testing.md)). Nothing identity-related merges to
`main` except the final v3 merge-back (breaking removals).

**GitHub default branch is `next/v3`.** That is how clones, Compare, and new PRs
work. `main` remains the v2.x **Release** line (`release.yml`, PyPI 2.x tags).
The main-branch ruleset targets `refs/heads/main` explicitly so moving the GitHub
default does not unprotect Release. Do not retarget `release.yml` to `next/v3`.

Marks land on this line. Foundation, developer lab, and extract-repos proceed with
the v3 shell. Recapture README screenshots once against that shell.

## Why not the alternatives

**Keep evolving Converge on `main` and recapture screenshots each time.** v2 polish
(library drawers, fleet tiles, platform console, motion) is enough for the 2.x line.
Further screenshot churn is discarded at v3 identity.

**Block all v3 work until the display name exists.** Rejected: the name is one surface.
The major already has a year of control-plane and decomposition work that should not
sit idle.

**Rebrand only via white-label config.** White-label is a tenant overlay. Product identity
is the default chrome, README lockup, and social card.

**Rename GitHub / PyPI / CLI in the same commit as the mark.** Unreviewable; fights
[ADR 007](007-v3-multi-repo-decomposition.md). Wire names stay `repave` in this ADR.

**Promote Converge from mark to product name.** Rejected. The display name stays
**repave**; Converge does not become the product. The v2 mark is replaced, not renamed.

**Change the GitHub default branch to `next/v3`.** Accepted (reversed the same day
as the first revision). Default branch is how the repo actually works. Dual-line
Release still needs `main` as a named protected ref, not as GitHub's default.
The ruleset file pins `refs/heads/main` so `~DEFAULT_BRANCH` does not follow the
move.

**Keep GitHub default branch on `main` while calling v3 the primary product line.**
Rejected. That split made "primary" a docs convention instead of clone/PR reality.

## Consequences

- `docs/brand/` is dual-track: Converge remains canonical on `main` until merge-back.
  On `next/v3`, [`docs/brand/README.md`](../brand/README.md) and
  [`docs/brand/v3.md`](../brand/v3.md) describe the platform-layer set.
- Portal-design **Visual v2** stays shipped history. **Visual v3** points here.
- No v2 screenshot refresh. Recapture README portal screenshots once against the v3
  shell.
- Developer lab, extract-repos, and autonomous-estate UI proceed on `next/v3` in the
  v3 shell.
- An uncommitted local draft that numbered fine-grained authorization as “ADR 009” must
  land as **ADR 010** (or later). This file owns 009.

## Follow-up PRs (same `next/v3` line)

1. Recapture README portal screenshots **once** against the v3 shell.
2. Dispatch **Release prerelease (next/v3)** after this ADR merges so the first tag is
   `v3.0.0-rc.1` (opening commit is `feat!:` for that bump).
3. Apply the GitHub org avatar from `docs/brand/assets/social/github-avatar.png`
   (manual; org-admin).
