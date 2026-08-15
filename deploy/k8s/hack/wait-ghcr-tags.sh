#!/usr/bin/env bash
# Wait until release image tags exist on ghcr.io (container.yml may still be pushing).
# Uses the GHCR token exchange — raw Bearer GITHUB_TOKEN often returns 403 on manifests.
set -euo pipefail

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
  echo "usage: $(basename "$0") VERSION" >&2
  exit 1
fi
if ! [[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "invalid semver: ${VERSION}" >&2
  exit 1
fi

TOKEN="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
if [[ -z "${TOKEN}" ]]; then
  echo "set GHCR_TOKEN or GITHUB_TOKEN to read private GHCR packages" >&2
  exit 1
fi

USER_NAME="${GHCR_USER:-${GITHUB_REPOSITORY_OWNER:-${GITHUB_ACTOR:-x-access-token}}}"

IMAGES=(
  "opsdevcode/repave-engine"
  "opsdevcode/repave-engine-portal"
  "opsdevcode/repave-corpus"
  "opsdevcode/repave-operator"
  "opsdevcode/repave-backstage"
)

MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
SLEEP_SECONDS="${SLEEP_SECONDS:-20}"

pull_token() {
  local image="$1"
  local scope="repository:${image}:pull"
  curl -sS -u "${USER_NAME}:${TOKEN}" \
    "https://ghcr.io/token?service=ghcr.io&scope=${scope}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))'
}

manifest_ready() {
  local image="$1"
  local reg_token code
  reg_token="$(pull_token "${image}")"
  if [[ -z "${reg_token}" ]]; then
    return 1
  fi
  code="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${reg_token}" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://ghcr.io/v2/${image}/manifests/${VERSION}" || true)"
  [[ "${code}" == "200" ]]
}

for image in "${IMAGES[@]}"; do
  echo "waiting for ghcr.io/${image}:${VERSION} ..."
  ready=false
  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    if manifest_ready "${image}"; then
      echo "ready: ghcr.io/${image}:${VERSION}"
      ready=true
      break
    fi
    echo "  attempt ${attempt}/${MAX_ATTEMPTS}: not ready yet"
    sleep "${SLEEP_SECONDS}"
  done
  if [[ "${ready}" != "true" ]]; then
    echo "timed out waiting for ghcr.io/${image}:${VERSION}" >&2
    exit 1
  fi
done

echo "all release images present for ${VERSION}"
