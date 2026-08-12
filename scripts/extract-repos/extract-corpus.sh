#!/usr/bin/env bash
# Extract repave-corpus into a new git repository.
# Usage: extract-corpus.sh <target-dir>
set -euo pipefail

TARGET="${1:?usage: extract-corpus.sh <target-dir>}"
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
  --path blueprints/ \
  --path standards/ \
  --path policy/ \
  --path schemas/ \
  --path ansible/ \
  --path observability/ \
  --path scripts/check_blueprint_conformance_manifests.py \
  --path engine/src/repave_engine/blueprint_conformance.py \
  --path engine/tests/test_blueprint_conformance.py \
  --path engine/tests/test_blueprint_conformance_helpers.py \
  --path engine/tests/test_blueprint_conformance_manifest.py \
  --path repos/repave-corpus/ \
  --path-rename repos/repave-corpus/:docs/

echo "Extracted corpus repo at $TARGET"
