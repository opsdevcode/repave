#!/usr/bin/env bash
# kind smoke: decomposed portal (no gates) + worker Deployment + Postgres queue.
# Submits a dry-run async run and waits for worker completion.
# CI: .github/workflows/chart.yml (chart-smoke-decomposed job).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke-decomposed}"
NS="${CHART_SMOKE_DECOMPOSED_NAMESPACE:-repave-decomposed-smoke}"
PORTAL_REPO="${CHART_SMOKE_PORTAL_REPO:-repave-portal}"
WORKER_REPO="${CHART_SMOKE_WORKER_REPO:-repave-worker}"
CORPUS_REPO="${CHART_SMOKE_CORPUS_REPO:-repave-corpus}"
IMG_TAG="${CHART_SMOKE_DECOMPOSED_TAG:-chart-smoke-decomposed}"
TIMEOUT="${CHART_SMOKE_DECOMPOSED_TIMEOUT:-420}"
PORT="${CHART_SMOKE_DECOMPOSED_PORT:-18089}"

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
  if [[ "${CHART_SMOKE_DECOMPOSED_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_DECOMPOSED_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}

wait_rollout() {
  local deployment="$1"
  kubectl -n "${NS}" rollout status "deployment/${deployment}" --timeout="${TIMEOUT}s"
}

wait_run_terminal() {
  local run_id="$1"
  local deadline=$((SECONDS + TIMEOUT))
  local status=""
  while (( SECONDS < deadline )); do
    status="$(curl -sf "http://127.0.0.1:${PORT}/api/v1/runs/${run_id}" | python3 -c "import json,sys; print(json.load(sys.stdin)['status'])")"
    if [[ "${status}" == "succeeded" ]]; then
      echo "OK: run ${run_id} status=succeeded"
      return 0
    fi
    if [[ "${status}" == "failed" || "${status}" == "dead_letter" ]]; then
      echo "run ${run_id} ended with status=${status}" >&2
      curl -sf "http://127.0.0.1:${PORT}/api/v1/runs/${run_id}" >&2 || true
      kubectl -n "${NS}" logs "deployment/repave-worker" --tail=120 >&2 || true
      return 1
    fi
    sleep 4
  done
  echo "Timed out after ${TIMEOUT}s waiting for run ${run_id} (last status=${status:-<empty>})" >&2
  kubectl -n "${NS}" get pods >&2
  kubectl -n "${NS}" logs "deployment/repave-worker" --tail=120 >&2 || true
  return 1
}

trap cleanup EXIT

echo "==> kind cluster ${CLUSTER_NAME}"
kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
kind create cluster --name "${CLUSTER_NAME}"

echo "==> docker build portal ${PORTAL_REPO}:${IMG_TAG} (no gate toolchain)"
docker build -f "${ROOT}/deploy/local/Dockerfile" \
  --build-arg "INSTALL_GATE_TOOLCHAIN=0" \
  -t "${PORTAL_REPO}:${IMG_TAG}" "${ROOT}"

echo "==> docker build worker ${WORKER_REPO}:${IMG_TAG} (gate toolchain)"
docker build -f "${ROOT}/deploy/local/Dockerfile" \
  --build-arg "INSTALL_GATE_TOOLCHAIN=1" \
  -t "${WORKER_REPO}:${IMG_TAG}" "${ROOT}"

echo "==> docker build corpus ${CORPUS_REPO}:${IMG_TAG}"
docker build -f "${ROOT}/deploy/local/Dockerfile.corpus" \
  -t "${CORPUS_REPO}:${IMG_TAG}" "${ROOT}"

echo "==> kind load images"
kind load docker-image "${PORTAL_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"
kind load docker-image "${WORKER_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"
kind load docker-image "${CORPUS_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"

echo "==> postgres fixture in ${NS}"
kubectl create namespace "${NS}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NS}" apply -f "${ROOT}/deploy/k8s/hack/postgres-kind.yaml"
wait_rollout postgres

echo "==> helm install decomposed chart"
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  --set image.repository="${PORTAL_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set workerImage.repository="${WORKER_REPO}" \
  --set workerImage.tag="${IMG_TAG}" \
  --set corpus.repository="${CORPUS_REPO}" \
  --set corpus.tag="${IMG_TAG}" \
  --set repave.output.githubOrg=example-org \
  --wait --timeout "${TIMEOUT}s"

echo "==> wait for portal and worker"
wait_rollout repave
wait_rollout repave-worker

if kubectl -n "${NS}" get deployment repave-worker >/dev/null 2>&1; then
  echo "OK: worker Deployment present"
else
  echo "missing worker Deployment repave-worker" >&2
  exit 1
fi

if kubectl -n "${NS}" get deployment repave -o yaml | grep -q 'repave.dev/gate-toolchain: "false"'; then
  echo "OK: portal pod labeled gate-toolchain=false"
else
  echo "portal must run without gate toolchain in decomposed smoke" >&2
  exit 1
fi

echo "==> port-forward portal"
kubectl -n "${NS}" port-forward "svc/repave" "${PORT}:8088" >/tmp/repave-chart-smoke-decomposed-pf.log 2>&1 &
PF_PID=$!
trap 'kill "${PF_PID}" 2>/dev/null || true; cleanup' EXIT
sleep 4

for attempt in 1 2 3 4 5; do
  if curl -sf "http://127.0.0.1:${PORT}/health" | grep -q '"status":"ok"' \
    && curl -sf "http://127.0.0.1:${PORT}/readyz" | grep -q '"status":"ready"'; then
    break
  fi
  if [[ "${attempt}" -eq 5 ]]; then
    echo "portal health/readyz probes failed after port-forward" >&2
    cat /tmp/repave-chart-smoke-decomposed-pf.log >&2 || true
    exit 1
  fi
  sleep 2
done

echo "==> enqueue dry-run async run"
submit_json="$(curl -sf -X POST "http://127.0.0.1:${PORT}/api/v1/runs" \
  -H 'Content-Type: application/json' \
  -d '{
    "blueprint": "terraform-module-generic",
    "dry_run": true,
    "inputs": {
      "module_name": "chart-smoke-demo",
      "description": "decomposed chart smoke",
      "cloud_provider": "aws",
      "provider_services": "ec2,s3"
    }
  }')"
run_id="$(printf '%s' "${submit_json}" | python3 -c "import json,sys; print(json.load(sys.stdin)['run_id'])")"
echo "OK: enqueued run_id=${run_id}"

wait_run_terminal "${run_id}"

gates_passed="$(curl -sf "http://127.0.0.1:${PORT}/api/v1/runs/${run_id}" | python3 -c "import json,sys; r=json.load(sys.stdin); print('ok' if r.get('result',{}).get('gates_passed') else 'fail')")"
if [[ "${gates_passed}" != "ok" ]]; then
  echo "expected gates_passed=True in run result" >&2
  curl -sf "http://127.0.0.1:${PORT}/api/v1/runs/${run_id}" >&2
  exit 1
fi

echo "OK: decomposed chart smoke passed"
