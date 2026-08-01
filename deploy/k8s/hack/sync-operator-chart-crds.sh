#!/usr/bin/env bash
# Copy controller-gen CRDs into the operator Helm chart with tpl() placeholders.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SRC="${ROOT}/operator/config/crd/bases"
DEST="${ROOT}/deploy/k8s/operator-chart/files/crd"

mkdir -p "${DEST}"
shopt -s nullglob
for crd in "${SRC}"/repave.dev_*.yaml; do
  base="$(basename "${crd}")"
  out="${DEST}/${base}"
  sed \
    -e 's/namespace: repave-system/namespace: {{ .Release.Namespace }}/g' \
    -e 's/name: repave-webhook-service/name: {{ .Values.service.webhook.name }}/g' \
    "${crd}" >"${out}.tmp"
  awk '
    /clientConfig:/ {
      print
      getline
      if ($0 ~ /service:/) {
        print "        caBundle: {{ required \"webhook.caBundle is required when crds.install=true\" .Values.webhook.caBundle }}"
      }
      print
      next
    }
    { print }
  ' "${out}.tmp" >"${out}"
  rm -f "${out}.tmp"
done

echo "OK: synced operator chart CRDs from ${SRC}"
