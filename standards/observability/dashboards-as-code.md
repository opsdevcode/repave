# Dashboards-as-code standard v1.2.0

Version: 1.2.0

Governed **Grafana** and **Datadog** dashboard JSON for the
`dashboards-as-code-generic` golden path. This standard aligns repave output with
widely adopted observability practice so teams start from a compliant baseline,
not a blank canvas.

## Community alignment

Repave encodes guidance from these sources (paraphrased as requirements below;
see [References](#references) for links):

| Practice | What we enforce in generated repos |
| --- | --- |
| **Four golden signals** (latency, traffic, errors, saturation) | Baseline dashboard: request rate, error rate, latency (p99) |
| **RED method** (Rate, Errors, Duration) for services | `service-golden-signals` layout and panel titles |
| **USE method** (Utilization, Saturation, Errors) for infra | Documented as follow-up rows; not auto-generated in v1 |
| **Grafana dashboard best practices** | UIDs, tags, templated `environment`, rows, shared crosshair, sane time range |
| **Datadog dashboard guidelines** | Ordered layout, note + query widgets, `template_variables`, unified tags |
| **OpenTelemetry resource semantics** | Tags/labels use `service`, `team`, and `deployment.environment` (`env:` tag) |
| **GitOps / as-code** | JSON under version control; `managed-by:repave` tag; gates block drift |

## Naming and layout

- Repository: `dashboards-{organization}-{service_name}` (blueprint).
- **Grafana** files: `grafana/dashboards/*.json` (kebab-case filenames).
- **Datadog** files: `datadog/dashboards/*.json`.
- Dashboard UIDs (Grafana): `{service_name}_overview`, `{service_name}_golden`
  (hyphens in `service_name` become underscores in UID).
- One **overview** dashboard (context, links, ownership) and one **golden signals**
  dashboard (platform baseline: rate, errors, duration).

## Required metadata

### Tags (both backends)

Every dashboard MUST include tags (Grafana `tags`, Datadog `tags`):

| Tag | Example | Purpose |
| --- | --- | --- |
| `service:{service_name}` | `service:checkout` | Service identity (OTel `service.name`) |
| `team:{team}` | `team:payments` | Ownership |
| `org:{organization}` | `org:platform` | Business unit / org slug |
| `env:{environment}` | `env:prod` | Deployment environment (OTel `deployment.environment`) |
| `managed-by:repave` | fixed | Provenance for golden-path generation |

Optional: `repave:golden-signals` on the golden-signals dashboard.

### Grafana-specific

| Field | Requirement |
| --- | --- |
| `title`, `uid` | Set; UID stable for GitOps import |
| `schemaVersion` | ≥ 39 |
| `timezone` | `browser` unless org standard says UTC |
| `refresh` | `30s` or `1m` on operational dashboards |
| `time` | Default last 1h (`now-1h` → `now`) |
| `templating` | `environment` variable matching blueprint input |
| `graphTooltip` | `1` (shared crosshair) on golden-signals dashboard |
| Panels | Overview: text + links; golden: **row** then RED timeseries |

Panels SHOULD use the blueprint `datasource_uid` (default `prometheus`) and filter
metrics with `service="{{ service_name }}"` and `environment="$environment"` where
applicable.

### Datadog-specific

| Field | Requirement |
| --- | --- |
| `title`, `description` | Set |
| `layout_type` | `ordered` |
| `widgets` | Non-empty; include note widget on overview |
| `template_variables` | `env` defaulting to blueprint `environment` |
| Queries | Filter with `service:{{ service_name }}`, `env:$env` (or equivalent) |

## Dashboard design rules

1. **Overview first** — Operators land on context, runbook link, notification routing,
   and a link to golden signals before deep metrics.
2. **RED before custom** — Extend golden signals before adding bespoke charts; keeps
   on-call muscle memory consistent ([Grafana][grafana-best], [Google SRE][sre-book]).
3. **No secrets in JSON** — API keys and tokens belong in CI/secrets stores only
   (`secrets` gate).
4. **Same tags on every dashboard** — Enables catalog search and chargeback in Grafana
   and Datadog.
5. **Prefer composable variables** — Environment (and later region) via variables, not
   hard-coded query strings.
6. **Document exceptions** — If you remove a required tag or panel class, record why
   in the repo README.

## Validation

| Gate | When |
| --- | --- |
| `grafana-dashboard` | Grafana JSON present under `grafana/dashboards/` |
| `datadog-dashboard` | Datadog JSON present under `datadog/dashboards/` |
| `terraform-fmt`, `terraform-validate` | `.tf` files at repo root (`output_mode=terraform`) |
| `opa` | Terraform mode when `conftest` is installed (managed-by tags) |
| `secrets`, `docs-drift`, `provenance-drift` | Always |

Native mode materializes **community dashboard packs** from `observability/dashboards/`.
Terraform mode can materialize the same packs and emit `dashboard_packs.tf` (`file()`-backed
`grafana_dashboard` / `datadog_dashboard_json` resources) or a starter `dashboard.tf` when the
pack has no vendored files.

Only one backend’s dashboard directory is emitted per generate (`backend` input) in native mode.

## Community dashboard packs

Packs are registered in `observability/catalog.json` (`dashboard_packs`) and materialized at
generate time from `observability/dashboards/`. Each pack entry MUST include:

- **Upstream link** (`reference_url`) and **license** when forked from Grafana.com or Datadog.
- **Parameterized templates** (`.json.jinja`) using blueprint inputs (`service_name`, `team`,
  `environment`, …).
- **`community:*` tag** on forked dashboards (for example `community:grafana-1860`).

The **platform baseline** pack ships only template-generated overview + golden-signals JSON.
Other packs **add** vendored community forks alongside the baseline (for example Node Exporter
[Grafana.com #1860](https://grafana.com/grafana/dashboards/1860), Kubernetes pods
[#15760](https://grafana.com/grafana/dashboards/15760), Datadog APM layouts).

Do not vendor multi-megabyte upstream exports; maintain a **reviewable fork** with attribution
and queries adapted to your metric model.

## References

- [Grafana: Best practices for dashboards][grafana-best]
- [Grafana: Dashboard management (GitOps)][grafana-gitops]
- [Google SRE Book — Monitoring distributed systems (four golden signals)][sre-book]
- [OpenTelemetry: Resource semantic conventions][otel-resource]
- [Datadog: Dashboard documentation][datadog-dashboards]
- [Datadog: Tagging best practices][datadog-tags]

[grafana-best]: https://grafana.com/docs/grafana/latest/dashboards/build-dashboards/best-practices/
[grafana-gitops]: https://grafana.com/docs/grafana/latest/administration/dashboard-management/
[sre-book]: https://sre.google/sre-book/monitoring-distributed-systems/
[otel-resource]: https://opentelemetry.io/docs/specs/semconv/resource/
[datadog-dashboards]: https://docs.datadoghq.com/dashboards/
[datadog-tags]: https://docs.datadoghq.com/tagging/
