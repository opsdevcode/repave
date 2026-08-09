#!/usr/bin/env bash
# Copy the platform dev profile into repave.config.yaml (gitignored) at repo root.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/examples/platform-dev/repave.config.platform-dev.yaml"
DEST="$ROOT/repave.config.yaml"
cp "$SRC" "$DEST"
echo "Installed platform dev config: $DEST"
echo "Start the portal: make serve  →  http://127.0.0.1:8089"
echo "Docs: docs/platform-console.md"
