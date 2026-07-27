# Observability standards

| Standard | Version | Golden path |
| --- | --- | --- |
| [dashboards-as-code.md](dashboards-as-code.md) | 1.2.0 | `dashboards-as-code-generic` (Grafana + Datadog dashboards) |
| [monitors-as-code.md](monitors-as-code.md) | 1.1.0 | `monitors-as-code-generic` (Datadog + Prometheus monitors) |
| [observability-as-code.md](observability-as-code.md) | 1.3.0 | `observability-as-code-generic` (umbrella / multi-backend; prefer split paths for new repos) |
| [service-registry.md](service-registry.md) | 1.0.0 | Portal service inventory + catalog merge |

All paths share notification and pack catalog entries under `observability/catalog.json` at
the repo root.
