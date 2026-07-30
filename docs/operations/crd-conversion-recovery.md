# CRD conversion webhook — recovery drill

Use this drill in a **non-production** cluster before upgrading the operator to a release
that stores `GoldenPathRepo` and `Blueprint` as **`repave.dev/v1beta1`**.

Automated proof: `make operator-e2e` runs the same checks via
[`operator/hack/assert-crd-conversion.sh`](../../operator/hack/assert-crd-conversion.sh).

## Objective

- v1alpha1 manifests continue to apply while etcd stores v1beta1
- A temporary webhook outage is detectable and recoverable without object loss
- Recovery time: **&lt; 15 minutes** (redeploy operator + re-inject CRD `caBundle`)

## Prerequisites

- kind cluster or staging namespace with operator e2e layout (`repave-system`)
- `openssl`, `kubectl`, operator image, and patched CRDs from
  [`operator/hack/setup-webhook-certs.sh`](../../operator/hack/setup-webhook-certs.sh) +
  [`operator/hack/inject-crd-ca-bundle.sh`](../../operator/hack/inject-crd-ca-bundle.sh)

## 1. Baseline conversion (no data loss)

```bash
cd operator
bash hack/setup-webhook-certs.sh
crd_tmp="$(mktemp -d)"
bash hack/inject-crd-ca-bundle.sh hack/webhook-certs/ca.crt config/crd/bases "${crd_tmp}"
kubectl apply -f "${crd_tmp}/"
kubectl apply -f config/e2e/webhook-service.yaml
kubectl apply -f config/e2e/manager.yaml

kubectl apply -f config/e2e/goldenpathrepo-drift.yaml
ROOT="$(pwd)" bash hack/assert-crd-conversion.sh
```

Expected: CRD storage version `v1beta1`; raw GET at `/apis/repave.dev/v1beta1/.../e2e-drift`
returns `apiVersion: repave.dev/v1beta1`.

## 2. Simulate webhook failure

Scale the operator Deployment to zero (webhook and reconciler share the manager pod):

```bash
kubectl -n repave-system scale deployment/repave-operator --replicas=0
kubectl -n repave-system wait --for=delete pod -l app=repave-operator --timeout=120s
```

Apply a **new** v1alpha1 object (or patch an existing one). Expect the API server to reject
the write with a conversion error while the webhook is unreachable.

## 3. Recovery

```bash
kubectl -n repave-system scale deployment/repave-operator --replicas=1
kubectl -n repave-system rollout status deployment/repave-operator --timeout=180s
ROOT="$(pwd)" bash hack/assert-crd-conversion.sh
kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.phase}{"\n"}'
```

Expected: conversion succeeds again; existing `e2e-drift` status is unchanged (no spec wipe).

## 4. Rollback (break-glass)

If conversion cannot be restored, reinstall the previous operator release whose CRDs served
**v1alpha1 as storage** (no conversion block). See
[`docs/operator-crd-v1beta1-migration.md`](../operator-crd-v1beta1-migration.md#rollback).

## Record the drill

Log date, cluster, operator image tag, and pass/fail for steps 1–3 in your change record or
release checklist. CI runs step 1 on every operator e2e workflow.

## Related

- [`docs/operator-crd-v1beta1-migration.md`](../operator-crd-v1beta1-migration.md)
- [`docs/operator-standards.md`](../operator-standards.md)
- [`operator/config/e2e/`](../operator/config/e2e/)
