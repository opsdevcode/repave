# ADR 001: `GoldenPathRepo.spec.repoURL` remote inventory

**Status:** Accepted — Phases A and B shipped (v1.72); Phase C outstanding  
**Date:** 2026-07-26 (updated 2026-07-27)  
**Scope:** repave operator (v1.17 GA+)

## Context

The `GoldenPathRepo` CRD accepts either:

- **`spec.localPath`** — read `repave.yaml` and the working tree on the operator pod (or a
  kind hostPath mount). **Shipped** for GA.
- **`spec.repoURL`** — intended for module repos hosted on GitHub (or other git remotes).

Today, inventory via **`repoURL` is not implemented**. The controller returns
`RemoteRepoUnsupported` and does not clone remotes ([`operator/internal/inventory/observe.go`](../../operator/internal/inventory/observe.go)).
Remediation PRs that push to GitHub already require `spec.repoURL` when `dryRun` is false
([`operator/internal/controller/remediation.go`](../../operator/internal/controller/remediation.go)).

Platform teams want to register many generated repos without mounting host paths into the
cluster. The engine and portal already support **local path** upgrade preview
(`repave update`, `/update`); the operator should eventually reconcile the same contracts
against remote repos.

## Decision

Implement **remote git inventory** as a **follow-on operator slice**, not a blocker for
v1.17 GA:

1. **Phase A — Read-only inventory (shipped):** shallow clone of the default branch into a
   temporary workspace; read `repave.yaml`; populate `status.observedPins` (same shape as
   `localPath`); remove the workspace. `internal/git/clone.go` +
   `inventory.RepoFetcher`; transient failures set `RemoteFetchFailed` and requeue.
2. **Phase B — Upgrade plan on cluster (shipped):** the clone is materialized once per
   reconcile as an `inventory.Workspace` and reused for both observation and bundled
   `repave plan-upgrade`, so `status.upgradePlan` is populated for remote repos with the
   same JSON contract as `localPath`.
3. **Phase C — Remediation:** reuse existing GitHub client; `spec.repoURL` + token on the
   operator Deployment; optional `preserveLocal` semantics documented for remote repos.

`RemoteRepoUnsupported` remains the surfaced reason when the operator runs without a
configured fetcher; `localPath` is still recommended for kind/e2e and dev clusters.

## Non-goals (this ADR)

- Multi-cluster fleet API or cross-tenant repo registry (v2).
- Replacing GitHub with in-cluster git hosting.
- Operator-side policy catalog editing (generation stays in the engine).

## Credentials and security

- **Clone/fetch:** use a Kubernetes Secret (or external secrets operator) referenced by
  the operator — e.g. `GITHUB_TOKEN` or deploy key with read access to module repos.
- **Never** log tokens; read-only inventory must not require write scope.
- **Remediation** continues to use the existing push/PR path with repo-scoped tokens.

## Alternatives considered

| Option | Rejection |
| --- | --- |
| Require `localPath` only forever | Does not scale to production module estates on GitHub. |
| Portal polls GitHub API for pins | Duplicates git truth; bypasses `repave.yaml` contract. |
| Sidecar git-sync per `GoldenPathRepo` | Heavier ops; defer until Phase A proves insufficient. |

## Consequences

- **Positive:** Clear GA boundary; CRD stays stable; e2e keeps using `localPath` fixtures.
- **Negative:** Users with only `repoURL` see unsupported status until Phase A lands.
- **Engine:** No change to `repave.yaml` schema for inventory; operator calls existing CLI
  subprocess contracts.

## Acceptance (when implemented)

- `GoldenPathRepo` with `spec.repoURL` (mock git server or Gitea in e2e) reaches
  `OutOfDate` when fixture pins drift from `spec.desiredPins`.
- Document Secret shape in [`docs/operator-local-dev.md`](../operator-local-dev.md) and
  [`operator/README.md`](../../operator/README.md).
- Update [Operator GA scope](../operator-ga.md) out-of-scope table → shipped.

## References

- [`docs/operator-ga.md`](../operator-ga.md)
- [`docs/operator-overview.md`](../operator-overview.md)
- Operator inventory: `operator/internal/inventory/observe.go`
