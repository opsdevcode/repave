# CRD v1beta1 migration

`GoldenPathRepo` and `Blueprint` are stored in etcd as **`repave.dev/v1beta1`**. The
operator continues to **serve** `repave.dev/v1alpha1` and converts through a webhook at
`/convert` (same manager pod as the reconciler).

## New installs

Use **`repave.dev/v1beta1`** in manifests and in `repave fleet-manifests` output (default
since the current engine release). Apply the operator CRDs and ensure the conversion webhook Service and
TLS secret are installed (`operator/config/e2e/` and `operator/hack/setup-webhook-certs.sh`
show the kind/e2e layout).

## Existing v1alpha1 manifests

You do **not** need to rewrite YAML immediately. The API server accepts
`apiVersion: repave.dev/v1alpha1` and stores the object as v1beta1 when the conversion
webhook is reachable.

To migrate GitOps repos explicitly:

```bash
kubectl get goldenpathrepo -A -o yaml | \
  sed 's|apiVersion: repave.dev/v1alpha1|apiVersion: repave.dev/v1beta1|g' > /tmp/gpr-v1beta1.yaml
# Review /tmp/gpr-v1beta1.yaml, then apply or commit the updated apiVersion only.
```

Repeat for `Blueprint` resources. **Spec and status field names are unchanged** between
v1alpha1 and v1beta1 — only the apiVersion string changes.

## Verify conversion

After upgrading the operator and CRDs:

```bash
# Apply a v1alpha1 fixture (e2e drift uses this path)
kubectl apply -f operator/config/e2e/goldenpathrepo-drift.yaml

# Stored version should be v1beta1
kubectl get goldenpathrepo e2e-drift -o jsonpath='{.apiVersion}{"\n"}'
# repave.dev/v1beta1
```

## Rollback

If the webhook is unavailable, CRD writes for v1alpha1 fail with conversion errors. Keep
the webhook Service, TLS secret, and manager webhook port (9443) aligned with
`operator/config/e2e/webhook-service.yaml`. To roll back CRDs, reinstall the previous
operator release that served v1alpha1 as the storage version (no conversion block).

See also [`docs/operator-standards.md`](operator-standards.md) and
[`docs/roadmap.md`](roadmap.md) (Phase 3d).
