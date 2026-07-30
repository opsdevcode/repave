#!/usr/bin/env bash
# Inject caBundle into CRD copies before kubectl apply (conversion webhook TLS).
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <ca.crt> <crd-dir> [output-dir]" >&2
  exit 1
fi

CA_FILE="$1"
CRD_SRC="$2"
OUT_DIR="${3:-${CRD_SRC}}"
CA_BUNDLE="$(base64 <"${CA_FILE}" | tr -d '\n')"

mkdir -p "${OUT_DIR}"
shopt -s nullglob
for crd in "${CRD_SRC}"/repave.dev_*.yaml; do
  base="$(basename "${crd}")"
  out="${OUT_DIR}/${base}"
  if grep -q 'caBundle:' "${crd}"; then
    sed "s|caBundle: .*|caBundle: ${CA_BUNDLE}|" "${crd}" >"${out}"
  else
    sed "/clientConfig:/a\\
        caBundle: ${CA_BUNDLE}
" "${crd}" >"${out}"
  fi
done
