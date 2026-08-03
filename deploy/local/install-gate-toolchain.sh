#!/usr/bin/env bash
# Pinned gate CLIs for portal dry-run and CI (pins: deploy/local/gate-toolchain-pins.env).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=gate-toolchain-pins.env
source "${SCRIPT_DIR}/gate-toolchain-pins.env"
CHECKOV_PIP_SPEC="${CHECKOV_PIP_SPEC:-checkov==${CHECKOV_VERSION}}"

INSTALL_TERRAFORM="${INSTALL_TERRAFORM:-1}"
INSTALL_ANSIBLE="${INSTALL_ANSIBLE:-1}"
INSTALL_ANSIBLE_COLLECTIONS="${INSTALL_ANSIBLE_COLLECTIONS:-1}"
INSTALL_HELM="${INSTALL_HELM:-1}"
INSTALL_KUBECTL="${INSTALL_KUBECTL:-1}"
INSTALL_ACTIONLINT="${INSTALL_ACTIONLINT:-1}"
DEST="${DEST:-/usr/local/bin}"
GATE_PIP_TARGET="${GATE_PIP_TARGET:-}"

# Last resort behind a TLS-inspecting proxy. Prefer trusting the corporate CA
# (deploy/local/certs for the compose image) over turning verification off.
REPAVE_TLS_INSECURE="${REPAVE_TLS_INSECURE:-0}"

CURL_GET=(curl -fsSL)
GALAXY_INSTALL=(ansible-galaxy collection install)
UV_PIP_INSTALL=(uv pip install --system --no-cache)
PIP_INSTALL=(python -m pip install)
if [[ -n "$GATE_PIP_TARGET" ]]; then
  mkdir -p "$GATE_PIP_TARGET"
  UV_PIP_INSTALL=(uv pip install --target "$GATE_PIP_TARGET" --no-cache)
  PIP_INSTALL=(python -m pip install --target "$GATE_PIP_TARGET")
fi

if [[ "$REPAVE_TLS_INSECURE" == "1" ]]; then
  echo "WARNING: REPAVE_TLS_INSECURE=1 - TLS verification disabled for toolchain downloads." >&2
  CURL_GET+=(--insecure)
  GALAXY_INSTALL+=(--ignore-certs)
  UV_PIP_INSTALL+=(--allow-insecure-host pypi.org --allow-insecure-host files.pythonhosted.org)
  PIP_INSTALL+=(--trusted-host pypi.org --trusted-host files.pythonhosted.org)
fi

pip_install() {
  if [[ "${USE_UV_PIP:-0}" == "1" ]]; then
    "${UV_PIP_INSTALL[@]}" "$@"
  else
    "${PIP_INSTALL[@]}" "$@"
  fi
}

arch="$(uname -m)"
case "$arch" in
  x86_64|amd64)
    tf_arch="amd64"
    tflint_arch="amd64"
    conf_arch="x86_64"
    helm_arch="amd64"
    kubectl_arch="amd64"
    ;;
  aarch64|arm64)
    tf_arch="arm64"
    tflint_arch="arm64"
    conf_arch="arm64"
    helm_arch="arm64"
    kubectl_arch="arm64"
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
  "${CURL_GET[@]}" \
    "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_${tf_arch}.zip" \
    -o "$tmp/terraform.zip"
  unzip -q "$tmp/terraform.zip" -d "$tmp"
  install_bin "$tmp/terraform"
  "${CURL_GET[@]}" \
    "https://github.com/terraform-linters/tflint/releases/download/v${TFLINT_VERSION}/tflint_linux_${tflint_arch}.zip" \
    -o "$tmp/tflint.zip"
  unzip -q "$tmp/tflint.zip" -d "$tmp"
  install_bin "$tmp/tflint"
  "${CURL_GET[@]}" \
    "https://github.com/open-policy-agent/conftest/releases/download/v${CONFTEST_VERSION}/conftest_${CONFTEST_VERSION}_Linux_${conf_arch}.tar.gz" \
    | tar xz -C "$tmp" conftest
  install_bin "$tmp/conftest"
  rm -rf "$tmp"
  pip_install "$CHECKOV_PIP_SPEC"
  tmp_ic="$(mktemp -d)"
  "${CURL_GET[@]}" \
    "https://github.com/infracost/cli/releases/download/v${INFRACOST_VERSION}/infracost-linux-${tf_arch}.tar.gz" \
    -o "$tmp_ic/infracost.tgz"
  tar xzf "$tmp_ic/infracost.tgz" -C "$tmp_ic" infracost
  install_bin "$tmp_ic/infracost"
  rm -rf "$tmp_ic"
fi

if [[ -z "${REPO_ROOT:-}" ]]; then
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  if [[ -f "${script_dir}/../../ansible/requirements-gate-collections.yml" ]]; then
    REPO_ROOT="$(cd "${script_dir}/../.." && pwd)"
  else
    echo "Set REPO_ROOT to the repave repository root (ansible gate collections file missing)." >&2
    exit 1
  fi
fi
GATE_COLLECTIONS="${REPO_ROOT}/ansible/requirements-gate-collections.yml"

if [[ "$INSTALL_ANSIBLE" == "1" ]]; then
  pip_install "ansible-lint>=24.0" "yamllint>=1.35" "ansible-core>=2.16"
  if [[ "$INSTALL_ANSIBLE_COLLECTIONS" == "1" ]] && command -v ansible-galaxy >/dev/null 2>&1; then
    if [[ ! -f "$GATE_COLLECTIONS" ]]; then
      echo "The requirements file '${GATE_COLLECTIONS}' does not exist." >&2
      exit 1
    fi
    "${GALAXY_INSTALL[@]}" -r "$GATE_COLLECTIONS"
  fi
fi

if [[ "$INSTALL_HELM" == "1" ]]; then
  tmp_helm="$(mktemp -d)"
  "${CURL_GET[@]}" \
    "https://get.helm.sh/helm-v${HELM_VERSION}-linux-${helm_arch}.tar.gz" \
    | tar xz -C "$tmp_helm"
  install_bin "$tmp_helm/linux-${helm_arch}/helm"
  rm -rf "$tmp_helm"
fi

if [[ "$INSTALL_KUBECTL" == "1" ]]; then
  tmp_kubectl="$(mktemp -d)"
  "${CURL_GET[@]}" \
    "https://dl.k8s.io/release/v${KUBECTL_VERSION}/bin/linux/${kubectl_arch}/kubectl" \
    -o "$tmp_kubectl/kubectl"
  install_bin "$tmp_kubectl/kubectl"
  rm -rf "$tmp_kubectl"
fi

if [[ "$INSTALL_ACTIONLINT" == "1" ]]; then
  case "$OSTYPE" in
    linux-*) al_os=linux ;;
    darwin*) al_os=darwin ;;
    *)
      echo "actionlint install skipped: unsupported OS ${OSTYPE}" >&2
      al_os=""
      ;;
  esac
  if [[ -n "$al_os" ]]; then
    tmp_al="$(mktemp -d)"
    "${CURL_GET[@]}" \
      "https://github.com/rhysd/actionlint/releases/download/v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_${al_os}_${kubectl_arch}.tar.gz" \
      | tar xz -C "$tmp_al" actionlint
    install_bin "$tmp_al/actionlint"
    rm -rf "$tmp_al"
  fi
fi

echo "Gate toolchain installed (terraform=${TERRAFORM_VERSION}, tflint=${TFLINT_VERSION}, conftest=${CONFTEST_VERSION}, helm=${HELM_VERSION}, infracost=${INFRACOST_VERSION}, kubectl=${KUBECTL_VERSION}, actionlint=${ACTIONLINT_VERSION})."
