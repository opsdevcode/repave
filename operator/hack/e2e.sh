#!/usr/bin/env bash
# kind e2e: slim operator (distroless) + in-cluster portal (/api/v2), apply drift
# fixture, assert OutOfDate + UpgradePlanned + non-empty upgradePlan.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MONOREPO_ROOT="$(cd "${ROOT}/.." && pwd)"
cd "${ROOT}"

CLUSTER_NAME="${KIND_CLUSTER_NAME:-repave-local}"
IMG="${IMG:-repave-operator:dev}"
PORTAL_IMG="${PORTAL_IMG:-repave-portal:e2e}"
TIMEOUT_SEC="${E2E_TIMEOUT_SEC:-180}"

if [[ -n "${KIND_BIN:-}" ]] && [[ -x "${KIND_BIN}" ]]; then
  :
elif command -v kind >/dev/null 2>&1; then
  KIND_BIN="$(command -v kind)"
else
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

echo "==> Building slim operator image ${IMG}"
docker build -f "${ROOT}/Dockerfile" -t "${IMG}" "${ROOT}"

echo "==> Building portal image ${PORTAL_IMG} (no gate toolchain)"
docker build -f "${MONOREPO_ROOT}/deploy/local/Dockerfile" \
  --build-arg INSTALL_GATE_TOOLCHAIN=0 \
  -t "${PORTAL_IMG}" "${MONOREPO_ROOT}"

echo "==> Loading images into kind"
"${KIND_BIN}" load docker-image "${IMG}" --name "${CLUSTER_NAME}"
"${KIND_BIN}" load docker-image "${PORTAL_IMG}" --name "${CLUSTER_NAME}"

echo "==> Applying CRDs and e2e manifests"
kubectl apply -f config/crd/bases/
kubectl apply -f config/e2e/namespace.yaml
kubectl apply -f config/e2e/rbac.yaml
kubectl apply -f config/e2e/portal.yaml
kubectl apply -f config/e2e/manager.yaml

echo "==> Waiting for portal Deployment"
kubectl -n repave-system rollout status deployment/repave-portal --timeout="${TIMEOUT_SEC}s"

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
  kubectl -n repave-system logs deploy/repave-portal --tail=120 || true
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

catalog_blueprint_version="$(
  awk '/^metadata:/{m=1; next} m && /^  version:/{gsub(/"/, "", $2); print $2; exit}' \
    "${MONOREPO_ROOT}/blueprints/terraform-module-generic/blueprint.yaml"
)"
plan_blueprint_name="$(kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.upgradePlan.blueprintName}' 2>/dev/null || true)"
plan_blueprint_version="$(kubectl get goldenpathrepo e2e-drift -o jsonpath='{.status.upgradePlan.blueprintVersion}' 2>/dev/null || true)"
if [[ "${plan_blueprint_name}" != "terraform-module-generic" ]]; then
  echo "Expected upgradePlan.blueprintName=terraform-module-generic (got ${plan_blueprint_name:-<empty>})" >&2
  exit 1
fi
if [[ -z "${catalog_blueprint_version}" ]]; then
  echo "Could not read terraform-module-generic catalog version from monorepo" >&2
  exit 1
fi
if [[ "${plan_blueprint_version}" != "${catalog_blueprint_version}" ]]; then
  echo "Expected upgradePlan.blueprintVersion=${catalog_blueprint_version} (catalog pin; got ${plan_blueprint_version:-<empty>})" >&2
  kubectl get goldenpathrepo e2e-drift -o yaml || true
  exit 1
fi
echo "OK: upgradePlan targets catalog blueprint terraform-module-generic@${plan_blueprint_version}"

echo "==> preserve-local apply-upgrade smoke (host copy of terraform-minimal)"
run_preserve_local_smoke() {
  local work staging_a
  work="$(mktemp -d)"
  staging_a="$(mktemp -d)"
  cp -a "${MODULES_HOST}/terraform-minimal/." "${work}/"
  (
    cd "${work}"
    git init -q
    git config user.email e2e@repave.dev
    git config user.name repave-e2e
    git add -A
    git commit -q -m "init fixture"
  )
  local repave_cli="${MONOREPO_ROOT}/engine/.venv/bin/repave"
  if [[ ! -x "${repave_cli}" ]]; then
    echo "skip preserve-local smoke: install engine venv (${repave_cli} missing)"
    rm -rf "${work}" "${staging_a}"
    return 0
  fi
  REPAVE_REPO_ROOT="${MONOREPO_ROOT}" "${repave_cli}" apply-upgrade \
    --repo-root "${MONOREPO_ROOT}" \
    --target-repo "${work}" \
    --git-branch repave/e2e-base \
    --commit-message "e2e base upgrade" \
    --format json >/dev/null
  echo "LOCAL EDIT" >>"${work}/README.md"
  REPAVE_REPO_ROOT="${MONOREPO_ROOT}" "${repave_cli}" apply-upgrade \
    --repo-root "${MONOREPO_ROOT}" \
    --target-repo "${work}" \
    --git-branch repave/e2e-preserve \
    --commit-message "e2e preserve" \
    --preserve-local \
    --format json >/dev/null
  if ! grep -q "LOCAL EDIT" "${work}/README.md"; then
    echo "README.md was overwritten; preserve-local failed" >&2
    rm -rf "${work}" "${staging_a}"
    exit 1
  fi
  if [[ ! -f "${work}/.repave/upgrade-staging/README.md" ]]; then
    echo "expected .repave/upgrade-staging/README.md hint" >&2
    rm -rf "${work}" "${staging_a}"
    exit 1
  fi
  rm -rf "${work}" "${staging_a}"
  echo "OK: preserve-local smoke on real module fixture"
}
run_preserve_local_smoke

kubectl get goldenpathrepo e2e-drift -o yaml
