#!/usr/bin/env bash
# Install the same pinned gate CLIs CI uses into repo-local .gate-tools (macOS or Linux).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export REPO_ROOT
export DEST="${DEST:-$REPO_ROOT/.gate-tools/bin}"
export GATE_PIP_TARGET="${GATE_PIP_TARGET:-$REPO_ROOT/.gate-tools/py-deps}"
export USE_UV_PIP="${USE_UV_PIP:-1}"

mkdir -p "$DEST" "$GATE_PIP_TARGET/bin"
# Stale helm-only layout used .gate-tools/pip and a dangling checkov symlink.
if [[ -L "$DEST/checkov" ]] && [[ ! -e "$DEST/checkov" ]]; then
  rm -f "$DEST/checkov"
fi

exec "$REPO_ROOT/deploy/local/install-gate-toolchain.sh"
