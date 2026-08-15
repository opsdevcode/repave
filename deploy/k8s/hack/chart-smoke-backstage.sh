#!/usr/bin/env bash
# kind smoke: engine + hosted Backstage (ADR 011).
# Builds both images, installs values-kind + values-backstage, probes
# engine /health + /api/v2, HTML 410, and Backstage liveness/readiness.
# CI: .github/workflows/chart.yml (chart-smoke-backstage; path-gated).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"
BACKSTAGE_DIR="${ROOT}/backstage"
CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-chart-smoke-backstage}"
NS="${CHART_SMOKE_BACKSTAGE_NAMESPACE:-repave-backstage-smoke}"
IMG_REPO="${CHART_SMOKE_IMAGE_REPO:-repave-engine}"
IMG_TAG="${CHART_SMOKE_IMAGE_TAG:-chart-smoke}"
BS_IMG_REPO="${CHART_SMOKE_BACKSTAGE_IMAGE_REPO:-repave-backstage}"
BS_IMG_TAG="${CHART_SMOKE_BACKSTAGE_IMAGE_TAG:-chart-smoke}"
INSTALL_GATE_TOOLCHAIN="${CHART_SMOKE_INSTALL_GATE_TOOLCHAIN:-0}"
TIMEOUT="${CHART_SMOKE_BACKSTAGE_TIMEOUT:-420}"
ENGINE_PORT="${CHART_SMOKE_BACKSTAGE_ENGINE_PORT:-18088}"
BS_PORT="${CHART_SMOKE_BACKSTAGE_PORT:-17007}"
YARN=(node "${BACKSTAGE_DIR}/.yarn/releases/yarn-4.13.0.cjs")

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

cleanup() {
  if [[ "${CHART_SMOKE_BACKSTAGE_KEEP_CLUSTER:-}" == "1" ]]; then
    echo "CHART_SMOKE_BACKSTAGE_KEEP_CLUSTER=1; leaving cluster ${CLUSTER_NAME}"
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

echo "==> yarn build Backstage backend"
(
  cd "${BACKSTAGE_DIR}"
  "${YARN[@]}" install --immutable
  "${YARN[@]}" tsc
  "${YARN[@]}" build:backend
)

echo "==> docker build ${BS_IMG_REPO}:${BS_IMG_TAG}"
docker build -f "${BACKSTAGE_DIR}/packages/backend/Dockerfile" \
  -t "${BS_IMG_REPO}:${BS_IMG_TAG}" "${BACKSTAGE_DIR}"

echo "==> kind load images"
kind load docker-image "${IMG_REPO}:${IMG_TAG}" --name "${CLUSTER_NAME}"
kind load docker-image "${BS_IMG_REPO}:${BS_IMG_TAG}" --name "${CLUSTER_NAME}"

SMOKE_VALUES="$(mktemp)"
cat >"${SMOKE_VALUES}" <<'EOF'
repave:
  backstage:
    extraEnv:
      - name: AUTH0_CLIENT_ID
        value: chart-smoke
      - name: AUTH0_CLIENT_SECRET
        value: chart-smoke
      - name: AUTH0_DOMAIN
        value: example.auth0.com
      - name: AUTH0_AUDIENCE
        value: chart-smoke
EOF

echo "==> helm install (kind + Backstage overlay)"
# Portal-only engine image: gateToolchain=false so /readyz does not wait on CLIs.
helm upgrade --install repave "${CHART}" \
  --namespace "${NS}" --create-namespace \
  -f "${CHART}/values-kind.yaml" \
  -f "${CHART}/values-backstage.yaml" \
  -f "${SMOKE_VALUES}" \
  --set image.repository="${IMG_REPO}" \
  --set image.tag="${IMG_TAG}" \
  --set image.pullPolicy=Never \
  --set image.gateToolchain=false \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set persistence.modules.kindHostPath="" \
  --set repave.backstage.image.repository="${BS_IMG_REPO}" \
  --set repave.backstage.image.tag="${BS_IMG_TAG}" \
  --set repave.backstage.image.pullPolicy=Never \
  --wait --timeout "${TIMEOUT}s"

echo "==> wait for rollouts"
kubectl -n "${NS}" rollout status deployment/repave --timeout="${TIMEOUT}s"
kubectl -n "${NS}" rollout status deployment/repave-backstage --timeout="${TIMEOUT}s"

echo "==> port-forward"
kubectl -n "${NS}" port-forward svc/repave "${ENGINE_PORT}:8088" \
  >/tmp/repave-chart-smoke-backstage-engine-pf.log 2>&1 &
ENGINE_PF_PID=$!
kubectl -n "${NS}" port-forward svc/repave-backstage "${BS_PORT}:7007" \
  >/tmp/repave-chart-smoke-backstage-pf.log 2>&1 &
BS_PF_PID=$!
trap 'kill "${ENGINE_PF_PID}" "${BS_PF_PID}" 2>/dev/null || true; cleanup' EXIT

probe_match() {
  local url="$1" pattern="$2"
  local body
  body="$(curl -sf "${url}")"
  grep -qiE "${pattern}" <<<"${body}"
}

probe_html_gone() {
  local headers body code
  headers="$(mktemp)"
  body="$(mktemp)"
  code="$(curl -sS -D "${headers}" -o "${body}" -w '%{http_code}' "http://127.0.0.1:${ENGINE_PORT}/")"
  [[ "${code}" == "410" ]] || return 1
  grep -qi '^sunset:' "${headers}"
}

for attempt in 1 2 3 4 5 6 7 8; do
  if probe_match "http://127.0.0.1:${ENGINE_PORT}/health" '"status":"ok"' \
    && probe_match "http://127.0.0.1:${ENGINE_PORT}/readyz" '"status":"ready"' \
    && probe_match "http://127.0.0.1:${ENGINE_PORT}/api/v2/catalog/entities" '"entities"' \
    && probe_html_gone \
    && curl -sf "http://127.0.0.1:${BS_PORT}/.backstage/health/v1/liveness" >/dev/null \
    && curl -sf "http://127.0.0.1:${BS_PORT}/.backstage/health/v1/readiness" >/dev/null; then
    echo "OK: Backstage chart smoke passed"
    exit 0
  fi
  if [[ "${attempt}" -eq 8 ]]; then
    echo "Backstage chart smoke probes failed after port-forward" >&2
    cat /tmp/repave-chart-smoke-backstage-engine-pf.log >&2 || true
    cat /tmp/repave-chart-smoke-backstage-pf.log >&2 || true
    kubectl -n "${NS}" get pods -o wide >&2 || true
    kubectl -n "${NS}" logs deploy/repave-backstage --tail=80 >&2 || true
    exit 1
  fi
  sleep 3
done
