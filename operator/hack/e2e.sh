#!/usr/bin/env bash
# kind e2e: deploy operator image, apply drift fixture, assert status.phase=OutOfDate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-local}"
IMG="${IMG:-repave-operator:dev}"
TIMEOUT_SEC="${E2E_TIMEOUT_SEC:-120}"
KIND_BIN="${KIND_BIN:-kind}"

if ! command -v "${KIND_BIN}" >/dev/null 2>&1; then
  echo "kind not found; install with: go install sigs.k8s.io/kind@v0.27.0" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required for operator e2e" >&2
  exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required for operator e2e" >&2
  exit 1
fi

cleanup() {
  if [[ "${E2E_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "E2E_KEEP_CLUSTER=1; leaving kind cluster ${CLUSTER_NAME}"
    return 0
  fi
  "${KIND_BIN}" delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Creating kind cluster ${CLUSTER_NAME}"
"${KIND_BIN}" delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
# Resolve modules mount to an absolute path for kind.
MODULES_HOST="${ROOT}/testdata/modules"
tmp_kind_cfg="$(mktemp)"
sed "s|hostPath: ./testdata/modules|hostPath: ${MODULES_HOST}|" \
  "${ROOT}/hack/kind-config.yaml" >"${tmp_kind_cfg}"
"${KIND_BIN}" create cluster --name "${CLUSTER_NAME}" --config "${tmp_kind_cfg}"
rm -f "${tmp_kind_cfg}"

echo "==> Building operator image ${IMG}"
docker build -t "${IMG}" .

echo "==> Loading image into kind"
"${KIND_BIN}" load docker-image "${IMG}" --name "${CLUSTER_NAME}"

echo "==> Applying CRDs and e2e manifests"
kubectl apply -f config/crd/bases/
kubectl apply -f config/e2e/namespace.yaml
kubectl apply -f config/e2e/rbac.yaml
kubectl apply -f config/e2e/manager.yaml

echo "==> Waiting for operator Deployment"
kubectl -n repave-system rollout status deployment/repave-operator --timeout="${TIMEOUT_SEC}s"

echo "==> Applying drift GoldenPathRepo fixture"
kubectl apply -f config/e2e/goldenpathrepo-drift.yaml

echo "==> Waiting for status.phase=OutOfDate"
deadline=$((SECONDS + TIMEOUT_SEC))
phase=""
while (( SECONDS < deadline )); do
  phase="$(kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.phase}' 2>/dev/null || true)"
  if [[ "${phase}" == "OutOfDate" ]]; then
    echo "OK: GoldenPathRepo e2e-drift is OutOfDate"
    kubectl get goldenpathrepo e2e-drift -o yaml
    exit 0
  fi
  sleep 2
done

echo "Timed out after ${TIMEOUT_SEC}s waiting for OutOfDate (last phase=${phase:-<empty>})" >&2
kubectl -n repave-system get pods -o wide || true
kubectl -n repave-system logs deploy/repave-operator --tail=80 || true
kubectl get goldenpathrepo e2e-drift -o yaml || true
exit 1
