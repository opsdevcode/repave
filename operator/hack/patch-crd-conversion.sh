#!/usr/bin/env bash
# Re-apply CRD conversion webhook clientConfig after controller-gen (it does not emit conversion).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONVERSION_FILE="${ROOT}/hack/crd-conversion-snippet.yaml"

for crd in "${ROOT}/config/crd/bases"/repave.dev_*.yaml; do
  if grep -q '^  conversion:' "${crd}"; then
    continue
  fi
  tmp="$(mktemp)"
  awk -v snippet="${CONVERSION_FILE}" '
    /^  scope: Namespaced/ {
      print
      while ((getline line < snippet) > 0) print line
      close(snippet)
      next
    }
    { print }
  ' "${crd}" >"${tmp}"
  mv "${tmp}" "${crd}"
done
