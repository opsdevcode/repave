#!/usr/bin/env bash
# kind smoke: build engine image, helm install chart, curl /health and catalog.
# Non-blocking in CI by default; run locally via: make chart-smoke
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke}"
NS="${CHART_SMOKE_NAMESPACE:-repave-smoke}"
IMG_REPO="${CHART_SMOKE_IMAGE_REPO:-repave-engine}"
IMG_TAG="${CHART_SMOKE_IMAGE_TAG:-chart-smoke}"
TIMEOUT="${CHART_SMOKE_TIMEOUT:-240}"

if ! command -v kind >/dev/null 2>&1; then
  echo "kind not found" >&2
  exit 1
fi
if ! command -v helm >/dev/null 2>&1; then
  echo "helm not found" >&2
  exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

cleanup() {
  if [[ "${CHART_SMOKE_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> kind cluster ${CLUSTER_NAME}"
kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}"

echo "==> docker build ${IMG_REPO}:${IMG_TAG}"
docker build -f "${ROOT}/deploy/local/Dockerfile" -t "${IMG_REPO}:${IMG_TAG}" "${ROOT}"

echo "==> kind load image"
kind load docker-image "${IMG_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"

echo "==> helm install"
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" --create-namespace \
  -f "${CHART}/values-kind.yaml" \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set repave.output.githubOrg=example-org \
  --wait --timeout "${TIMEOUT}s"

echo "==> port-forward and probe"
kubectl -n "${NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"
kubectl -n "${NS}" port-forward svc/repave 18088:8088 >/tmp/repave-chart-smoke-pf.log 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true; cleanup' EXIT
sleep 3

curl -sf "http://127.0.0.1:18088/health" | grep -q '"status":"ok"'
curl -sf "http://127.0.0.1:18088/readyz" | grep -q '"status":"ready"'
curl -sf "http://127.0.0.1:18088/" | grep -qi 'catalog\|blueprint\|repave'

echo "OK: chart smoke passed"
