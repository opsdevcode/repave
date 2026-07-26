#!/usr/bin/env bash
# kind e2e: deploy operator image (with repave CLI), apply drift fixture, assert
# OutOfDate + UpgradePlanned + non-empty upgradePlan.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONOREPO_ROOT="$(cd "${ROOT}/.." && pwd)"
cd "${ROOT}"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-local}"
IMG="${IMG:-repave-operator:dev}"
TIMEOUT_SEC="${E2E_TIMEOUT_SEC:-180}"
KIND_BIN="${KIND_BIN:-kind}"
DOCKERFILE="${OPERATOR_E2E_DOCKERFILE:-${ROOT}/Dockerfile.e2e}"

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
MODULES_HOST="${ROOT}/testdata/modules"
tmp_kind_cfg="$(mktemp)"
sed "s|hostPath: ./testdata/modules|hostPath: ${MODULES_HOST}|" \
  "${ROOT}/hack/kind-config.yaml" >"${tmp_kind_cfg}"
"${KIND_BIN}" create cluster --name "${CLUSTER_NAME}" --config "${tmp_kind_cfg}"
rm -f "${tmp_kind_cfg}"

echo "==> Building operator e2e image ${IMG} (repave CLI bundled)"
docker build -f "${DOCKERFILE}" -t "${IMG}" "${MONOREPO_ROOT}"

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

wait_gpr_field() {
  local jsonpath="$1"
  local expected="$2"
  local label="$3"
  local deadline=$((SECONDS + TIMEOUT_SEC))
  local value=""
  while (( SECONDS < deadline )); do
    value="$(kubectl get goldenpathrepo e2e-drift -o "jsonpath=${jsonpath}" 2>/dev/null || true)"
    if [[ "${value}" == "${expected}" ]]; then
      echo "OK: ${label} (${value})"
      return 0
    fi
    sleep 2
  done
  echo "Timed out after ${TIMEOUT_SEC}s waiting for ${label} (last=${value:-<empty>}, want=${expected})" >&2
  return 1
}

echo "==> Waiting for status.phase=OutOfDate"
wait_gpr_field '{.status.phase}' 'OutOfDate' 'status.phase'

echo "==> Waiting for UpgradePlanned=True"
deadline=$((SECONDS + TIMEOUT_SEC))
planned=""
while (( SECONDS < deadline )); do
  planned="$(kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.conditions[?(@.type=="UpgradePlanned")].status}' 2>/dev/null || true)"
  if [[ "${planned}" == "True" ]]; then
    echo "OK: condition UpgradePlanned=True"
    break
  fi
  sleep 2
done
if [[ "${planned}" != "True" ]]; then
  echo "Timed out waiting for UpgradePlanned=True (last=${planned:-<empty>})" >&2
  kubectl -n repave-system logs deploy/repave-operator --tail=120 || true
  kubectl get goldenpathrepo e2e-drift -o yaml || true
  exit 1
fi

changed="$(kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.upgradePlan.changedFileCount}' 2>/dev/null || true)"
if [[ -z "${changed}" ]] || [[ "${changed}" -lt 1 ]]; then
  echo "Expected status.upgradePlan.changedFileCount >= 1 (got ${changed:-<empty>})" >&2
  kubectl get goldenpathrepo e2e-drift -o yaml || true
  exit 1
fi
echo "OK: upgradePlan.changedFileCount=${changed}"

kubectl get goldenpathrepo e2e-drift -o yaml
