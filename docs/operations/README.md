# Repave service operations

Starter SLOs, alerts, and runbooks for a hosted repave engine (v1.35–v1.38).

## SLO targets (starter)

| SLI | Target | Notes |
| --- | --- | --- |
| Availability | 99.5% monthly | `GET /health` or ingress success rate |
| Generation success | 95% rolling 7d | `repave_generations_total{outcome="passed"}` |
| p95 generation latency | &lt; 120s | `repave_generation_seconds` histogram |

## Dashboards and alerts

- Import [`deploy/k8s/grafana-dashboard-repave.json`](../../deploy/k8s/grafana-dashboard-repave.json).
- Apply [`deploy/k8s/prometheus-rules.yaml`](../../deploy/k8s/prometheus-rules.yaml) with Prometheus Operator.

## Runbooks

### Generation failures

1. Check portal or audit JSONL for `gates_outcome=failed`.
2. Open the result gate excerpt or re-run with `--dry-run` via CLI.
3. Confirm gate tools exist in the image (terraform, checkov, etc.).

### Slow generations

1. Inspect `/metrics` and [OpenTelemetry traces](tracing.md) for stage timing.
2. Scale replicas or reduce concurrent Scaffolder/portal load.

### OIDC / sign-in outage

1. Confirm IdP status and client secret rotation.
2. Fall back to read-only mode is **not** automatic — restore IdP or disable
   `auth.service_mode` only in break-glass (local open mode).

### GitHub publish failures

1. Verify `GITHUB_TOKEN` scopes and expiry (`/readyz` reports presence only).
2. See rate-limit guidance in engine logs.

## Related

- [`docs/auth-service-mode.md`](../auth-service-mode.md) — OIDC and roles
- [`docs/backstage.md`](../backstage.md) — Scaffolder and `POST /api/v1/generate`
