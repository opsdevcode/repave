# Observability standards

| Standard | Version | Golden path |
| --- | --- | --- |
| [observability-as-code.md](observability-as-code.md) | 1.2.0 | `observability-as-code-generic` (alerts / multi-backend) |
| [dashboards-as-code.md](dashboards-as-code.md) | 1.2.0 | `dashboards-as-code-generic` (Grafana + Datadog dashboards) |
| [service-registry.md](service-registry.md) | 1.0.0 | Portal service inventory + catalog merge |

Both paths share notification catalog entries under `observability/catalog.json` at
the repo root.
