#!/usr/bin/env bash
# Render the operator chart with representative values and assert core objects exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/operator-chart"
FAKE_CA="ZmFrZS1jYS1idW5kbGU="

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required (https://helm.sh/docs/intro/install/)" >&2
  exit 1
fi

chmod +x "${ROOT}/deploy/k8s/hack/sync-operator-chart-crds.sh"
"${ROOT}/deploy/k8s/hack/sync-operator-chart-crds.sh"

helm lint "${CHART}" \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set webhook.caBundle="${FAKE_CA}"

rendered="$(mktemp)"
day2_rendered="$(mktemp)"
kind_rendered="$(mktemp)"
trap 'rm -f "${rendered}" "${day2_rendered}" "${kind_rendered}"' EXIT

helm template repave-operator-test "${CHART}" \
  --namespace repave-system \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set webhook.caBundle="${FAKE_CA}" \
  >"${rendered}"

for kind in Deployment Service ClusterRole ClusterRoleBinding ServiceAccount; do
  if ! grep -q "kind: ${kind}" "${rendered}"; then
    echo "missing ${kind} in helm template output" >&2
    exit 1
  fi
done

if ! grep -q 'kind: CustomResourceDefinition' "${rendered}"; then
  echo "default render must include CustomResourceDefinition resources" >&2
  exit 1
fi

if ! grep -q "caBundle: ${FAKE_CA}" "${rendered}"; then
  echo "webhook.caBundle must be injected into CRD conversion clientConfig" >&2
  exit 1
fi

if ! grep -q 'path: /healthz' "${rendered}" || ! grep -q 'path: /readyz' "${rendered}"; then
  echo "probes must reference /healthz and /readyz" >&2
  exit 1
fi

if ! grep -q 'name: REPAVE_API_URL' "${rendered}"; then
  echo "deployment must set REPAVE_API_URL" >&2
  exit 1
fi

if ! grep -q 'kind: PodDisruptionBudget' "${rendered}"; then
  echo "default render must include PodDisruptionBudget" >&2
  exit 1
fi

if ! grep -q '\-\-leader-elect=true' "${rendered}"; then
  echo "default render must enable leader election" >&2
  exit 1
fi

helm template repave-operator-day2 "${CHART}" \
  --namespace repave-system \
  -f "${CHART}/values-day2.yaml" \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set webhook.caBundle="${FAKE_CA}" \
  >"${day2_rendered}"

if ! grep -q 'kind: ServiceMonitor' "${day2_rendered}"; then
  echo "values-day2.yaml must render ServiceMonitor" >&2
  exit 1
fi

if ! grep -q 'replicas: 2' "${day2_rendered}"; then
  echo "values-day2.yaml must render two replicas" >&2
  exit 1
fi

if ! grep -q '\-\-metrics-bind-address=:8080' "${day2_rendered}"; then
  echo "values-day2.yaml must enable metrics on :8080" >&2
  exit 1
fi

helm template repave-operator-kind "${CHART}" \
  --namespace repave-system \
  -f "${CHART}/values-kind.yaml" \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set webhook.caBundle="${FAKE_CA}" \
  --set image.repository=repave-operator \
  --set image.tag=dev \
  >"${kind_rendered}"

if ! grep -q '\-\-leader-elect=false' "${kind_rendered}"; then
  echo "values-kind.yaml must disable leader election" >&2
  exit 1
fi

if ! grep -q 'path: /modules' "${kind_rendered}"; then
  echo "values-kind.yaml must mount modules hostPath" >&2
  exit 1
fi

fleet_shared_rendered="$(mktemp)"
helm template repave-operator-fleet "${CHART}" \
  --namespace repave \
  -f "${CHART}/values-fleet-shared.yaml" \
  --set repave.apiUrl=http://repave.repave.svc.cluster.local:8088 \
  --set webhook.caBundle="${FAKE_CA}" \
  >"${fleet_shared_rendered}"

if ! grep -q 'REPAVE_FLEET_SYNC_ENABLED' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must enable fleet registry sync env" >&2
  exit 1
fi

if ! grep -q 'claimName: repave-fleet' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must mount existingClaim repave-fleet" >&2
  exit 1
fi

if ! grep -q 'verbs: \["get", "list", "watch", "create", "update", "patch", "delete"\]' "${fleet_shared_rendered}"; then
  echo "operator RBAC must allow goldenpathrepos create/delete for fleetSync" >&2
  exit 1
fi

echo "OK: operator chart lint and template checks passed"
