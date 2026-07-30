#!/usr/bin/env bash
# Assert v1beta1 is the CRD storage version and v1alpha1 writes convert successfully.
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
E2E_DIR="${SCRIPT_ROOT}/config/e2e"

assert_crd_storage_version() {
  local crd="$1"
  local want="${2:-v1beta1}"
  local got
  got="$(kubectl get crd "${crd}" -o "jsonpath={.spec.versions[?(@.storage==true)].name}")"
  if [[ "${got}" != "${want}" ]]; then
    echo "Expected CRD ${crd} storage version ${want} (got ${got:-<empty>})" >&2
    kubectl get crd "${crd}" -o yaml >&2 || true
    return 1
  fi
  echo "OK: CRD ${crd} storage version ${want}"
}

assert_raw_get_version() {
  local resource_path="$1"
  local want_api_version="$2"
  local label="$3"
  local body api_version
  body="$(kubectl get --raw "${resource_path}")"
  api_version="$(printf '%s' "${body}" | python3 -c "import json,sys; print(json.load(sys.stdin)['apiVersion'])")"
  if [[ "${api_version}" != "${want_api_version}" ]]; then
    echo "Expected ${label} apiVersion=${want_api_version} (got ${api_version})" >&2
    printf '%s\n' "${body}" >&2
    return 1
  fi
  echo "OK: ${label} stored as ${want_api_version}"
}

echo "==> CRD storage versions"
assert_crd_storage_version goldenpathrepos.repave.dev
assert_crd_storage_version blueprints.repave.dev

echo "==> GoldenPathRepo v1alpha1 apply converts to v1beta1 storage"
assert_raw_get_version \
  "/apis/repave.dev/v1beta1/namespaces/default/goldenpathrepos/e2e-drift" \
  "repave.dev/v1beta1" \
  "GoldenPathRepo/e2e-drift"

if [[ -f "${E2E_DIR}/blueprint-conversion.yaml" ]]; then
  echo "==> Blueprint v1alpha1 apply converts to v1beta1 storage"
  kubectl apply -f "${E2E_DIR}/blueprint-conversion.yaml"
  assert_raw_get_version \
    "/apis/repave.dev/v1beta1/namespaces/default/blueprints/e2e-conversion" \
    "repave.dev/v1beta1" \
    "Blueprint/e2e-conversion"
fi
