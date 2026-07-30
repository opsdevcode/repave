#!/usr/bin/env bash
# Generate self-signed TLS material for the conversion webhook (kind e2e / local dev).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CERT_DIR="${WEBHOOK_CERT_DIR:-${ROOT}/hack/webhook-certs}"
NAMESPACE="${WEBHOOK_NAMESPACE:-repave-system}"
SECRET_NAME="${WEBHOOK_SECRET_NAME:-webhook-server-cert}"
SERVICE_NAME="${WEBHOOK_SERVICE_NAME:-repave-webhook-service}"

mkdir -p "${CERT_DIR}"

if [[ ! -f "${CERT_DIR}/ca.key" ]]; then
  openssl genrsa -out "${CERT_DIR}/ca.key" 2048
  openssl req -x509 -new -nodes -key "${CERT_DIR}/ca.key" -sha256 -days 3650 \
    -out "${CERT_DIR}/ca.crt" -subj "/CN=repave-webhook-ca"
fi

openssl genrsa -out "${CERT_DIR}/tls.key" 2048
openssl req -new -key "${CERT_DIR}/tls.key" \
  -out "${CERT_DIR}/tls.csr" \
  -subj "/CN=${SERVICE_NAME}.${NAMESPACE}.svc"
openssl x509 -req -in "${CERT_DIR}/tls.csr" \
  -CA "${CERT_DIR}/ca.crt" -CAkey "${CERT_DIR}/ca.key" -CAcreateserial \
  -out "${CERT_DIR}/tls.crt" -days 3650 -sha256 \
  -extfile <(printf "subjectAltName=DNS:%s.%s.svc,DNS:%s.%s.svc.cluster.local" \
    "${SERVICE_NAME}" "${NAMESPACE}" "${SERVICE_NAME}" "${NAMESPACE}")

kubectl create namespace "${NAMESPACE}" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "${NAMESPACE}" create secret tls "${SECRET_NAME}" \
  --cert="${CERT_DIR}/tls.crt" \
  --key="${CERT_DIR}/tls.key" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "OK: webhook TLS secret ${SECRET_NAME} in ${NAMESPACE}"
