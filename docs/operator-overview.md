# Operator overview

Kubernetes controller for **estate drift and blueprint upgrades** (alpha; v1.17
slices). Generation does not require the operator; use it when many module repos
must stay aligned with catalog pin changes.

Local development: [operator-local-dev.md](operator-local-dev.md) · GA scope:
[operator-ga.md](operator-ga.md)

## Capabilities

| Capability | CRD / API | Notes |
| --- | --- | --- |
| Inventory | `GoldenPathRepo` | Read `repave.yaml` from `spec.localPath`; `status.observedPins` |
| Drift detection | `GoldenPathRepo` status | `OutOfDate` when observed ≠ desired pins |
| Upgrade diff | `status.upgradePlan` | `repave plan-upgrade` contract |
| Remediation PR | `spec.remediation` | `repave apply-upgrade` + GitHub client; dry-run without token |
| Catalog pin watch | `Blueprint` + `spec.blueprintRef` | Reconcile GPRs when Blueprint pins change |

`spec.repoURL` (git clone inventory) is not implemented yet; use `localPath` for
dev and envtest.

## Engine vs operator

```text
Generation:  form/API  →  render  →  gates  →  new module repo

Operator:    GoldenPathRepo  →  observe repave.yaml  →  upgrade plan  →  remediation PR
             Blueprint       →  watch blueprintRef ────────────────┘
```

Package layout: [`operator/`](../operator/)
