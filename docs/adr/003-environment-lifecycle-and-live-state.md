# ADR 003: Environment lifecycle and how far repave reaches into live state

**Status:** Accepted for **Phase 1** (deployment status, read-only). Phases 2–3 are
directional — revisit this ADR before implementing either.  
**Date:** 2026-08-01  
**Scope:** engine catalog read models, portal, worker role, `repave.config.yaml`, blueprints
(`terraform-environment-stack`) — v2.x line, post [contract freeze](../roadmap.md#v200--platform-ga)

## Context

repave v2.0.0 governs **repositories**. The loop is generate → gate → publish → observe pin
drift → open a remediation PR, and it stops at the pull request. Three consequences follow
from that boundary:

- **Nothing knows what is running.** `CatalogEntity`
  ([`engine/src/repave_engine/entity_catalog.py`](../../engine/src/repave_engine/entity_catalog.py))
  carries blueprint lineage, standard pins, scorecards, operator phase, and cost — but no
  answer to "did my last change reach an environment?" The portal can show a merged
  remediation PR next to a stale deployment and cannot tell the difference.
- **Policy is evaluated against repo shape, not effect.** Gates run over rendered output;
  `terraform validate` needs no state, and Checkov and OPA read files. A change that is
  perfectly compliant as source can still destroy a database on apply, and repave has no
  view of that.
- **"Drift" means pin drift.** The operator compares `repave.yaml` provenance against
  blueprint and standard versions. Infrastructure drift — the resource someone edited in the
  console — is invisible.

The `terraform-environment-stack` blueprint and its standard generate a repository that
*describes* an environment. Nothing requests, vends, tracks ownership of, bounds the cost of,
or reclaims an actual environment. The roadmap parked this under
[beyond v2.0.0](../roadmap.md#lifecycle-control-plane) as "environments as a service" and
"deployment health", which assumed the next step was a v3 concern.

Four constraints frame any answer:

1. **Local-first.** The full loop must keep running on a laptop via Compose and `make serve`.
   Anything added here is optional and off by default.
2. **No bypass.** Every artifact that reaches a repository passed the blueprint's gates.
   A live-state feature must not create a second path that skips them.
3. **A human on every mutation.** v2 keeps a person on remediation PRs by design; the
   low-risk auto-merge tier is explicitly [v3 work](../roadmap.md#autonomous-governed-remediation).
4. **repave must not become a credential honeypot.** It already holds GitHub write access for
   the whole estate. Adding cloud administrative credentials to the same service multiplies
   blast radius far more than it multiplies capability.

## Decision

Adopt a three-rung ladder from **read** to **plan** to **vend**, and commit only to rung 1
now. Each rung is independently valuable, and each one earns the credentials the next needs.

### Phase 1 — Deployment status (read-only) — accepted

Enrich catalog entities with deployment state read from the GitOps controller that already
owns it (Argo CD or Flux): sync state, health, deployed revision, last-synced timestamp, and
a deep link.

Reuse the enrichment pattern the catalog already established rather than inventing one:

| Concern | Existing precedent | Applies here |
| --- | --- | --- |
| Reader dispatch by config | `cost_reader: url \| aws \| azure` in `cost_actuals.py` | `deployment_reader: url \| argocd \| flux` |
| Detail-route fetch, cheap list | `slo_summary` / `cost_actuals` on entity detail | `deployment_status` on entity detail |
| Cheap list-wide state | `fleet.operator_status_file` snapshot written by `repave fleet-operator-snapshot` | optional snapshot refresh for list/scorecard |
| TTL cache | `cost_cache.py` (1h) | shorter TTL; deployment state moves faster than spend |
| Frozen entity enrichment | `dataclasses.replace` in `catalog_cost.py` | same |
| Scorecard dimension | `apply_cost_to_scorecard` | optional `deployment` dimension |

Credentials are **read-only, server-side, and optional**. The reader is a best-effort side
path: an Argo outage degrades the entity to "unknown" and never fails a catalog request.

**repave does not write.** No sync, no rollback, no refresh trigger. Argo and Flux keep
owning reconciliation; repave observes.

### Phase 2 — Governed plan against live state — directional

Run a real `terraform plan` for a target repository or environment against a configured
backend, evaluate OPA against the **plan JSON** rather than the source tree, and attach the
plan summary plus policy verdict to the run record and the PR body.

Boundaries that must hold if this is built:

- **Worker role only.** Plans execute through the existing run queue and per-run Kubernetes
  Jobs ([ADR 002](002-v2-service-decomposition.md)), never in the portal process. Credentials
  are scoped per environment and mounted into the Job, not the portal.
- **Plan output is sensitive.** Plan JSON can contain resource attributes and occasionally
  secret material. It gets bounded retention, redaction before display, and it never enters
  `repave.yaml` provenance or the audit record — only a summary and the policy verdict do.
- **Plan only.** No apply on this rung, regardless of how convenient it becomes.

### Phase 3 — Environment vending and sandboxes — directional

Request an environment from a governed environment blueprint, receive one with an owner, a
TTL, a cost view, and a lifecycle.

The decision that matters here: **repave vends by writing desired state into a GitOps
repository and lets the existing CD toolchain apply it.** repave does not run `terraform
apply` against production cloud credentials.

That keeps every property v2 already relies on. The change is a reviewable commit, git stays
the system of record, gates still run before anything is published, the audit trail is the
same one that covers generation, and repave's credential surface stays GitHub-shaped.

Environment records carry owner, class, TTL, blueprint lineage, deployment status (Phase 1),
and cost. On expiry, a **sandbox-class** environment may be reclaimed automatically inside a
non-production boundary with a budget cap; anything else expires into a decommission PR with
a human on it.

## Alternatives considered

| Option | Rejection |
| --- | --- |
| repave becomes a Terraform runner (Atlantis / Spacelift shape) | Puts cloud admin credentials next to estate-wide GitHub write access; makes repave own state locking and backends; duplicates a mature tool category; breaks local-first. |
| Portal reads the cluster directly with a kubeconfig | Portal is toolchain-free, stateless, and multi-replica; per-replica cluster clients add latency and an outage mode to every catalog request. Snapshot plus worker fetch matches the existing operator-status design. |
| Store deployment status on the `GoldenPathRepo` CRD | The CRD governs repository conformance. Deployment state is per-environment, changes on a different cadence, and would churn status writes against etcd. |
| Skip Phase 1 and build sandboxes directly | Vending without a status read gives no feedback loop: repave would create environments it cannot observe, and every failure becomes a support ticket. |
| Infrastructure drift detection in the operator now | Requires provider credentials for the whole estate before there is any consumer for the signal. Revisit after Phase 2 proves credential scoping. |

## Consequences

- **Positive:** the catalog finally answers "is my change live"; Phase 2 makes policy
  preventative rather than descriptive; Phase 3 gives environments owners, expiry, and cost
  without repave holding apply rights.
- **Negative:** new optional configuration and credential surface at each rung; more external
  dependencies that must degrade gracefully; a second definition of "drift" (pin drift versus
  deployment divergence) that the portal has to keep legible.
- **Local-first preserved:** every rung is optional and disabled by default. Compose and
  `make serve` are unchanged when no reader is configured.
- **Deferred risk:** Phase 3 depends on the adopter running Argo CD or Flux. Shops that apply
  Terraform from CI get Phase 1 through the generic `url` reader and little from Phase 3
  until a CD-agnostic vending path exists.

## Acceptance

**Phase 1**

- A catalog entity backed by an Argo CD application shows sync state, health, deployed
  revision, and last-synced time in the portal and on `GET /api/v2/catalog/entities/{id}`.
- With no `deployment_reader` configured, catalog responses are byte-identical to today.
- With the reader configured and the GitOps API unreachable, entity detail still renders and
  reports unknown status rather than erroring.
- No repave code path writes to Argo CD or Flux.

**Phase 2 (before implementation)**

- A plan runs in a worker Job with per-environment credentials, and a policy failure on plan
  JSON blocks the PR the same way a gate failure does.
- Plan JSON never appears in provenance, audit records, or logs.

**Phase 3 (before implementation)**

- An environment request produces a reviewable commit in a GitOps repository, and the applied
  environment appears as a catalog entity with owner, TTL, and cost.
- A sandbox past its TTL is reclaimed inside the non-production boundary; a non-sandbox
  environment expires into a decommission PR.

## References

- [Roadmap — environment lifecycle and deployment awareness](../roadmap.md#environment-lifecycle-and-deployment-awareness)
- [Roadmap — lifecycle control plane (v3 boundary)](../roadmap.md#lifecycle-control-plane)
- [ADR 002 — v2 service decomposition](002-v2-service-decomposition.md) (worker role, per-run Jobs)
- [ADR 001 — `GoldenPathRepo.spec.repoURL` remote inventory](001-goldenpathrepo-repo-url-inventory.md)
- Catalog read model: `engine/src/repave_engine/entity_catalog.py`,
  `portal_context.py`, `fleet_view.py`
- Enrichment precedents: `cost_actuals.py`, `cost_cache.py`, `observability_slo.py`,
  `fleet_operator_status.py`
