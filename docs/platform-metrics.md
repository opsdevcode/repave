# Platform metrics (golden-path adoption)

Repave treats the IDP as a product. This surface measures **developer outcomes** — whether
teams choose golden paths, where plan→apply drops off, and how long first success takes —
instead of only generation counts and queue depth.

Roadmap theme: [v1.85 — Golden path adoption and DX metrics](roadmap-archive.md#v185--golden-path-adoption-and-dx-metrics).

Platform console enablement (fleet, auth, Prometheus optional):
[`platform-console.md`](platform-console.md).

## What is measured

| Metric | Meaning |
| --- | --- |
| **Adoption ratio** | Governed repos (fleet registry) ÷ eligible repos |
| **Bypass list** | Eligible repos not in the fleet (shadow-IT signal) |
| **Plan → apply funnel** | Dry-run vs apply counts per blueprint |
| **Time to first artifact** | Per acting user: first audit event → first successful apply (p50/p90) |
| **Service creation time** | p50/p90 of apply `duration_seconds` from audit |
| **Gate friction** | Blueprints with the highest fail rates |

**Eligible set:** configured GitHub `org:` / `topic:` searches when a token is available;
otherwise the fleet itself (ratio then reads as 100% of known governed repos).

**Audit off:** adoption still works from the fleet; funnel and time-to-first-artifact degrade
with an explicit message (same pattern as `/activity` and `/estate`).

Backstage `/adoption` calls `GET /api/v2/platform/metrics` through the proxy.

## Configuration

```yaml
# repave.config.yaml
apiVersion: repave.dev/v1

platform_metrics:
  enabled: true
  snapshot_file: data/platform-metrics/snapshots.jsonl
  github_orgs: [your-github-org]
  github_topics: []
  search_limit: 100
  baseline_adoption_ratio: 0.6
  baseline_plan_apply_ratio: 0.4
```

Env overrides:

| Variable | Effect |
| --- | --- |
| `REPAVE_PLATFORM_METRICS=1` | Enable without a config block |
| `REPAVE_PLATFORM_METRICS_FILE` | Override snapshot JSONL path |

GitHub search needs the same credentials as other GitHub features
(`GITHUB_TOKEN` or GitHub App — see [`github-app-auth.md`](github-app-auth.md)).

When `durability.database_url` is set, snapshots also land in the `dx_metrics_snapshots`
SQL table; JSONL export follows `durability.export_jsonl`.

## Surfaces

| Surface | Path / command |
| --- | --- |
| Portal (admin) | `/platform/adoption` |
| Portal compliance (admin) | `/platform/compliance` |
| Portal value stream (admin) | `/platform/value-stream` |
| Portal roadmap evidence (admin) | `/platform/roadmap` |
| API | `GET /api/v2/platform/metrics` (`?persist=1`, `?history=12`) |
| API compliance | `GET /api/v2/platform/compliance` |
| API value stream | `GET /api/v2/platform/value-stream` |
| API roadmap evidence | `GET /api/v2/platform/roadmap-evidence` |
| CLI | `repave metrics adoption [--persist] [--format json] [--history N]` |
| Prometheus | `repave_golden_path_adoption_ratio`, `repave_plan_apply_conversion_ratio`, `repave_dx_time_to_first_artifact_seconds` |

## Helm

Chart defaults turn metrics **on** (`repave.platformMetrics.enabled` and
`platformMetricsSnapshot.cronJob.enabled`). Set `githubOrgs` (and optional baselines)
in your release values:

```yaml
repave:
  platformMetrics:
    enabled: true
    snapshotFile: /data/fleet/platform-metrics.jsonl
    githubOrgs: [your-github-org]
    baselineAdoptionRatio: 0.6

platformMetricsSnapshot:
  cronJob:
    enabled: true
    schedule: "0 * * * *"
```

The CronJob runs `repave metrics adoption --persist` so `/platform/adoption` can show
trend sparklines (at/above baseline = pass). Set `enabled: false` only when you want
the portal empty-state instead of metrics pages.

## Feedback loop (v1.86)

Lightweight CSAT (1–5) and optional friction tags on **result** and **run-console** surfaces.
Events correlate with `blueprint@version`, dry-run vs apply, and gates outcome.

### Configuration

Uses the same `platform_metrics` block:

```yaml
platform_metrics:
  enabled: true
  feedback_file: data/platform-metrics/feedback.jsonl
```

| Variable | Effect |
| --- | --- |
| `REPAVE_PLATFORM_FEEDBACK_FILE` | Override feedback JSONL path |

When `durability.database_url` is set, events also land in the `feedback_events` SQL table;
JSONL export follows `durability.export_jsonl`.

### Friction tags

`slow`, `confusing-form`, `unclear-errors`, `missing-docs`, `gates-heavy`, `other`.

### Surfaces

| Surface | Path / command |
| --- | --- |
| Portal capture | Result page card; compact panel on run-console complete |
| Portal (admin) | `/platform/feedback` |
| Backstage | `/feedback` — rollup plus submit (`surface=backstage`) |
| API | `POST /api/v2/platform/feedback` (generator or admin) |
| API rollup | `GET /api/v2/platform/feedback` (admin; `?limit=50`) |

Portal JS posts once per run via `sessionStorage` — feedback append is best-effort and never
blocks generation.

## Stakeholder interfaces (v1.87)

Secondary stakeholders get dedicated **read-only** pages over the same metrics store —
behind platform-admin roles — without adding fields to the developer catalog or library.

| Audience | Portal | API | Focus |
| --- | --- | --- | --- |
| Security / compliance | `/platform/compliance` | `GET /api/v2/platform/compliance` | Gate pass rate, bypass list size, per-path friction |
| Leadership | `/platform/value-stream` | `GET /api/v2/platform/value-stream` | Adoption, plan→apply, time-to-first-artifact, trend history |

These slices reuse `capture_dx_metrics` / snapshot history; they do not introduce a separate
store or role beyond existing platform admin.

## Roadmap evidence loop (v1.89)

Connect shipped platform themes to adoption metrics and surface low-adoption golden paths
for sunset or simplification review.

| Surface | Path / command |
| --- | --- |
| Portal (admin) | `/platform/roadmap` |
| Backstage | `/roadmap` |
| API | `GET /api/v2/platform/roadmap-evidence` |
| Evidence source | `/platform/adoption` snapshot (fleet adoption, funnel, baselines) |

### Configuration

Optional block under `platform_metrics` (defaults ship v1.85–v1.88 theme rows):

```yaml
platform_metrics:
  enabled: true
  roadmap_evidence:
    sunset_conversion_threshold: 0.25
    sunset_min_plans: 1
    sunset_review_days: 90
    themes:
      - key: v185-adoption
        title: Golden path adoption and DX metrics (v1.85)
        requesting_team: platform
        evidence_kind: fleet_adoption
      - key: v188-guided-forms
        title: Cognitive load reduction (v1.88)
        requesting_team: portal
        evidence_kind: blueprint_funnel
        blueprint_names: [terraform-module-generic, ansible-role-generic]
```

`evidence_kind`: `fleet_adoption`, `plan_apply`, or `blueprint_funnel` (requires
`blueprint_names` for per-path funnel citation).

Sunset candidates list blueprints whose plan→apply conversion is below
`sunset_conversion_threshold` with at least `sunset_min_plans` audit plans; each row
includes a `review_by` date `sunset_review_days` ahead.

## Baselines

Set `baseline_adoption_ratio` / `baseline_plan_apply_ratio` once you have a stable week of
data. Trends matter more than a single reading — principle 5 from
[platform product management for IDPs](https://platformengineering.org/blog/five-product-management-principles-for-internal-developer-platforms).

## Related

- Operations overview: [`operations/README.md`](operations/README.md)
- Portal design: [`portal-design.md`](portal-design.md)
- Fleet registry: [`fleet-registry.md`](fleet-registry.md)
- Config schema: [`repave-config-v1.md`](repave-config-v1.md)
