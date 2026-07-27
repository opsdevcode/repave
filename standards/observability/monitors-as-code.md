# Monitors-as-code standard v1.0.0

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
| `datadog` | `datadog/monitors/*.json` | Datadog provider (`monitors.tf` at repo root) |
| `prometheus` | `prometheus/rules/*.yaml`, `prometheus/alertmanager/alertmanager.yaml` | `prometheus_rules.tf`, `alertmanager.tf` (`null_resource` payloads for GitOps) |

## Policy packs

Default generate inputs: `policy_pack_source=repave-observability-pack`,
`policy_profile=observability-default`. See `policy/PACKS.md` and
`standards/policy/customization.md`.

## Validation

Generated repos run `yamllint`, `promtool check rules`, `amtool check-config` (Prometheus
native), `datadog-monitor`, optional `datadog-api-validate` (when API keys are set),
`terraform-fmt` / `terraform-validate` (Terraform mode), `opa`, `secrets`, `docs-drift`,
and `provenance-drift`.

Portal dry-run uses **`require_run`**: install the gate toolchain locally or via
`deploy/local` Docker Compose so missing CLIs fail instead of skip.
