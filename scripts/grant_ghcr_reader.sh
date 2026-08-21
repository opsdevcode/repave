#!/usr/bin/env bash
# Grant GHCR package read to a GitHub user (after IP assignment + payment).
# Usage: ./scripts/grant_ghcr_reader.sh <github-username>
set -euo pipefail

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  echo "usage: $0 <github-username>" >&2
  exit 2
fi

user="$1"
org="${GHCR_ORG:-opsdevcode}"
packages=(
  repave-engine
  repave-engine-portal
  repave-corpus
  charts/repave
)

for pkg in "${packages[@]}"; do
  encoded="${pkg//\//%2F}"
  echo "grant read: ${org}/${pkg} -> ${user}"
  gh api --method PUT \
    "orgs/${org}/packages/container/${encoded}/collaborators/${user}" \
    -f permission=read
done
