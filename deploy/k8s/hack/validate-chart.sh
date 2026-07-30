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
trap 'rm -f "${rendered}" "${portal_rendered}" "${hpa_rendered}" "${decomposed_rendered}" "${job_rendered}" "${decomposed_smoke_rendered}"' EXIT

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

echo "helm lint and template checks passed"
