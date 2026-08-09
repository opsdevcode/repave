# Developing on the v3 line

Working guide for the `next/v3` branch. The decision and its rationale live in
[ADR 006](adr/006-v3-branching-release-and-testing.md); this page is the day-to-day
mechanics. Scope for v3 stays governed by
[beyond v2.0.0](roadmap.md#beyond-v200--autonomous-estate-and-lifecycle-control-plane).

**Status:** `next/v3` cut from `main` at v2.47.0. Enablement (PSR prerelease group,
prerelease workflow, ruleset, chart-publish guard) is not landed yet — see
[Enablement checklist](#enablement-checklist).

## Where work goes

| Change | Branch | Result |
| --- | --- | --- |
| v2.x feature or fix | `feat/*` → `main` | v2.x minor or patch, as today |
| Fix needed on both lines | `feat/*` → `main` first | Reaches `next/v3` on the next sync |
| v3 feature | `feat/v3-*` → `next/v3` | `3.0.0-rc.N` prerelease |
| Breaking removal | `feat/v3-*` → `next/v3`, held to the end | Part of the merge-back |

Nothing is cherry-picked from `next/v3` back to `main`. If something on the v3 branch turns
out to be needed sooner, move it to `main` as a normal v2.x change and let the sync
deduplicate it — that is the roadmap's existing promotion rule, applied to branches.

## Keeping the branch current

```bash
git checkout next/v3
git fetch origin
git merge origin/main      # merge, never rebase — next/v3 is published
```

Run weekly and before cutting any rc. Rebase is still correct inside a short-lived
`feat/v3-*` branch before it merges into `next/v3`.

Two skipped syncs in a row is the trigger to revisit
[ADR 006](adr/006-v3-branching-release-and-testing.md) rather than to keep drifting.

## Flag discipline

Every v3 behavior ships **default-off behind config** so `next/v3` stays in a state that
could be released as a v2.x minor at any point. Deletions and default changes are held as a
small separate commit set at the end.

This is not ceremony. It is what makes the merge-back PR reviewable, and it is the fallback
path: default-off features can be replayed onto `main` individually if the long-lived branch
is ever abandoned.

## Testing

The full v2 suite is the floor. No required check is relaxed on `next/v3`, and coverage
thresholds stay at 75 (engine) and 80 (cli).

```bash
make format && make quality && make test    # same loop as main
make test-v3                                # post-flip behavior (v3 marker)
```

The `v3` pytest marker carries behavior that is only valid **after** the breaking flip.
`make test` asserts the v2 contract still holds; `make test-v3` asserts the v3 shape. Both
pass on `next/v3` for as long as both contracts are served, which is what makes the eventual
removal commit a small, legible diff.

The four v3-specific test obligations — dual-line contracts, autonomy safety, frozen-clock
waiver expiry, and migration round-trips — are specified in
[ADR 006 § Testing strategy](adr/006-v3-branching-release-and-testing.md#testing-strategy).

## Releases

Conventional commits on `next/v3` produce `3.0.0-rc.N` via a dedicated prerelease workflow.
`release.yml` is not modified — it stays the v2 path (see
[`.cursor/rules/repave-release.mdc`](../.cursor/rules/repave-release.mdc)).

rc tags publish container images (safe: `latest` is not applied to prereleases) and must
**not** dispatch a deploy to `opsdevcode/repave-aws-infra`.

## Enablement checklist

Ordered. Each is a small PR onto `next/v3` unless noted.

1. **PSR prerelease group** — add `[tool.semantic_release.branches.main]` and
   `[tool.semantic_release.branches.v3]` to [`engine/pyproject.toml`](../engine/pyproject.toml).
   Adding the explicit `main` group is required: defining any branch group replaces the PSR
   default, so omitting it would break v2 releases.
2. **`release-prerelease.yml`** — new workflow, `push: branches: [next/v3]`, mirroring
   `release.yml` minus the doc/chart version sync and the infra dispatch. Keeps the
   `psr()` / `env -u GITHUB_OUTPUT` helper.
3. **`chart-publish.yml` guard** — skip prerelease tags instead of failing; never dispatch
   `repave-release` for a tag containing `-`.
4. **Push triggers** — add `next/v3` to `branches: [main]` on `ci.yml`,
   `python-quality-security.yml`, `operator.yml`, `chart.yml`, and the `operator-e2e.yml`
   nightly. PR triggers need no change (they are unfiltered).
5. **Ruleset** — `.github/rulesets/next-v3-branch.json` targeting `refs/heads/next/v3` with
   the same ten required checks; teach `sync-ruleset.yml` to PUT both files.
6. **`make test-v3`** and the `v3` pytest marker in
   [`engine/pyproject.toml`](../engine/pyproject.toml).

Only after 1–6 does the branch enforce what this document claims.

## Foundation slice (first implementation)

The first v3 work is deliberately not a feature. It is the metadata and enforcement
primitives that autonomous remediation, mandatory policy, and the breaking removals all
depend on — built default-off so nothing changes for v2 users.

**Risk classes.** Blueprints declare a risk class per change type
(`mechanical` | `standard` | `sensitive`); absent means `standard`. A pure
`classify_change(...) -> RiskClass` function with a frozen result and no I/O, consumed at
this stage only by tests and a read-only portal badge. Auto-merge reads it later; shipping
the classification first means the trust argument is testable before anything acts on it.

**Waivers as data with enforced expiry.** A `load_waivers()` loader and a frozen
`WaiverStatus` (`active` / `expiring` / `expired` / `missing`) with an injected clock.
Expired waivers fail the gate rather than warn. This is the piece that makes mandatory
policy tolerable, so it lands before the mandatory tier, not after.

**A single deprecation registry.** One `deprecations.py` listing every v3 removal with its
sunset date and migration doc link, wired to the existing `Sunset` / `Deprecation` response
headers. Today those dates are written by hand in
[`docs/api-v1-migration.md`](api-v1-migration.md) and in the router; a registry makes the
[breaking-change list](roadmap.md#breaking-at-v300) checkable from code instead of
maintained by memory across a year.

**Done when:** risk class and waiver expiry are expressible, loaded, and unit-tested with
frozen time; the deprecation registry is the only source of sunset dates; every piece is
default-off; `make test` and `make test-v3` both pass on `next/v3`.

## Related

- [ADR 006](adr/006-v3-branching-release-and-testing.md) — the decision and alternatives
- [Roadmap — beyond v2.0.0](roadmap.md#beyond-v200--autonomous-estate-and-lifecycle-control-plane)
- [Breaking at v3.0.0](roadmap.md#breaking-at-v300)
- [`docs/api-v1-migration.md`](api-v1-migration.md) — sunset 1 Aug 2027
- [`docs/blueprint-versioning.md`](blueprint-versioning.md) — schema v2 window
- [`docs/releases.md`](releases.md#roadmap-milestones-and-engine-semver) — roadmap ↔ semver
