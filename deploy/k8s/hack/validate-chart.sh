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
trap 'rm -f "${rendered}"' EXIT

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

echo "helm lint and template checks passed"
