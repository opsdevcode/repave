#!/usr/bin/env bash
# Package and push repave Helm charts to GHCR OCI.
set -euo pipefail

VERSION="${1:-}"
REGISTRY="${REGISTRY:-oci://ghcr.io/opsdevcode/charts}"

if [[ -z "${VERSION}" ]]; then
  echo "usage: $(basename "$0") VERSION" >&2
  echo "  VERSION  semver without v prefix (matches release tag)" >&2
  exit 1
fi

if ! [[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "invalid semver: ${VERSION}" >&2
  exit 1
fi

if ! command -v helm >/dev/null 2>&1; then
  echo "helm is required (https://helm.sh/docs/intro/install/)" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CHARTS=(
  deploy/k8s/chart
  deploy/k8s/operator-chart
)

workdir="$(mktemp -d)"
trap 'rm -rf "${workdir}"' EXIT

for rel in "${CHARTS[@]}"; do
  chart="${ROOT}/${rel}"
  name="$(grep '^name:' "${chart}/Chart.yaml" | awk '{print $2}')"
  echo "packaging ${name} ${VERSION}"
  pkg="$(helm package "${chart}" \
    --version "${VERSION}" \
    --app-version "${VERSION}" \
    --destination "${workdir}" \
    | awk '{print $NF}')"
  echo "pushing ${pkg} to ${REGISTRY}"
  helm push "${pkg}" "${REGISTRY}"
done

echo "published charts to ${REGISTRY} at version ${VERSION}"
