# ADR 013: Component-level self-service vending

**Status:** Accepted — vend + TTL reclaim  
**Date:** 2026-08-16  
**Scope:** engine catalog, async runs, GitOps PR flow, component reclaim.
Extends [ADR 003](003-environment-lifecycle-and-live-state.md) Phase 4.
Does not change environment reclaim, state custody (ADR 004), or
`POST /api/v2/components/plan` (`repave add` onto an existing repo).
**Related:** [`docs/api-v2.md`](../api-v2.md),
[`docs/service-catalog.md`](../service-catalog.md)

## Context

ADR 003 Phase 3 vends **environments** by writing desired state into a GitOps
repository. Builders still request a managed database, bucket, or queue by
hand — a second write path that skips gates, or a ticket that never becomes
lineage.

`POST /api/v2/components/plan` layers a second **blueprint** onto a governed
repo. That is not vending a cloud component.

## Decision

**Vend managed components the same way as environments: render a governed
blueprint, open a GitOps PR, register the result. repave does not run
`terraform apply`.**

### Kinds

Built-in kinds: `database`, `bucket`, `queue`. Each maps to a blueprint
(default `terraform-environment-stack`) and default inputs. Operators may
override the catalog in `component_vending.kinds`.

### Flow

1. `POST /api/v2/components/vend` (or `POST /api/v2/runs` with
   `kind: component_vend`) enqueues a worker run.
2. Generate runs the blueprint gates. `dry_run: true` (API default) stops
   there.
3. A non–dry-run run clones the GitOps repo, writes
   `{path_prefix}/{kind}/{name}`, and opens a reviewable PR.
4. Success appends `data/components/registry.jsonl`. Catalog entities use
   `"source": "component"`.
5. `POST /api/v2/components/reclaim` (admin) opens a GitOps decommission PR
   that removes `{path_prefix}/{kind}/{name}`. Auto-reclaim kinds drop from
   the registry when the PR opens (or the path is already gone). Other kinds
   stay `expired` until the PR merges (`registry_finalize`).

Credentials stay GitHub-shaped. CD applies after merge.

### Out of scope (later slices)

- Dedicated RDS/S3/SQS module blueprints
- Operator JSON contract changes
- Backstage UI for component reclaim

Backstage `/vend` calls `GET /api/v2/component-kinds` and
`POST /api/v2/components/vend`.

## Consequences

- Environment and component vending share the GitOps-only boundary.
- A later kind-specific blueprint can replace `terraform-environment-stack`
  without changing the API.
- Component reclaim is a separate admin API from environment reclaim.
