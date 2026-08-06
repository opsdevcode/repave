#!/usr/bin/env bash
# kind smoke: build engine image, helm install chart, curl /health and catalog.
# CI: .github/workflows/chart.yml (required check; path-gated skip on unrelated PRs).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke}"
NS="${CHART_SMOKE_NAMESPACE:-repave-smoke}"
IMG_REPO="${CHART_SMOKE_IMAGE_REPO:-repave-engine}"
IMG_TAG="${CHART_SMOKE_IMAGE_TAG:-chart-smoke}"
INSTALL_GATE_TOOLCHAIN="${CHART_SMOKE_INSTALL_GATE_TOOLCHAIN:-1}"
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

echo "==> docker build ${IMG_REPO}:${IMG_TAG} (INSTALL_GATE_TOOLCHAIN=${INSTALL_GATE_TOOLCHAIN})"
docker build -f "${ROOT}/deploy/local/Dockerfile" \
  --build-arg "INSTALL_GATE_TOOLCHAIN=${INSTALL_GATE_TOOLCHAIN}" \
  -t "${IMG_REPO}:${IMG_TAG}" "${ROOT}"

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
  --set persistence.modules.kindHostPath="" \
  --wait --timeout "${TIMEOUT}s"

echo "==> port-forward and probe"
kubectl -n "${NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"
kubectl -n "${NS}" port-forward svc/repave 18088:8088 >/tmp/repave-chart-smoke-pf.log 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true; cleanup' EXIT

# Capture curl body before grep: with pipefail, `curl | grep -q` can exit 23
# (SIGPIPE) when grep matches early while curl is still writing.
probe_match() {
  local url="$1" pattern="$2"
  local body
  body="$(curl -sf "${url}")"
  grep -qiE "${pattern}" <<<"${body}"
}

for attempt in 1 2 3 4 5; do
  if probe_match "http://127.0.0.1:18088/health" '"status":"ok"' \
    && probe_match "http://127.0.0.1:18088/readyz" '"status":"ready"' \
    && probe_match "http://127.0.0.1:18088/" 'catalog|blueprint|repave'; then
    echo "OK: chart smoke passed"
    exit 0
  fi
  if [[ "${attempt}" -eq 5 ]]; then
    echo "portal probes failed after port-forward" >&2
    cat /tmp/repave-chart-smoke-pf.log >&2 || true
    exit 1
  fi
  sleep 2
done
