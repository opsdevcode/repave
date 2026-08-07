#!/usr/bin/env bash
# Log in to ghcr.io for CI pushes. Use the org/user that owns packages, not github.actor.
set -euo pipefail

REGISTRY="${REGISTRY:-ghcr.io}"
USER_NAME="${GHCR_USER:-${GITHUB_REPOSITORY_OWNER:-}}"
TOKEN="${GHCR_TOKEN:-${GITHUB_TOKEN:-}}"

if [[ -z "${USER_NAME}" ]]; then
  echo "set GITHUB_REPOSITORY_OWNER or GHCR_USER for ghcr login" >&2
  exit 1
fi
if [[ -z "${TOKEN}" ]]; then
  echo "set GITHUB_TOKEN or GHCR_TOKEN for ghcr login" >&2
  exit 1
fi

echo "${TOKEN}" | docker login "${REGISTRY}" -u "${USER_NAME}" --password-stdin
