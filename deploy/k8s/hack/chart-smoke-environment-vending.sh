#!/usr/bin/env bash
# kind smoke: environment vending overlay (environments PVC + reclaim CronJob).
# Exercises dry-run reclaim via HTTP and a one-off CronJob run.
# CI: .github/workflows/chart.yml (chart-smoke-environment-vending job).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke-env-vending}"
NS="${CHART_SMOKE_ENV_VENDING_NAMESPACE:-repave-env-vending-smoke}"
IMG_REPO="${CHART_SMOKE_ENV_VENDING_IMAGE_REPO:-repave-engine}"
IMG_TAG="${CHART_SMOKE_ENV_VENDING_IMAGE_TAG:-chart-smoke-env-vending}"
INSTALL_GATE_TOOLCHAIN="${CHART_SMOKE_INSTALL_GATE_TOOLCHAIN:-0}"
TIMEOUT="${CHART_SMOKE_ENV_VENDING_TIMEOUT:-300}"
PORT="${CHART_SMOKE_ENV_VENDING_PORT:-18090}"

require() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required" >&2
    exit 1
  fi
}

require kind
require helm
require docker
require kubectl
require curl
require python3

cleanup() {
  if [[ "${CHART_SMOKE_ENV_VENDING_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_ENV_VENDING_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> kind cluster ${CLUSTER_NAME}"
kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}"

echo "==> docker build ${IMG_REPO}:${IMG_TAG}"
docker build -f "${ROOT}/deploy/local/Dockerfile" \
  --build-arg "INSTALL_GATE_TOOLCHAIN=${INSTALL_GATE_TOOLCHAIN}" \
  -t "${IMG_REPO}:${IMG_TAG}" "${ROOT}"

echo "==> kind load image"
kind load docker-image "${IMG_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"

echo "==> helm install (environment vending overlay)"
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" --create-namespace \
  -f "${CHART}/values-kind.yaml" \
  -f "${CHART}/values-environment-vending.yaml" \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set repave.output.githubOrg=example-org \
  --set environmentReclaim.cronJob.dryRun=true \
  --set persistence.modules.enabled=false \
  --set persistence.modules.kindHostPath="" \
  --wait --timeout "${TIMEOUT}s"

CRONJOB="repave-environment-reclaim"
PVC="repave-environments"

echo "==> verify CronJob and environments PVC"
kubectl -n "${NS}" get "cronjob/${CRONJOB}"
kubectl -n "${NS}" get "pvc/${PVC}"

echo "==> port-forward and probe reclaim API (dry-run)"
kubectl -n "${NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"
kubectl -n "${NS}" port-forward svc/repave "${PORT}:8088" >/tmp/repave-env-vending-smoke-pf.log 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true; cleanup' EXIT
sleep 3

curl -sf "http://127.0.0.1:${PORT}/health" | grep -q '"status":"ok"'

reclaim_body="$(curl -sf -X POST "http://127.0.0.1:${PORT}/api/v2/environments/reclaim" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true}')"
python3 -c "import json,sys; body=json.loads(sys.argv[1]); assert body.get('count', -1) == 0" "${reclaim_body}"

echo "==> run one-off reclaim job from CronJob"
job_name="env-reclaim-smoke-$(date +%s)"
kubectl -n "${NS}" create job --from="cronjob/${CRONJOB}" "${job_name}"
kubectl -n "${NS}" wait --for=condition=complete "job/${job_name}" --timeout="${TIMEOUT}s"

echo "OK: environment vending chart smoke passed"
