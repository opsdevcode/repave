#!/usr/bin/env bash
# Pinned gate CLIs for portal dry-run and CI (keep aligned with engine/ci_toolchain.py).
set -euo pipefail

TERRAFORM_VERSION="${TERRAFORM_VERSION:-1.9.8}"
TFLINT_VERSION="${TFLINT_VERSION:-0.55.1}"
CONFTEST_VERSION="${CONFTEST_VERSION:-0.56.0}"
HELM_VERSION="${HELM_VERSION:-3.14.4}"
CHECKOV_PIP_SPEC="${CHECKOV_PIP_SPEC:-checkov>=3.2.0}"

INSTALL_TERRAFORM="${INSTALL_TERRAFORM:-1}"
INSTALL_ANSIBLE="${INSTALL_ANSIBLE:-1}"
INSTALL_HELM="${INSTALL_HELM:-1}"
DEST="${DEST:-/usr/local/bin}"
PIP="${PIP:-pip}"

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64)
    tf_arch="amd64"
    tflint_arch="amd64"
    conf_arch="x86_64"
    helm_arch="amd64"
    ;;
  aarch64|arm64)
    tf_arch="arm64"
    tflint_arch="arm64"
    conf_arch="arm64"
    helm_arch="arm64"
    ;;
  *)
    echo "unsupported architecture: $arch" >&2
    exit 1
    ;;
esac

install_bin() {
  local src="$1"
  local name
  name="$(basename "$src")"
  if [[ -w "$DEST" ]]; then
    install -m 0755 "$src" "$DEST/$name"
  else
    sudo install -m 0755 "$src" "$DEST/$name"
  fi
}

if [[ "$INSTALL_TERRAFORM" == "1" ]]; then
  tmp="$(mktemp -d)"
  curl -fsSL \
    "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${tf_arch}.zip" \
    -o "$tmp/terraform.zip"
  unzip -q "$tmp/terraform.zip" -d "$tmp"
  install_bin "$tmp/terraform"
  curl -fsSL \
    "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_${tflint_arch}.zip" \
    -o "$tmp/tflint.zip"
  unzip -q "$tmp/tflint.zip" -d "$tmp"
  install_bin "$tmp/tflint"
  curl -fsSL \
    "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${conf_arch}.tar.gz" \
    | tar xz -C "$tmp" conftest
  install_bin "$tmp/conftest"
  rm -rf "$tmp"
  "$PIP" install "$CHECKOV_PIP_SPEC"
fi

if [[ "$INSTALL_ANSIBLE" == "1" ]]; then
  "$PIP" install "ansible-lint>=24.0" "yamllint>=1.35" "ansible-core>=2.16"
fi

if [[ "$INSTALL_HELM" == "1" ]]; then
  tmp_helm="$(mktemp -d)"
  curl -fsSL \
    "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${helm_arch}.tar.gz" \
    | tar xz -C "$tmp_helm"
  install_bin "$tmp_helm/linux-${helm_arch}/helm"
  rm -rf "$tmp_helm"
fi

echo "Gate toolchain installed (terraform=${TERRAFORM_VERSION}, tflint=${TFLINT_VERSION}, conftest=${CONFTEST_VERSION}, helm=${HELM_VERSION})."
