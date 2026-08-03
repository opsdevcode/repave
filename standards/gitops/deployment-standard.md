# GitOps deployment standard v1.0.0

Version: 1.0.0

Governed Argo CD and Flux deployment manifests from the `gitops-deployment-generic` golden path.
One repository describes one service in one environment, so a promotion is a reviewable commit
in exactly one place.

## Naming

- Repository name: `gitops-{environment}-{service_name}` (from blueprint).
- Manifest `metadata.name` is `{service_name}-{environment}` so a cluster hosting several
  environments never collides.
- The target namespace is explicit; it is never inherited from the tool's default.

## Required files

| File | Purpose |
| --- | --- |
| `apps/release.yaml` | Argo CD `Application` or Flux `HelmRelease` |
| `README.md` | Usage and **Provenance** (repave lineage) |
| `repave.yaml` | Generation provenance |
| `.yamllint` | Lint configuration for the manifest |

Flux repositories also carry `apps/kustomization.yaml` so the manifest is reachable from a
cluster-level `Kustomization`.

## Pinning

Floating references are the failure this path exists to prevent.

- `chart_version` MUST be an exact semantic version. `HEAD`, `latest`, `*`, and range
  specifiers are rejected by the `opa` gate.
- `chart_repo_url` MUST be an absolute `https://` or `oci://` URL.
- Argo CD `targetRevision` carries the chart version, never a branch name.
- Flux `HelmRelease.spec.chart.spec.version` carries the same value, and its
  `sourceRef` names a `HelmRepository` that already exists in the cluster.

## Sync policy

`sync_policy` is an explicit decision recorded in provenance, not a default:

- `manual` — Argo CD omits `syncPolicy.automated`; Flux sets `suspend: false` with no
  automated image or chart upgrade. A human promotes by merging a version bump.
- `automated` — Argo CD sets `syncPolicy.automated` with **both** `prune` and `selfHeal`
  declared explicitly; Flux enables remediation with a bounded retry count.

Automated sync without an explicit prune and self-heal decision is rejected by the `opa` gate,
because silently defaulting either one changes what happens to resources a developer deletes.

## Scoping

- Argo CD manifests MUST set `spec.project`; the implicit `default` project is rejected.
- Argo CD manifests MUST set `spec.destination.server` and `spec.destination.namespace`.
- Flux manifests MUST set `spec.targetNamespace` and `spec.storageNamespace`.

## Validation

Manifests run `yamllint`, `opa`, `secrets`, `docs-drift`, and `provenance-drift` gates. Tools
skip cleanly when not installed.

Rendering the referenced chart (`helm-template` against `chart_repo_url`) is **not** part of
this standard yet — it needs network access to the chart repository from the gate runner. Until
that lands, the `opa` gate enforces the pin and sync rules on the manifest itself.
