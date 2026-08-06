#!/usr/bin/env bash
# Tier A ops smoke: simulate github-repo fleet register → fleet-manifests.
# No live GitHub and no Kubernetes cluster required.
#
# Usage (from repo root):
#   ./scripts/validate-github-repo-fleet.sh
#   make validate-github-repo-fleet
#
# Optional: VALIDATE_GITHUB_REPO_FLEET_UNITS=1 also runs engine + fleetsync unit tests.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="${VALIDATE_GITHUB_REPO_FLEET_WORKDIR:-$(mktemp -d "${TMPDIR:-/tmp}/repave-github-repo-fleet.XXXXXX")}"
REGISTRY="$WORK/registry.jsonl"
MANIFESTS="$WORK/manifests"
REPO_URL="${VALIDATE_GITHUB_REPO_FLEET_URL:-https://github.com/example-org/platform-demo}"
BLUEPRINT_NAME="github-repo-generic"
BLUEPRINT_VERSION="0.2.0"
STANDARD_SOURCE="standards/github/repo-provisioning-standard.md"
STANDARD_VERSION="1.1.0"

cleanup() {
  if [[ "${VALIDATE_GITHUB_REPO_FLEET_KEEP:-}" == "1" ]]; then
    echo "Keeping workdir: $WORK"
    return
  fi
  rm -rf "$WORK"
}
trap cleanup EXIT

mkdir -p "$WORK" "$MANIFESTS"
export REPAVE_FLEET_FILE="$REGISTRY"

echo "==> Register simulated github-repo provision ($REPO_URL)"
(
  cd "$ROOT/engine"
  uv run repave register "$REPO_URL" \
    --repo-root "$ROOT" \
    --blueprint "$BLUEPRINT_NAME" \
    --blueprint-version "$BLUEPRINT_VERSION" \
    --standard-source "$STANDARD_SOURCE" \
    --standard-version "$STANDARD_VERSION"
)

echo "==> List fleet registry"
FLEET_JSON="$(
  cd "$ROOT/engine"
  uv run repave fleet --repo-root "$ROOT" --format json
)"
echo "$FLEET_JSON"

if ! printf '%s' "$FLEET_JSON" | grep -q "$BLUEPRINT_NAME"; then
  echo "error: registry JSON missing blueprint $BLUEPRINT_NAME" >&2
  exit 1
fi
if ! printf '%s' "$FLEET_JSON" | grep -q "$BLUEPRINT_VERSION"; then
  echo "error: registry JSON missing blueprint version $BLUEPRINT_VERSION" >&2
  exit 1
fi
if ! printf '%s' "$FLEET_JSON" | grep -Fq "$REPO_URL"; then
  echo "error: registry JSON missing repo URL $REPO_URL" >&2
  exit 1
fi

echo "==> Render fleet-manifests (GoldenPathRepo YAML)"
(
  cd "$ROOT/engine"
  uv run repave fleet-manifests \
    --repo-root "$ROOT" \
    --output "$MANIFESTS" \
    --namespace repave-system \
    --kustomization \
    --gitops-readme \
    --prune
)

shopt -s nullglob
YAML_FILES=("$MANIFESTS"/*.yaml)
shopt -u nullglob
if [[ ${#YAML_FILES[@]} -eq 0 ]]; then
  echo "error: no YAML manifests under $MANIFESTS" >&2
  exit 1
fi

MATCHED=0
for yaml in "${YAML_FILES[@]}"; do
  base="$(basename "$yaml")"
  if [[ "$base" == "kustomization.yaml" ]]; then
    continue
  fi
  if grep -q "kind: GoldenPathRepo" "$yaml" \
    && grep -q "blueprintName: $BLUEPRINT_NAME" "$yaml" \
    && grep -Fq "repoURL: $REPO_URL" "$yaml" \
    && grep -q "repave.dev/managed-by: repave-fleet" "$yaml"; then
    MATCHED=1
    echo "OK: $yaml"
    break
  fi
done

if [[ "$MATCHED" -ne 1 ]]; then
  echo "error: no GoldenPathRepo manifest matched $REPO_URL / $BLUEPRINT_NAME" >&2
  ls -la "$MANIFESTS" >&2 || true
  exit 1
fi

if [[ "${VALIDATE_GITHUB_REPO_FLEET_UNITS:-}" == "1" ]]; then
  # Do not leak the smoke registry path into tests that assert fleet-disabled.
  unset REPAVE_FLEET_FILE
  echo "==> Engine unit tests (github-repo fleet + fleet manifests)"
  (
    cd "$ROOT/engine"
    PATH="$ROOT/.gate-tools/bin:$PATH" uv run pytest \
      tests/test_github_repo_fleet.py \
      tests/test_fleet_manifests.py \
      -q --no-cov
  )
  echo "==> Operator fleetsync unit tests"
  (
    cd "$ROOT/operator"
    go test ./internal/fleetsync/... -count=1
  )
fi

echo
echo "Tier A validation passed."
echo "Next: make chart-smoke-fleet-snapshot  # Tier B (kind)"
echo "Docs: docs/operations/github-repo-fleet-validation.md"
