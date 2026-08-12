#!/usr/bin/env bash
# Extract repave-cli into a new git repository.
# Usage: extract-cli.sh <target-dir>
set -euo pipefail

TARGET="${1:?usage: extract-cli.sh <target-dir>}"
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
  --path cli/ \
  --path repos/repave-cli/

echo "Extracted cli repo at $TARGET"
