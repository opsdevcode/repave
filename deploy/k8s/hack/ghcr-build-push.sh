#!/usr/bin/env bash
# Build and push one image to GHCR with login refresh + retries (container.yml).
set -euo pipefail

CONTEXT="${CONTEXT:-.}"
FILE="${FILE:?set FILE to the Dockerfile path}"
TAGS="${TAGS:?set TAGS to newline-separated image tags}"
BUILD_ARGS="${BUILD_ARGS:-}"
ATTEMPTS="${PUSH_ATTEMPTS:-3}"
WAIT="${PUSH_RETRY_WAIT_SECONDS:-45}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

declare -a tag_flags=()
while IFS= read -r tag; do
  [[ -z "${tag}" ]] && continue
  tag_flags+=(--tag "${tag}")
done <<< "${TAGS}"

declare -a build_arg_flags=()
while IFS= read -r line; do
  [[ -z "${line}" ]] && continue
  build_arg_flags+=(--build-arg "${line}")
done <<< "${BUILD_ARGS}"

if ((${#tag_flags[@]} == 0)); then
  echo "no tags to push; set TAGS" >&2
  exit 1
fi

for ((attempt = 1; attempt <= ATTEMPTS; attempt++)); do
  echo "build push attempt ${attempt}/${ATTEMPTS}"
  "${SCRIPT_DIR}/ghcr-login.sh"
  if docker buildx build \
    --file "${FILE}" \
    --push \
    "${tag_flags[@]}" \
    "${build_arg_flags[@]}" \
    "${CONTEXT}"; then
    exit 0
  fi
  if ((attempt < ATTEMPTS)); then
    echo "push failed; retrying in ${WAIT}s"
    sleep "${WAIT}"
  fi
done

echo "build push failed after ${ATTEMPTS} attempts" >&2
exit 1
