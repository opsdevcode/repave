#!/usr/bin/env bash
# Confirm a GHCR tag is pullable (post-push gate for container.yml).
# Uses the GHCR token exchange — raw Bearer GITHUB_TOKEN often returns 403 on manifests.
set -euo pipefail

IMAGE="${1:-}"
REF="${2:-}"
if [[ -z "${IMAGE}" || -z "${REF}" ]]; then
  echo "usage: $(basename "$0") IMAGE REF" >&2
  echo "  IMAGE  opsdevcode/repave-engine-portal" >&2
  echo "  REF    main | abc1234 | 2.35.0" >&2
  exit 1
fi

TOKEN="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"
if [[ -z "${TOKEN}" ]]; then
  echo "set GHCR_TOKEN or GITHUB_TOKEN to verify GHCR tags" >&2
  exit 1
fi

USER_NAME="${GHCR_USER:-${GITHUB_REPOSITORY_OWNER:-${GITHUB_ACTOR:-x-access-token}}}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-12}"
SLEEP_SECONDS="${SLEEP_SECONDS:-10}"

pull_token() {
  local scope="repository:${IMAGE}:pull"
  curl -sS -u "${USER_NAME}:${TOKEN}" \
    "https://ghcr.io/token?service=ghcr.io&scope=${scope}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))'
}

manifest_ready() {
  local reg_token code
  reg_token="$(pull_token)"
  if [[ -z "${reg_token}" ]]; then
    return 1
  fi
  code="$(curl -sS -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer ${reg_token}" \
    -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json, application/vnd.docker.distribution.manifest.list.v2+json" \
    "https://ghcr.io/v2/${IMAGE}/manifests/${REF}" || true)"
  [[ "${code}" == "200" ]]
}

echo "verifying ghcr.io/${IMAGE}:${REF} ..."
for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
  if manifest_ready; then
    echo "ready: ghcr.io/${IMAGE}:${REF}"
    exit 0
  fi
  echo "  attempt ${attempt}/${MAX_ATTEMPTS}: not ready yet"
  sleep "${SLEEP_SECONDS}"
done

echo "timed out verifying ghcr.io/${IMAGE}:${REF}" >&2
exit 1
