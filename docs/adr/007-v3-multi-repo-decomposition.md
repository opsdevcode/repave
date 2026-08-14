# ADR 007: v3 multi-repo decomposition and per-repo CI

**Status:** Accepted — extraction scaffolding on `main`; physical repo split in phases.
**Date:** 2026-08-12
**Scope:** repository boundaries, CI sharding, release coordination for v3.0.0.
**Related:** [ADR 002](002-v2-service-decomposition.md) (runtime roles shipped),
[ADR 008](008-v3-branching-release-and-testing.md) (branching),
[`docs/v3-development.md`](../v3-development.md),
[`versions.lock`](../../versions.lock)

## Context

[ADR 002](002-v2-service-decomposition.md) shipped runtime decomposition: portal/worker/corpus
images, Postgres queue, per-run Jobs, operator on `/api/v2`. The **codebase** stayed a single
`repave-engine` package with **1,571** pytest cases (~165s for `make test-fast` alone). CI runs
the full suite with coverage on every non-docs PR.

ADR 002 deferred **repository** split to v3 when a concrete trigger appears. CI duration
crossing the ~3-minute dev loop is that trigger, alongside the existing triggers (independent
release cadence, external contributors).

## Decision

Split the monorepo into **six code repositories** plus a slim **umbrella** `opsdevcode/repave`,
following the OCI image map in [`deploy/packages/`](../packages/README.md).

| Repository | Contents | PR CI focus |
| --- | --- | --- |
| `opsdevcode/repave-corpus` | `blueprints/`, `standards/`, `policy/`, `schemas/`, `ansible/`, `observability/` | Conformance manifests + render-only matrix |
| `opsdevcode/repave-core` | Pure domain: blueprint, pipeline, gates corpus, provenance | Unit tests, no FastAPI, no gate subprocesses |
| `opsdevcode/repave-worker` | `generate_api`, worker queue path, `gate_runners` | Gate integration with toolchain |
| `opsdevcode/repave-server` | FastAPI routers, portal, platform, durability HTTP | `test_api*` / `test_portal*` / `test_platform*` |
| `opsdevcode/repave-cli` | `cli/` (already isolated) | Boundary tests + 80% coverage |
| `opsdevcode/repave-operator` | `operator/` Go module | envtest + nightly kind e2e |
| `opsdevcode/repave` (umbrella) | Helm charts, docs, `versions.lock`, integration harness | Chart validate + kind smokes + contract matrix |

**Non-goals preserved from ADR 002:** gates are not a network service; fleet/audit/registry stay
read models in `repave-server`; the laptop loop still works via the umbrella dev compose.

### Monorepo preparation (before `git filter-repo`)

Until extraction completes, the umbrella repo carries:

- [`repos/`](../repos/README.md) — extraction manifests and target READMEs per future repo
- [`packages/`](../packages/README.md) — Python package boundaries (`repave-core`, `repave-server`,
  `repave-worker`) with import-boundary tests
- **Sharded engine CI** — `engine-unit`, `engine-portal`, `engine-slow` parallel jobs
- [`versions.lock`](../../versions.lock) — pinned cross-artifact versions for integration

### Extraction sequence

1. **Phase 0 (umbrella, `main`):** pytest shards + path filters — immediate CI relief
2. **Phase 1:** `repave-corpus` — lowest coupling; conformance-only CI
3. **Phase 2:** `repave-operator`, `repave-cli` — already isolated modules
4. **Phase 3:** `repave-core` / `repave-server` / `repave-worker` Python split with boundary tests
5. **Phase 4:** `versions.lock` + umbrella integration matrix; coordinated `v3.0.0` merge-back

Extraction scripts live under [`scripts/extract-repos/`](../scripts/extract-repos/README.md).

### Local-first dev

`make serve` and `docker compose up` bind-mount all checkouts via `REPAVE_DEV_REPOS` (documented
in [`docs/v3-development.md`](../v3-development.md)). A single-process collapse remains the
default for contributors who only clone the umbrella repo.

### Release coordination

- Each extracted repo gets its own semantic-release workflow
- Umbrella [`versions.lock`](../../versions.lock) pins corpus digest, PyPI packages, and chart
  `appVersion`
- Integration workflow runs nightly and before every `3.0.0-rc.N` tag
- rc tags must **not** dispatch `repave-release` to hosted infra (see ADR 008)

## Consequences

- **Positive:** PR CI time drops to parallel ~90s shards; corpus/operator/cli PRs stop running
  the full 1,571-test engine job; independent release cadence per artifact
- **Negative:** cross-repo coordination cost; `versions.lock` must stay current
- **Contract risk:** `/api/v2` is public and internal transport — contract tests in umbrella
  integration harness are mandatory before rc tags

## Acceptance

- A blueprint-only PR runs corpus conformance CI only (not engine-unit/portal/slow)
- `make test-core`, `make test-portal`, `make test-slow` mirror CI shards locally
- Import boundary tests fail if `repave-server` imports `gate_runners` or `repave-cli` imports
  `fastapi`
- `versions.lock` lists every published artifact version; integration workflow passes on `main`
