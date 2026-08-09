# FinOps enablement in repave

Repave is an internal developer platform. Its FinOps role is to make the **right cost
behavior the easy path** on golden paths — not to replace a FinOps billing warehouse.

Roadmap: [FinOps enablement (v2.x)](roadmap.md#finops-enablement-v2x) (planning labels
v1.90–v1.94). Foundation already shipped: [Cost visibility](roadmap.md#cost-visibility).

Community anchors:

- [FinOps Framework 2025](https://www.finops.org/insights/2025-finops-framework/) —
  Domains, Capabilities, and Scopes (Cloud+)
- [FOCUS](https://focus.finops.org/focus-specification/) — FinOps Open Cost and Usage
  Specification for normalized billing data

## What ships today

| Surface | Role |
| --- | --- |
| `infracost` gate | Estimate monthly cost at terraform plan / generated-repo CI |
| `gates.infracost.required` | Org floor: require Infracost (fail skips) and inject when omitted (v1.91) |
| `gates.infracost.max_monthly_usd` | Org default monthly cap; blueprint `gate_config` can tighten |
| Audit `extra` + PR evidence | Estimate summary on generation/import audit and PR checklist |
| Upgrade / import cost delta | Preview delta vs prior `.repave/cost-estimate.json` when present |
| `portal.cost_reader` (`url` / `aws` / `azure` / `k8s` / `focus`) | Read-only L30D actuals for catalog entities |
| Library badges + Cloud spend scorecard | Showback signal on `/library` and entity detail |
| Cost snapshot trends + budgets (v1.92) | Library sparklines, entity budget vs actual, `/platform/finops` rollup |
| State graph blast-radius cost join | Join Infracost breakdown to graph resources |
| Terraform tag standards | Required FinOps allocation tags on golden paths (v1.90) |

Config examples: [`repave.config.yaml.example`](../repave.config.yaml.example).

## Framework capabilities → repave

| Capability | In repave | Outside repave |
| --- | --- | --- |
| **Planning & estimating** | Infracost gate; org floor (v1.91) | Detailed rate cards, custom pricing sheets |
| **Allocation** | Tag governance (v1.90); CE/OpenCost tag filters | Shared-cost models, idle pool allocation |
| **Reporting & analytics** | Entity L30D + trends/budgets + `/platform/finops` (v1.92) | Executive BI, multi-year history |
| **Data ingestion** | Thin FOCUS reader (v1.93) | CUR → FOCUS ETL, vendor FOCUS warehouses |
| **Budgeting** | Entity / fleet budgets vs actual (v1.92) | Finance systems of record |
| **Anomaly management** | WoW/MoM threshold + webhook (v1.94) | Advanced ML anomaly products |
| **Invoicing & chargeback** | CSV/JSON export handoff (v1.94) | Invoice generation, AR, commitment purchases |
| **Rate optimization** | — | RI/SP/CUD purchase and coverage tooling |
| **Workload optimization** | Golden-path defaults (right-size later) | Autoscaling / rightsizing engines |

## Inform → Optimize → Operate

1. **Inform (v1.90, v1.92)** — Required allocation tags so spend maps to owners; trends and
   budgets so teams see their share.
2. **Optimize (v1.91)** — Cost in the path of change: require estimates, org monthly caps,
   PR evidence (shipped — see below).
3. **Operate (v1.93–v1.94)** — FOCUS-shaped ingest when multi-cloud normalization matters;
   export for finance; simple anomaly notifications.

## Tag → actuals mapping

Cost readers resolve catalog fields to cloud tags (defaults today: owner → `Owner`, service
name → `Service`). Incomplete tags yield `tag_coverage` of `partial` or `missing` and suppress
actuals.

v1.90 makes those tags **gate-enforced** on golden paths and allows org-specific key names via
`portal.cost_allocation.tag_keys`.

### Gate enforcement (v1.90)

| Gate | What fails |
| --- | --- |
| Checkov `CKV2_REPAVE_13` | `locals.tf` `common_tags` missing `Owner`/`Service`/`Environment`/`CostCenter` from module inputs |
| OPA `allocation_tags` | Terraform plan resources with tags missing allocation keys |
| OPA `kubernetes` (helm) | Deployment `metadata.labels` missing `repave.dev/owner`, `repave.dev/service`, `repave.dev/environment` |
| Cloud spend scorecard | **Fail** (not warn) when `portal.cost_reader` is configured and catalog tags are incomplete |

Configure org-specific cloud tag key names (defaults: `Owner`, `Service`, `Environment`, `CostCenter`):

```yaml
portal:
  cost_allocation:
    tag_keys:
      owner: Team
      service: App
      environment: Environment
      cost_center: CostCenter
```

Environment override: `REPAVE_COST_ALLOCATION_TAG_KEYS=owner=Team,service=App,environment=Environment,cost_center=CostCenter`.
`portal.cost_aws` / `portal.cost_azure` `tag_key_*` inherit from `cost_allocation` unless overridden per reader block.

| Catalog field | Typical cloud tag | Used by |
| --- | --- | --- |
| `owner` | `Owner` | AWS CE, Azure Cost Management |
| `display_name` / service | `Service` | AWS CE, Azure Cost Management |
| Kubernetes label | `app.kubernetes.io/name` (default aggregate) | OpenCost `k8s` reader |

## Estimate policy at plan time (v1.91)

Org floor in `repave.config.yaml` (or env):

```yaml
gates:
  infracost:
    required: true          # fail when Infracost cannot run; inject gate when omitted
    max_monthly_usd: 500    # default cap when blueprint has no gate_config.infracost
```

| Env | Effect |
| --- | --- |
| `REPAVE_INFRACOST_REQUIRED=1` | Same as `required: true` |
| `REPAVE_INFRACOST_MAX_MONTHLY_USD` | Overrides org `max_monthly_usd` |

Blueprint `gate_config.infracost.max_monthly_usd` still wins when set (stricter per path).
Estimates land in audit `extra` (`cost_estimate_*`), the generate PR evidence checklist,
and upgrade/import preview deltas when a prior `.repave/cost-estimate.json` exists.

## Showback: trends and budgets (v1.92)

```yaml
portal:
  cost_snapshots:
    enabled: true
    file: data/fleet/cost-snapshots.jsonl
  cost_budgets:
    default_monthly_usd: 250
    entities:
      opsdevcode-tf-aws-eks-demo: 600
```

| Surface | Role |
| --- | --- |
| Library sparklines | 8-point L30D trend from snapshot JSONL/SQL |
| Entity detail | Budget vs actual badge + trend sparkline |
| `/platform/finops` | Fleet rollup table; over-budget entities first |
| `/metrics` | `repave_finops_fleet_actual_30d_usd`, `repave_finops_fleet_budget_monthly_usd`, `repave_finops_over_budget_entities` |

Per-entity budget can also come from `repave.dev/monthly-budget-usd` on `catalog-info.yaml`
(config overrides catalog; catalog overrides default).

## Thin FOCUS ingest (v1.93)

Repave accepts FOCUS-shaped data produced **elsewhere** (cloud FOCUS export or
[FOCUS converters](https://github.com/finopsfoundation/focus_converters)). It does not retain
multi-year CUR or run full FOCUS ETL.

```yaml
portal:
  cost_reader: focus
  cost_focus:
    file: data/focus/export.json   # or https://billing.example/focus.jsonl
    lookback_days: 30
    tag_key_owner: Owner
    tag_key_service: Service
```

Env override: `REPAVE_COST_FOCUS_FILE` (path or HTTPS URL).

**Supported formats:** JSON array, JSON object with `rows`/`data`/`records`, or JSONL.
Parquet is not read in-process — convert to JSON/JSONL upstream.

**Supported column subset** (case-insensitive; extra columns ignored):

| FOCUS column | Use |
| --- | --- |
| `BilledCost` | Amount summed per entity |
| `BillingCurrency` | Currency (default `USD`) |
| `ChargePeriodStart` / `BillingPeriodStart` | Lookback window filter |
| `ChargePeriodEnd` / `BillingPeriodEnd` | `as_of` timestamp |
| `ServiceName` | Service dimension fallback when service tag absent |
| `Tags` | Map or key/value list → owner / service allocation |

Rows match catalog entities using the same allocation rules as AWS/Azure readers
(`portal.cost_allocation.tag_keys` / `cost_focus.tag_key_*`). L30D actuals feed library
badges, entity detail, and `/platform/finops` rollup.

## Explicit non-goals

- Full FOCUS warehouse / multi-year CUR retention inside Postgres
- Commitment discount or rate-optimization engines
- GCP Cost Explorer–style native API beyond FOCUS ingest (FOCUS is the multi-cloud path)
- Replacing OpenCost/Kubecost for cluster idle and shared-cost detail — keep
  `portal.cost_reader: k8s`; use those products for depth
- Org-wide invoicing / AR — chargeback is an **export**, not a billing system

## Related

- Product model (IDP): [Concepts](concepts.md) · [README — What repave is](../README.md#what-repave-is)
- Roadmap cluster: [FinOps enablement](roadmap.md#finops-enablement-v2x)
- Shipped foundation: [Cost visibility](roadmap.md#cost-visibility)
- Config contract: [`repave-config-v1.md`](repave-config-v1.md)
- Portal surfaces: [`portal-design.md`](portal-design.md)
- Docs index: [`README.md`](README.md)
- Operations index: [`operations/README.md`](operations/README.md)
- State graph cost join: [`state-graph.md`](state-graph.md)
