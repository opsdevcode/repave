#!/usr/bin/env bash
# Capture portal PNGs into docs/images/portal/ (server must be on :8088).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/docs/images/portal"
BASE="${REPAVE_PORTAL_URL:-http://127.0.0.1:8088}"

if ! curl -sf "$BASE/health" >/dev/null; then
  echo "repave portal not reachable at $BASE (start repave serve or docker compose)" >&2
  exit 1
fi

mkdir -p "$OUT"

run_capture() {
  local url="$1"
  local file="$2"
  npx --yes playwright screenshot "$url" "$OUT/$file" --viewport-size=1280,800
}

run_capture "$BASE/" home-catalog.png
run_capture "$BASE/blueprints/terraform-module-generic" blueprint-form.png
run_capture "$BASE/update" update-repo.png
run_capture "$BASE/import" import-repo.png

echo "Capturing generate result (requires REPAVE_GITHUB_ORG and REPAVE_MODULES_ROOT)…"
cd "$ROOT/engine" && REPAVE_GITHUB_ORG="${REPAVE_GITHUB_ORG:-opsdevcode}" \
  REPAVE_MODULES_ROOT="${REPAVE_MODULES_ROOT:-$HOME/repave-modules}" \
  uv run --with playwright python ../scripts/capture_generate_result.py

echo "Capturing CLI dry-run screenshot…"
cd "$ROOT/engine" && REPAVE_GITHUB_ORG="${REPAVE_GITHUB_ORG:-opsdevcode}" \
  REPAVE_MODULES_ROOT="${REPAVE_MODULES_ROOT:-$HOME/repave-modules}" \
  uv run --with playwright python ../scripts/capture_cli_screenshot.py

echo "Wrote PNGs under $OUT and docs/images/cli/"
