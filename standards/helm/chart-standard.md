# Helm chart standard v1.0.0

Version: 1.0.0

Governed Kubernetes Helm charts from the `helm-chart-generic` golden path.

## Naming

- Repository name: `helm-{chart_name}` (from blueprint).
- Chart `name` in `Chart.yaml` matches `chart_name` (lowercase, hyphenated).
- Kubernetes resource names use `Release.Name` and chart helpers (no hard-coded env names).

## Required chart files

| File | Purpose |
| --- | --- |
| `Chart.yaml` | Chart metadata and version |
| `values.yaml` | Default configuration |
| `templates/_helpers.tpl` | Naming and label helpers |
| `templates/deployment.yaml` | Workload |
| `templates/service.yaml` | ClusterIP/NodePort/LoadBalancer service |
| `templates/NOTES.txt` | Post-install notes |
| `README.md` | Usage and **Provenance** (repave lineage) |

Optional: `templates/ingress.yaml` when `enable_ingress` is true at generate time.

## Labels

All workloads MUST include standard labels from `_helpers.tpl`:

- `app.kubernetes.io/name`
- `app.kubernetes.io/instance`
- `helm.sh/chart`
- `repave.dev/owner`, `repave.dev/service`, `repave.dev/environment` (FinOps allocation — required via `values.owner`, `values.serviceName`, `values.environment`)

Optional: `values.costCenter` for chargeback metadata.

## Validation

Charts run `helm lint`, `helm template`, `yamllint`, `actionlint`, `secrets`, `docs-drift`, and
`provenance-drift` gates. Tools skip cleanly when not installed.

When `enable_deploy_pipeline` is true, generated repos include `repave-deploy.yml`, which opens
a GitOps promotion PR (v1.79 manifest bump) instead of running `helm upgrade` in CI. Operators
wire `REPAVE_GITOPS_APP_TOKEN` and environment protection once — see
`docs/operations/deploy-pipeline-oidc.md` in the repave monorepo.
