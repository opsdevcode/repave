#!/usr/bin/env bash
# Render the chart with representative values and assert core objects exist.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHART="${ROOT}/deploy/k8s/chart"

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required (https://helm.sh/docs/intro/install/)" >&2
  exit 1
fi

helm lint "${CHART}"

rendered="$(mktemp)"
portal_rendered="$(mktemp)"
hpa_rendered="$(mktemp)"
decomposed_rendered="$(mktemp)"
job_rendered="$(mktemp)"
decomposed_smoke_rendered="$(mktemp)"
day2_rendered="$(mktemp)"
multi_replica_rendered="$(mktemp)"
worker_hpa_rendered="$(mktemp)"
fleet_shared_rendered="$(mktemp)"
trap 'rm -f "${rendered}" "${portal_rendered}" "${hpa_rendered}" "${decomposed_rendered}" "${job_rendered}" "${decomposed_smoke_rendered}" "${day2_rendered}" "${multi_replica_rendered}" "${worker_hpa_rendered}" "${fleet_shared_rendered}"' EXIT

helm template repave-test "${CHART}" \
  --namespace repave-test \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set secrets.create=true \
  --set secrets.githubToken=test-token \
  >"${rendered}"

for kind in Deployment Service ConfigMap ServiceAccount; do
  if ! grep -q "kind: ${kind}" "${rendered}"; then
    echo "missing ${kind} in helm template output" >&2
    exit 1
  fi
done

if ! grep -q 'path: /health' "${rendered}" || ! grep -q 'path: /readyz' "${rendered}"; then
  echo "probes must reference /health and /readyz" >&2
  exit 1
fi

if ! grep -q 'kind: PodDisruptionBudget' "${rendered}"; then
  echo "default render must include PodDisruptionBudget" >&2
  exit 1
fi

if ! grep -q 'startupProbe:' "${rendered}"; then
  echo "deployment must define startupProbe" >&2
  exit 1
fi

if ! grep -q 'terminationGracePeriodSeconds: 120' "${rendered}"; then
  echo "deployment must set terminationGracePeriodSeconds" >&2
  exit 1
fi

helm template repave-hpa "${CHART}" \
  --namespace repave-hpa \
  --set repave.output.githubOrg=example-org \
  --set persistence.modules.enabled=false \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=2 \
  --set autoscaling.maxReplicas=5 \
  >"${hpa_rendered}"

if ! grep -q 'kind: HorizontalPodAutoscaler' "${hpa_rendered}"; then
  echo "autoscaling.enabled must render HorizontalPodAutoscaler" >&2
  exit 1
fi

if grep -q '^  replicas:' "${hpa_rendered}"; then
  echo "HPA mode must omit Deployment.spec.replicas" >&2
  exit 1
fi

if ! grep -q 'name: REPAVE_IMAGE_GATE_TOOLCHAIN' "${rendered}"; then
  echo "deployment must set REPAVE_IMAGE_GATE_TOOLCHAIN" >&2
  exit 1
fi


helm template repave-portal "${CHART}" \
  --namespace repave-portal \
  -f "${CHART}/values-portal.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${portal_rendered}"

if ! grep -q 'repave.dev/gate-toolchain: "false"' "${portal_rendered}"; then
  echo "values-portal.yaml must render gate-toolchain: false label" >&2
  exit 1
fi

helm template repave-decomposed "${CHART}" \
  --namespace repave-decomposed \
  -f "${CHART}/values-decomposed.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${decomposed_rendered}"

if ! grep -q 'name: repave-decomposed-worker' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'name: corpus-init' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must render corpus initContainer" >&2
  exit 1
fi

if ! grep -q 'ghcr.io/opsdevcode/repave-engine:' "${decomposed_rendered}"; then
  echo "worker Deployment must use gate-toolchain image" >&2
  exit 1
fi

if grep -q 'REPAVE_ARTIFACT_STORE_URI' "${decomposed_rendered}"; then
  echo "values-decomposed.yaml must not require REPAVE_ARTIFACT_STORE_URI (snapshots default)" >&2
  exit 1
fi

helm template repave-decomposed-job "${CHART}" \
  --namespace repave-decomposed-job \
  -f "${CHART}/values-decomposed-job.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${job_rendered}"

if grep -q 'name: repave-decomposed-job-worker' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must not render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'kind: Role' "${job_rendered}" || ! grep -q 'run-jobs' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must render run-job RBAC Role" >&2
  exit 1
fi

if ! grep -q 'REPAVE_RUN_JOBS' "${job_rendered}"; then
  echo "values-decomposed-job.yaml must set REPAVE_RUN_JOBS on portal Deployment" >&2
  exit 1
fi

helm template repave-decomposed-smoke "${CHART}" \
  --namespace repave-decomposed-smoke \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${decomposed_smoke_rendered}"

if ! grep -q 'name: repave-decomposed-smoke-worker' "${decomposed_smoke_rendered}"; then
  echo "values-decomposed-smoke.yaml must render worker Deployment" >&2
  exit 1
fi

if ! grep -q 'repave.dev/gate-toolchain: "false"' "${decomposed_smoke_rendered}"; then
  echo "values-decomposed-smoke.yaml must render portal without gate toolchain" >&2
  exit 1
fi

helm template repave-day2 "${CHART}" \
  --namespace repave-day2 \
  -f "${CHART}/values-day2.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${day2_rendered}"

if ! grep -q 'kind: ServiceMonitor' "${day2_rendered}"; then
  echo "values-day2.yaml must render ServiceMonitor when monitoring is enabled" >&2
  exit 1
fi

if ! grep -q 'kind: PrometheusRule' "${day2_rendered}"; then
  echo "values-day2.yaml must render PrometheusRule when monitoring is enabled" >&2
  exit 1
fi

if ! grep -q 'RepaveAsyncRunFailureRateHigh' "${day2_rendered}"; then
  echo "PrometheusRule must include async run failure alert" >&2
  exit 1
fi

helm template repave-multi-replica-smoke "${CHART}" \
  --namespace repave-multi-replica-smoke \
  -f "${CHART}/values-decomposed-smoke.yaml" \
  -f "${CHART}/values-multi-replica-smoke.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${multi_replica_rendered}"

if ! grep -q 'replicas: 2' "${multi_replica_rendered}"; then
  echo "values-multi-replica-smoke.yaml must render portal Deployment with replicas: 2" >&2
  exit 1
fi

worker_hpa_rendered="$(mktemp)"

helm template repave-worker-hpa "${CHART}" \
  --namespace repave-worker-hpa \
  -f "${CHART}/values-decomposed.yaml" \
  --set repave.output.githubOrg=example-org \
  --set workerAutoscaling.enabled=true \
  --set workerAutoscaling.minReplicas=2 \
  --set workerAutoscaling.maxReplicas=6 \
  >"${worker_hpa_rendered}"

if ! grep -q 'kind: HorizontalPodAutoscaler' "${worker_hpa_rendered}"; then
  echo "workerAutoscaling must render worker HorizontalPodAutoscaler" >&2
  exit 1
fi

if ! grep -A2 'kind: HorizontalPodAutoscaler' "${worker_hpa_rendered}" | grep -q 'name: repave-worker-hpa-worker'; then
  echo "workerAutoscaling HPA must target repave-worker-hpa-worker Deployment" >&2
  exit 1
fi

if grep -A20 'name: repave-worker-hpa-worker' "${worker_hpa_rendered}" | grep -q '^  replicas:'; then
  echo "worker HPA mode must omit worker Deployment.spec.replicas" >&2
  exit 1
fi

fleet_shared_rendered="$(mktemp)"

helm template repave-fleet-shared "${CHART}" \
  --namespace repave \
  -f "${CHART}/values-fleet-shared.yaml" \
  --set repave.output.githubOrg=example-org \
  >"${fleet_shared_rendered}"

if ! grep -q 'kind: PersistentVolumeClaim' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must render fleet PVC" >&2
  exit 1
fi

if ! grep -q 'name: repave-fleet' "${fleet_shared_rendered}"; then
  echo "values-fleet-shared.yaml must name fleet claim repave-fleet" >&2
  exit 1
fi

if ! grep -q 'require_session_secret: true' "${multi_replica_rendered}"; then
  echo "values-multi-replica-smoke.yaml must require session secret for multi-replica" >&2
  exit 1
fi

echo "helm lint and template checks passed"
