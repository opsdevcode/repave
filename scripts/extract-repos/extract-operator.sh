#!/usr/bin/env bash
# Extract repave-operator into a new git repository.
# Usage: extract-operator.sh <target-dir>
set -euo pipefail

TARGET="${1:?usage: extract-operator.sh <target-dir>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "install git-filter-repo: pip install git-filter-repo" >&2
  exit 1
fi

mkdir -p "$(dirname "$TARGET")"
if [[ -e "$TARGET" ]]; then
  echo "target already exists: $TARGET" >&2
  exit 1
fi

git clone "$ROOT" "$TARGET"
cd "$TARGET"
git filter-repo --force \
  --path operator/ \
  --path deploy/k8s/operator-chart/ \
  --path deploy/packages/repave-operator/ \
  --path .github/workflows/operator.yml \
  --path .github/workflows/operator-e2e.yml

echo "Extracted operator repo at $TARGET"
