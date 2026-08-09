#!/usr/bin/env bash
# Seed the hosted demo library via the portal pod (GitHub App auth — no laptop PAT).
# See docs/hosted-demo-library.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAMESPACE="${REPAVE_NAMESPACE:-repave}"
RELEASE="${REPAVE_RELEASE:-repave}"
OPERATOR_NS="${OPERATOR_NAMESPACE:-repave-system}"
MANIFESTS_DIR="${ROOT}/fleet-manifests"
TMP_PREFIX="/tmp/repave-demo-library"

pod="$(kubectl get pod -n "${NAMESPACE}" \
  -l "app.kubernetes.io/instance=${RELEASE},app.kubernetes.io/component=portal" \
  -o jsonpath='{.items[0].metadata.name}')"
if [[ -z "${pod}" ]]; then
  echo "No portal pod in namespace ${NAMESPACE} (release ${RELEASE})" >&2
  exit 1
fi

echo "Using portal pod ${NAMESPACE}/${pod} (GITHUB_APP_* from repave-secrets)"

phase="$(kubectl get pod -n "${NAMESPACE}" "${pod}" \
  -o jsonpath='{.status.phase}' 2>/dev/null || true)"
ready="$(kubectl get pod -n "${NAMESPACE}" "${pod}" \
  -o jsonpath='{.status.containerStatuses[?(@.name=="repave")].ready}' 2>/dev/null || true)"
if [[ "${phase}" != "Running" || "${ready}" != "true" ]]; then
  echo "Portal pod is not ready (phase=${phase:-unknown}, repave.ready=${ready:-unknown})." >&2
  echo "Recent logs:" >&2
  kubectl logs -n "${NAMESPACE}" "${pod}" -c repave --tail=25 2>&1 >&2 || true
  echo >&2
  echo "Common fix: OCI chart may lack databaseUrlSecret wiring — redeploy with:" >&2
  echo "  REPAVE_CHART_PATH=~/repave/deploy/k8s/chart ./scripts/sync-repave.sh" >&2
  exit 1
fi

kubectl exec -n "${NAMESPACE}" "${pod}" -- mkdir -p /data/fleet /data/modules "${TMP_PREFIX}"
kubectl cp "${ROOT}/scripts/hosted-demo-library.yaml" \
  "${NAMESPACE}/${pod}:${TMP_PREFIX}/hosted-demo-library.yaml"
kubectl cp "${ROOT}/scripts/seed_hosted_demo_library.py" \
  "${NAMESPACE}/${pod}:${TMP_PREFIX}/seed_hosted_demo_library.py"

seed_args=(
  python3 "${TMP_PREFIX}/seed_hosted_demo_library.py"
  --repo-root /app
  --catalog "${TMP_PREFIX}/hosted-demo-library.yaml"
  --modules-root /data/modules
  --fleet-file /data/fleet/registry.jsonl
  --engine-dir /app/engine
  --operator-namespace "${OPERATOR_NS}"
  --render-manifests
  --manifests-dir "${TMP_PREFIX}/fleet-manifests"
)
if [[ "${SEED_DRY_RUN:-}" == "1" ]]; then
  seed_args+=(--dry-run)
fi
if [[ "${SEED_SKIP_PUBLISH:-}" == "1" ]]; then
  seed_args+=(--skip-publish)
fi
if [[ "${SEED_SKIP_REGISTER:-}" == "1" ]]; then
  seed_args+=(--skip-register)
fi

if [[ "${SEED_CONTINUE_ON_ERROR:-}" == "1" ]]; then
  seed_args+=(--continue-on-error)
fi

kubectl exec -n "${NAMESPACE}" "${pod}" -- env -u GITHUB_TOKEN REPAVE_FORCE_GITHUB_APP=1 "${seed_args[@]}"

if [[ "${SEED_DRY_RUN:-}" == "1" ]]; then
  echo "Dry run complete (no manifests copied)."
  exit 0
fi

rm -rf "${MANIFESTS_DIR}"
mkdir -p "${MANIFESTS_DIR}"
kubectl cp "${NAMESPACE}/${pod}:${TMP_PREFIX}/fleet-manifests/." "${MANIFESTS_DIR}/"

if [[ "${SEED_APPLY_MANIFESTS:-}" == "1" ]]; then
  kubectl apply -k "${MANIFESTS_DIR}"
fi

if [[ "${SEED_SKIP_COST_SNAPSHOTS:-}" != "1" ]]; then
  kubectl cp "${ROOT}/scripts/seed_hosted_demo_cost_snapshots.py" \
    "${NAMESPACE}/${pod}:${TMP_PREFIX}/seed_hosted_demo_cost_snapshots.py"
  cost_args=(
    python3 "${TMP_PREFIX}/seed_hosted_demo_cost_snapshots.py"
    --repo-root /app
    --catalog "${TMP_PREFIX}/hosted-demo-library.yaml"
    --output /data/fleet/cost-snapshots.jsonl
  )
  if [[ "${SEED_DRY_RUN:-}" == "1" ]]; then
    cost_args+=(--dry-run)
  fi
  kubectl exec -n "${NAMESPACE}" "${pod}" -- "${cost_args[@]}"
fi

echo "Fleet registry on portal PVC: /data/fleet/registry.jsonl"
echo "Cost snapshots on portal PVC: /data/fleet/cost-snapshots.jsonl"
echo "GPR manifests: ${MANIFESTS_DIR} (kubectl apply -k when ready)"
