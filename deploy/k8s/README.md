# Kubernetes operability artifacts

Starter manifests for hosted repave (roadmap v1.35–v1.36). Install the engine with the
**Helm chart** under [`chart/`](chart/README.md), then wire these observability artifacts
into your overlay.

| Path | Purpose |
| --- | --- |
| [`chart/`](chart/README.md) | Helm chart: Deployment, HPA, PDB, probes, resources, Ingress |
| [`hack/kind-co-install.sh`](hack/kind-co-install.sh) | kind: portal + fleet registry + operator + `fleet-manifests` apply |
| `prometheus-rules.yaml` | Alert on generation failure rate and p95 latency |
| `grafana-dashboard-repave.json` | Dashboard for throughput and gate outcomes |

Health endpoints on the engine:

- `GET /health` — liveness
- `GET /readyz` — readiness (config loaded; reports `GITHUB_TOKEN` presence)
- `GET /metrics` — Prometheus scrape target

Enable service-mode auth and OIDC before exposing the portal on a shared cluster.
See [`docs/auth-service-mode.md`](../../docs/auth-service-mode.md).
