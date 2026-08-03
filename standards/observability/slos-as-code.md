# SLOs-as-code standard v1.0.0

Version: 1.0.0

Governed **service level objectives** for the `slo-as-code-generic` golden path: Prometheus
recording rules and multi-window burn-rate alerts. Symptom monitors live in
`monitors-as-code-generic`; dashboards in `dashboards-as-code-generic`.

## Naming

- Repository: `slo-{organization}-{service_name}` (blueprint).
- Recording rules: `{service_name}:slo:availability:ratio5m` and `:ratio1h`.
- Burn alerts: `{service_name}_slo_burn_fast` (5m) and `_slo_burn_slow` (1h).

## Required metadata

Every burn-rate alert MUST include:

| Field | Location | Requirement |
| --- | --- | --- |
| `severity` | `labels` | `critical` for fast burn, `warning` for slow burn |
| `service` | `labels` | Matches blueprint `service_name` |
| `team` | `labels` | Owning team slug |
| `runbook_url` | `annotations` | HTTPS URL (repo `RUNBOOK.md` or wiki) |
| `summary` | `annotations` | One-line operator summary |

## Runbook

Generated repos ship `RUNBOOK.md` with **Owner**, **Escalation**, **Dashboards**,
**Rollback procedure**, and **Game-day checklist** sections. The `docs-drift` gate
enforces these headings.

## SLO target

`slo_target_percent` is required at generate time (for example `99.9`). Burn thresholds
follow Google SRE multi-window guidance (fast burn ≈ 14.4× budget, slow burn ≈ 6×).

## Policy packs

Optional **`enable_policy`** vend **`repave-observability-pack`** / profile
**`observability-default`**. See `policy/PACKS.md`.

## Validation

Generated repos run `yamllint`, `promtool check rules`, optional `opa`, `secrets`,
`docs-drift`, and `provenance-drift` gates.

Cross-links: [`monitors-as-code.md`](monitors-as-code.md), [`dashboards-as-code.md`](dashboards-as-code.md).
