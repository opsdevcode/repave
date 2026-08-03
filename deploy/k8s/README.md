# Kubernetes operability artifacts

Starter manifests and chart hooks for hosted repave (roadmap v1.35–v1.38). Install the
engine with the **Helm chart** under [`chart/`](chart/README.md), then wire observability
via chart values or standalone manifests.

| Path | Purpose |
| --- | --- |
| [`chart/`](chart/README.md) | Helm chart: Deployment, HPA, PDB, probes, resources, Ingress |
| [`chart/values-day2.yaml`](chart/values-day2.yaml) | Production overlay: HPA, ServiceMonitor, PrometheusRule, session/GitHub readiness |
| [`chart/values-decomposed.yaml`](chart/values-decomposed.yaml) | Decomposed portal + worker + corpus (Phase 2) |
| [`chart/values-decomposed-day2.yaml`](chart/values-decomposed-day2.yaml) | Recommended hosted production: decomposed + day-2 operability |
| [`chart/values-environment-vending.yaml`](chart/values-environment-vending.yaml) | Environment vending registry PVC + TTL reclaim CronJob |
| [`chart/values-fleet-shared.yaml`](chart/values-fleet-shared.yaml) | Shared fleet registry PVC + operator snapshot CronJob for platform console |
| [`chart/values-digest-pinned.yaml`](chart/values-digest-pinned.yaml) | Supply-chain overlay: pin portal/worker/corpus by digest |
| [`chart/values-multi-replica-smoke.yaml`](chart/values-multi-replica-smoke.yaml) | CI overlay: two portal replicas on shared Postgres |
| [`hack/kind-co-install.sh`](hack/kind-co-install.sh) | kind: portal + fleet registry + operator fleetSync + drift fixture |
| [`chart/templates/servicemonitor.yaml`](chart/templates/servicemonitor.yaml) | Optional Prometheus Operator scrape (when `monitoring.serviceMonitor.enabled`) |
| [`chart/templates/prometheusrules.yaml`](chart/templates/prometheusrules.yaml) | Optional alert rules (when `monitoring.prometheusRules.enabled`) |
| `prometheus-rules.yaml` | Standalone alert pack (same rules as chart template; no Prometheus Operator chart required) |
| `grafana-dashboard-repave.json` | Dashboard: generation throughput, latency, async queue, run outcomes |

Health endpoints on the engine:

- `GET /health` — liveness
- `GET /readyz` — readiness (`checks`: writable paths, gate tools when `REPAVE_IMAGE_GATE_TOOLCHAIN=1`,
  optional GitHub API, fails with 503 while draining for shutdown)
- `GET /metrics` — Prometheus scrape target

Enable service-mode auth and OIDC before exposing the portal on a shared cluster.
See [`docs/auth-service-mode.md`](../../docs/auth-service-mode.md).
