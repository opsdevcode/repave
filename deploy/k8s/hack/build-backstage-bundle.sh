#!/usr/bin/env bash
# Produce packages/backend/dist/{skeleton,bundle}.tar.gz for the Backstage Dockerfile.
# Used by chart-smoke-backstage and container.yml (GHCR publish).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BACKSTAGE_DIR="${ROOT}/backstage"
YARN=(node "${BACKSTAGE_DIR}/.yarn/releases/yarn-4.13.0.cjs")

cd "${BACKSTAGE_DIR}"
"${YARN[@]}" install --immutable
"${YARN[@]}" tsc
"${YARN[@]}" build:backend
