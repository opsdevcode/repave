#!/usr/bin/env bash
# Publish + register the opsdevcode hosted demo library (see docs/hosted-demo-library.md).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENGINE="${ROOT}/engine"
FLEET_FILE="${REPAVE_FLEET_FILE:-${ROOT}/repave-fleet/registry.jsonl}"
MODULES_ROOT="${REPAVE_MODULES_ROOT:-${HOME}/repave-modules}"
MANIFESTS_DIR="${ROOT}/fleet-manifests"
OPERATOR_NS="${OPERATOR_NAMESPACE:-repave-system}"

if [[ "${SEED_TARGET:-}" == "k8s" || "${SEED_USE_GITHUB_APP:-}" == "1" ]]; then
  exec "${ROOT}/scripts/seed-hosted-demo-library-k8s.sh"
fi

if kubectl config current-context >/dev/null 2>&1 \
  && kubectl get deploy -n "${REPAVE_NAMESPACE:-repave}" "${REPAVE_RELEASE:-repave}" >/dev/null 2>&1 \
  && [[ -z "${GITHUB_TOKEN:-}" ]]; then
  echo "Cluster reachable and no GITHUB_TOKEN — using portal pod GitHub App auth." >&2
  exec "${ROOT}/scripts/seed-hosted-demo-library-k8s.sh"
fi

if [[ -z "${GITHUB_TOKEN:-}" && -z "${GITHUB_APP_ID:-}" ]]; then
  echo "Hosted: ./scripts/seed-hosted-demo-library-k8s.sh (GitHub App on portal pod)" >&2
  echo "Local:  export GITHUB_APP_* or GITHUB_TOKEN, then re-run." >&2
  exit 1
fi

mkdir -p "$(dirname "${FLEET_FILE}")"

cd "${ENGINE}" && uv sync --extra dev --quiet

export REPAVE_FLEET_FILE="${FLEET_FILE}"
export REPAVE_MODULES_ROOT="${MODULES_ROOT}"
export REPAVE_GITHUB_ORG="${REPAVE_GITHUB_ORG:-opsdevcode}"

ARGS=(python3 "${ROOT}/scripts/seed_hosted_demo_library.py" --repo-root "${ROOT}")
if [[ "${SEED_DRY_RUN:-}" == "1" ]]; then
  ARGS+=(--dry-run)
fi
if [[ "${SEED_SKIP_PUBLISH:-}" == "1" ]]; then
  ARGS+=(--skip-publish)
fi
if [[ "${SEED_SKIP_REGISTER:-}" == "1" ]]; then
  ARGS+=(--skip-register)
fi

"${ARGS[@]}" \
  --render-manifests \
  --manifests-dir "${MANIFESTS_DIR}" \
  --operator-namespace "${OPERATOR_NS}"

if [[ "${SEED_APPLY_MANIFESTS:-}" == "1" && "${SEED_DRY_RUN:-}" != "1" ]]; then
  kubectl apply -k "${MANIFESTS_DIR}"
fi

if [[ "${SEED_COPY_FLEET_TO_CLUSTER:-}" == "1" && "${SEED_DRY_RUN:-}" != "1" ]]; then
  portal_pod="$(kubectl get pod -n repave -l app.kubernetes.io/name=repave \
    -o jsonpath='{.items[0].metadata.name}')"
  kubectl exec -n repave "${portal_pod}" -- mkdir -p /data/fleet
  kubectl cp "${FLEET_FILE}" "repave/${portal_pod}:/data/fleet/registry.jsonl"
  echo "Copied fleet registry to portal pod ${portal_pod}"
fi

echo "Library seed complete. See docs/hosted-demo-library.md for /activity and /fleet walkthrough."
