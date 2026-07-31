# Repave service operations

SLOs, alerts, and runbooks for a hosted repave engine (day-2 operability).

## SLO targets (starter)

| SLI | Target | Notes |
| --- | --- | --- |
| Availability | 99.5% monthly | `GET /health` or ingress success rate |
| Generation success | 95% rolling 7d | `repave_generations_total{outcome="passed"}` |
| p95 generation latency | &lt; 120s | `repave_generation_seconds` histogram |

## Dashboards and alerts

- Import [`deploy/k8s/grafana-dashboard-repave.json`](../../deploy/k8s/grafana-dashboard-repave.json).
- **Chart-managed:** enable `monitoring.prometheusRules.enabled` and
  `monitoring.serviceMonitor.enabled` (see [`values-day2.yaml`](../../deploy/k8s/chart/values-day2.yaml)).
- **Standalone:** apply [`deploy/k8s/prometheus-rules.yaml`](../../deploy/k8s/prometheus-rules.yaml)
  with Prometheus Operator.

| Alert | Runbook |
| --- | --- |
| `RepaveGenerationFailureRateHigh` | [Generation failures](#generation-failures) |
| `RepaveGenerationLatencyHigh` | [Slow generations](#slow-generations) |
| `RepaveAsyncRunFailureRateHigh` | [Generation failures](#generation-failures) |
| `RepaveAsyncRunDeadLetterRate` | [Generation failures](#generation-failures) |
| `RepaveRunQueueBacklogHigh` | [Scale out](#scale-out) |
| `RepaveJsonlAppendFailures` | [Stuck async queue](#stuck-async-queue) |
| `RepaveHPAAtMaxReplicas` | [Scale out](#scale-out) (requires kube-state-metrics) |

## Runbooks

### Node drain / rollout

1. Chart defaults: `maxUnavailable: 0`, PDB `minAvailable: 1`, `terminationGracePeriodSeconds: 120`.
2. `/readyz` fails while the pod drains (`shutting_down: true`); async runs finish during
   `REPAVE_SHUTDOWN_DRAIN_SECONDS` (default 105s).
3. `kubectl rollout status deployment/repave -n repave`

See [Upgrade and rollback](upgrade-and-rollback.md) for Helm steps.

### Scale out

1. Configure shared SQL durability (`repave.durability.databaseUrl`) and
   `secrets.sessionSecret` before `autoscaling.enabled` or `replicaCount` > 1.
2. For decomposed deploys, use `values-decomposed.yaml` with an external worker Deployment
   and Postgres; validate with `make chart-smoke-decomposed` or
   `make chart-smoke-multi-replica` when scaling portal replicas.
3. Watch HPA: `kubectl get hpa -n repave`
4. Dashboard: generation latency, CPU, and `repave_run_queue_inflight`.

### Upgrade / rollback

Follow [upgrade-and-rollback.md](upgrade-and-rollback.md): pre-upgrade `make chart-smoke`, pinned
digest, `helm upgrade --wait`, and `helm rollback`.

### Readiness failures

1. `kubectl exec` → `curl -s localhost:8088/readyz | jq` and inspect `checks`.
2. **`gate_tools: false`** — wrong image variant; use gate-toolchain build or `image.gateToolchain: true`.
3. **`runs_db_writable: false`** — PVC mount or permissions on `/data/runs`.
4. **`session_store: false`** — SQL session store unreachable when `databaseUrl` is set;
   verify Postgres connectivity and credentials.
5. **`github_api: false`** (when `REPAVE_READY_REQUIRE_GITHUB=1`) — PAT scope/expiry or
   GitHub App credentials; see [GitHub publish failures](#github-publish-failures) and
   [`docs/github-app-auth.md`](../github-app-auth.md).
6. **`session_secret: false`** — set `REPAVE_SESSION_SECRET` when auth or
   `durability.require_session_secret` is enabled.

### Generation failures

1. Check portal, `/api/v1/runs`, or audit JSONL for `gates_outcome=failed`.
2. Open the result gate excerpt or re-run with `--dry-run` via CLI.
3. Confirm gate tools exist in the image (`repave doctor --strict` in the container).
4. Replay dead-letter runs: `POST /api/v1/runs/{id}/replay` (admin).

### Slow generations

1. Inspect `/metrics` and [OpenTelemetry traces](../tracing.md) for stage timing.
2. Scale replicas or reduce concurrent Scaffolder/portal load.
3. Tune `durability.max_concurrent_runs` and HPA max replicas.

### OIDC / sign-in outage

1. Confirm IdP status and client secret rotation.
2. Fall back to read-only mode is **not** automatic — restore IdP or disable
   `auth.service_mode` only in break-glass (local open mode).

### GitHub publish failures

1. Verify PAT scopes and expiry, or GitHub App ID/installation ID/private key in the
   release Secret (`/readyz` reports presence; optional `github_api_reachable` when
   credentials are configured).
2. See rate-limit guidance in engine logs and [`docs/github-app-auth.md`](../github-app-auth.md).

### Stuck async queue

1. Check `repave_run_queue_inflight` and running pods' `/readyz`.
2. Avoid force-deleting pods during long runs; use graceful drain (see [Node drain](#node-drain--rollout)).
3. After infra failure, replay from dead letter via the runs API.

## Related

- [`docs/auth-service-mode.md`](../auth-service-mode.md) — OIDC and roles
- [`docs/github-app-auth.md`](../github-app-auth.md) — GitHub App vs PAT for publish
- [`docs/backstage.md`](../backstage.md) — Scaffolder and `POST /api/v1/generate`
- [`docs/durability.md`](../durability.md) — async runs and SQLite store
- [`crd-conversion-recovery.md`](crd-conversion-recovery.md) — operator CRD conversion drill
