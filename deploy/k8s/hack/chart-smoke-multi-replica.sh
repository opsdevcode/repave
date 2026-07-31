#!/usr/bin/env bash
# kind smoke: two portal replicas + decomposed worker + Postgres (shared sessions/queue).
# Submits a dry-run async run and asserts each portal pod passes /readyz (session_store).
# CI: .github/workflows/chart.yml (chart-smoke-multi-replica job).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke-multi-replica}"
NS="${CHART_SMOKE_MULTI_REPLICA_NAMESPACE:-repave-multi-replica-smoke}"
PORTAL_REPO="${CHART_SMOKE_PORTAL_REPO:-repave-portal}"
WORKER_REPO="${CHART_SMOKE_WORKER_REPO:-repave-worker}"
CORPUS_REPO="${CHART_SMOKE_CORPUS_REPO:-repave-corpus}"
IMG_TAG="${CHART_SMOKE_MULTI_REPLICA_TAG:-chart-smoke-multi-replica}"
TIMEOUT="${CHART_SMOKE_MULTI_REPLICA_TIMEOUT:-480}"
PORT="${CHART_SMOKE_MULTI_REPLICA_PORT:-18090}"
EXPECTED_PORTAL_REPLICAS="${CHART_SMOKE_MULTI_REPLICA_COUNT:-2}"

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
  if [[ "${CHART_SMOKE_MULTI_REPLICA_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_MULTI_REPLICA_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
    return 0
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}

wait_rollout() {
  local deployment="$1"
  kubectl -n "${NS}" rollout status "deployment/${deployment}" --timeout="${TIMEOUT}s"
}

portal_pod_names() {
  kubectl -n "${NS}" get pods \
    -l "app.kubernetes.io/instance=repave,repave.dev/gate-toolchain=false" \
    -o jsonpath='{.items[*].metadata.name}'
}

assert_portal_replica_count() {
  local pods ready_count=0 pod
  pods="$(portal_pod_names)"
  if [[ -z "${pods}" ]]; then
    echo "no portal pods found" >&2
    kubectl -n "${NS}" get pods >&2
    exit 1
  fi
  for pod in ${pods}; do
    if kubectl -n "${NS}" get pod "${pod}" -o jsonpath='{.status.conditions[?(@.type=="Ready")].status}' | grep -q True; then
      ready_count=$((ready_count + 1))
    fi
  done
  if [[ "${ready_count}" -lt "${EXPECTED_PORTAL_REPLICAS}" ]]; then
    echo "expected ${EXPECTED_PORTAL_REPLICAS} ready portal pods, got ${ready_count}" >&2
    kubectl -n "${NS}" get pods -o wide >&2
    exit 1
  fi
  echo "OK: ${ready_count} portal replica(s) ready"
}

assert_portal_pods_readyz() {
  local pod
  for pod in $(portal_pod_names); do
    kubectl -n "${NS}" exec "${pod}" -- python3 -c "
import json
import urllib.request

payload = json.load(urllib.request.urlopen('http://127.0.0.1:8088/readyz'))
assert payload.get('status') == 'ready', payload
checks = payload.get('checks') or {}
assert checks.get('session_store') is True, payload
"
    echo "OK: pod ${pod} /readyz session_store=true"
  done
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

echo "==> helm install multi-replica decomposed chart"
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  -f "${CHART}/values-multi-replica-smoke.yaml" \
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

assert_portal_replica_count
assert_portal_pods_readyz

if kubectl -n "${NS}" get deployment repave-worker >/dev/null 2>&1; then
  echo "OK: worker Deployment present"
else
  echo "missing worker Deployment repave-worker" >&2
  exit 1
fi

echo "==> port-forward portal Service (load-balanced)"
kubectl -n "${NS}" port-forward "svc/repave" "${PORT}:8088" >/tmp/repave-chart-smoke-multi-replica-pf.log 2>&1 &
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
    cat /tmp/repave-chart-smoke-multi-replica-pf.log >&2 || true
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
      "module_name": "chart-smoke-multi-replica",
      "description": "multi-replica chart smoke",
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

echo "OK: multi-replica chart smoke passed"
