#!/usr/bin/env bash
# Create or patch the Kubernetes Secret with a state-store KEK (ADR 004).
#
# Optional env:
#   REPAVE_NAMESPACE           — default: repave
#   REPAVE_SECRET_NAME         — default: repave-secrets
#   REPAVE_STATE_KEK           — base64 32-byte key; generated if unset
#   REPAVE_STATE_KEK_ID        — key label for rotation (default: default)
#
# Usage:
#   export REPAVE_STATE_KEK="$(openssl rand -base64 32)"
#   ./deploy/k8s/hack/bootstrap-state-store-secrets.sh
#
# Store the KEK outside the database it protects (secret manager). Losing the KEK
# makes encrypted state unreadable even if Postgres restores cleanly.
set -euo pipefail

NAMESPACE="${REPAVE_NAMESPACE:-repave}"
SECRET_NAME="${REPAVE_SECRET_NAME:-repave-secrets}"
KEK_ID="${REPAVE_STATE_KEK_ID:-default}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate REPAVE_STATE_KEK" >&2
  exit 1
fi

if [[ -z "${REPAVE_STATE_KEK:-}" ]]; then
  REPAVE_STATE_KEK="$(openssl rand -base64 32)"
  echo "Generated REPAVE_STATE_KEK (save it in your secret manager before continuing)" >&2
fi

if kubectl get secret "${SECRET_NAME}" --namespace "${NAMESPACE}" >/dev/null 2>&1; then
  kubectl patch secret "${SECRET_NAME}" \
    --namespace "${NAMESPACE}" \
    --type merge \
    --patch "$(
      printf '{"stringData":{"state-kek":%s,"state-kek-id":%s}}' \
        "$(printf '%s' "${REPAVE_STATE_KEK}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')" \
        "$(printf '%s' "${KEK_ID}" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
    )"
  echo "Patched secret/${SECRET_NAME} in namespace ${NAMESPACE} (state-kek, state-kek-id)"
else
  kubectl create secret generic "${SECRET_NAME}" \
    --namespace "${NAMESPACE}" \
    --from-literal=state-kek="${REPAVE_STATE_KEK}" \
    --from-literal=state-kek-id="${KEK_ID}" \
    --from-literal=session-secret="" \
    --from-literal=oidc-client-secret="" \
    --from-literal=github-token="" \
    --from-literal=api-token=""
  echo "Created secret/${SECRET_NAME} in namespace ${NAMESPACE}"
fi

echo "Point Helm at it: --set secrets.existingSecret=${SECRET_NAME}"
