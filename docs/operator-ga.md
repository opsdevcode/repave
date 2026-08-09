# Operator GA scope (v1.17)

This document records what **general availability** means for the repave operator
today and what remains intentionally out of scope.

## GA capabilities

| Area | Status | Notes |
| --- | --- | --- |
| CRDs | GA | `GoldenPathRepo`, `Blueprint` — **`repave.dev/v1beta1` storage**; `v1alpha1` served with conversion webhook |
| Inventory / drift | GA | `spec.localPath` or `spec.repoURL` (shallow clone) reads `repave.yaml` pins vs desired; missing `repave.yaml` sets `Ready=False` with reason **`ProvenanceMissing`** (no drift/remediation until fixed) |
| Remote remediation | GA | `spec.repoURL` + token: apply-upgrade and PR from the inventory clone ([ADR 001](adr/001-goldenpathrepo-repo-url-inventory.md)) |
| Upgrade planning | GA | `POST /api/v2/upgrades/plan` when `REPAVE_API_URL` is set; local dev may still use `repave plan-upgrade` CLI |
| Remediation | GA | `POST /api/v2/upgrades/apply`, optional GitHub PR, `preserveLocal` |
| Blueprint pin watch | GA | `spec.blueprintRef` reconciles when catalog pins change |
| Local verification | GA | `make operator-test`, `make operator-e2e` (kind, conversion + HTTP operator, no production GitHub) |
| CI | GA | `operator-test` on PRs; `operator-e2e` nightly, on `main` operator changes, and `workflow_dispatch` |

## Out of scope for GA

| Area | Target | Notes |
| --- | --- | --- |
| Multi-tenant fleet API | v2 | Single-cluster inventory per operator instance |
| In-cluster notifications | Optional | Webhooks via `REPAVE_OPERATOR_NOTIFY_*` (see operator README) |

## GA checklist (maintainers)

Last verified on **`main`**: 2026-07-30 (engine **v2.46.0**).

- [x] `make operator-test` and `make operator-e2e` pass on `main`
- [x] Sample manifests under `operator/config/e2e/` match blueprint pins on `main`
- [x] `operator/README.md` and [`operator-local-dev.md`](operator-local-dev.md) match controller behavior
- [x] CRD conversion: v1alpha1 apply stores v1beta1 (`operator/hack/assert-crd-conversion.sh`)
- [ ] Breaking CRD changes follow [`operator-standards.md`](operator-standards.md) and release notes

### E2E fixture contract

| Source | Role |
| --- | --- |
| `operator/testdata/modules/terraform-minimal/repave.yaml` | **Observed** pins: blueprint `terraform-module-generic@0.9.0`, standard `standards/terraform-standards@1.1.0` (fixture stays behind catalog on purpose). |
| `operator/config/e2e/goldenpathrepo-drift.yaml` | **Desired** blueprint `9.9.9` forces `OutOfDate`; standard fields match the fixture. |
| `operator/config/e2e/blueprint-conversion.yaml` | v1alpha1 **Blueprint** fixture; e2e asserts storage as v1beta1. |
| Catalog `blueprints/terraform-module-generic/blueprint.yaml` | **Current** blueprint version is what `repave plan-upgrade` targets in `status.upgradePlan` (asserted in `operator/hack/e2e.sh`). |

When bumping the terraform-module-generic blueprint or standard pins, update the fixture README and any envtest assertions; keep e2e **desired** blueprint ahead of **observed** (see [`operator/README.md`](../operator/README.md#baseline-from-generation-v114)).

## Related

- [`operator/README.md`](../operator/README.md)
- [`roadmap.md`](roadmap.md) — v1.17 reconciliation operator
