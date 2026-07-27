#!/usr/bin/env bash
# Install gate CLIs into repo-local .gate-tools/bin (macOS).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${DEST:-$REPO_ROOT/.gate-tools/bin}"
HELM_VERSION="${HELM_VERSION:-3.14.4}"

mkdir -p "$DEST"

arch="$(uname -m)"
case "$arch" in
  arm64|aarch64) helm_arch="arm64" ;;
  x86_64) helm_arch="amd64" ;;
  *)
    echo "unsupported architecture: $arch" >&2
    exit 1
    ;;
esac

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

curl -fsSL "https://get.helm.sh/helm-v${HELM_VERSION}-darwin-${helm_arch}.tar.gz" \
  | tar xz -C "$tmp"
install -m 0755 "$tmp/darwin-${helm_arch}/helm" "$DEST/helm"

echo "Installed helm ${HELM_VERSION} to ${DEST}"
echo "make test prepends this directory to PATH automatically."
