# Monitors-as-code standard v1.1.0

Governed **alerts and monitors** for the `monitors-as-code-generic` golden path:
Datadog monitors and Prometheus alerting rules (plus Alertmanager routing stubs). Dashboard
repos use `dashboards-as-code-generic`; full-stack observability uses
`observability-as-code-generic`.

## Naming

- Repository: `monitors-{organization}-{service_name}` (blueprint).
- Prometheus rule groups: `{service_name}-alerts`.
- Files under `prometheus/rules/` use kebab-case filenames.
- Datadog monitor JSON under `datadog/monitors/`.

## Required metadata

Every alert rule MUST include:

| Field | Location | Requirement |
| --- | --- | --- |
| `severity` | `labels` | One of `critical`, `warning`, `info` |
| `service` | `labels` or tags | Matches blueprint `service_name` |
| `team` | `labels` or tags | Owning team slug |
| `runbook_url` | `annotations` | HTTPS URL to the runbook |
| `summary` | `annotations` | One-line operator summary |

Datadog monitors MUST tag `service`, `team`, `org`, `env`, and `managed-by:repave`.
Monitor messages MUST reference the catalog `notification_target`.

## Notification routing

`notification_source` and `notification_target` come from `observability/catalog.json`.
Native Prometheus Alertmanager configs MUST name the receiver after `notification_target`
and include a provider-appropriate stub (`pagerduty_configs`, `slack_configs`, or
`email_configs`).

## SLOs

When `slo_target_percent` is set on generate, the repo includes a starter SLO recording
rule and burn-rate alert under `prometheus/rules/` (Prometheus native mode).

## Monitor packs

`monitor_pack_source` selects curated layouts from `observability/catalog.json`
(`monitor_packs`). Every pack includes the template baseline; non-starter packs add
files under `observability/monitors/` (see `observability/monitors/README.md`).

## Backends and output modes

| Backend | Native layout | Terraform mode |
| --- | --- | --- |
| `datadog` | `datadog/monitors/*.json` | Datadog provider (`monitors.tf` at repo root); provider `validate = false` allows `terraform plan` in CI without API keys |
| `prometheus` | `prometheus/rules/*.yaml`, `prometheus/alertmanager/alertmanager.yaml` | `prometheus_rules.tf`, `alertmanager.tf` — `null_resource` payloads (rule group + Alertmanager YAML) for GitOps; map triggers to your ruler (Mimir, AMP, Prometheus Operator, Thanos Ruler, etc.) |

`output_mode=terraform` emits `versions.tf`, `providers.tf`, `variables.tf`, and backend-specific
resources. Community **monitor packs** (`monitor_pack_source`) materialize under native paths only;
Terraform repos use the template baseline in `.tf` until pack Terraform is added in a later release.

Generated repos vend `policy/opa/policies/` from the selected pack and `tests/fixtures/plan-create-only.json`
for Conftest when live plan JSON is unavailable.

## Policy packs

Default generate inputs: `policy_pack_source=repave-observability-pack`,
`policy_profile=observability-default`. See `policy/PACKS.md` and
`standards/policy/customization.md`.

## Validation

Generated repos run `yamllint`, `promtool check rules`, `amtool check-config` (Prometheus native),
`datadog-monitor`, `datadog-api-validate` (when `DD_API_KEY` and `DD_APP_KEY` are set),
`terraform-fmt` / `terraform-validate` (when `.tf` files exist), `opa` (Terraform plan or native
JSON/YAML via conftest), `secrets`, `docs-drift`, and `provenance-drift` gates.

Dry-run and CI **require** gate CLIs when configured on the blueprint; install the repave local
toolchain or use Docker Compose for parity with publish pipelines.
