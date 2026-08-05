#!/usr/bin/env bash
# Create or update the Kubernetes Secret used by the portal chart for Auth0 OIDC.
#
# Required env:
#   REPAVE_SESSION_SECRET      — 32+ random bytes (openssl rand -hex 32)
#   REPAVE_OIDC_CLIENT_SECRET  — Auth0 Application client secret
#
# Optional env:
#   REPAVE_NAMESPACE           — default: repave
#   REPAVE_SECRET_NAME         — default: repave-secrets
#   GITHUB_TOKEN               — PAT or leave empty if using GitHub App keys
#   REPAVE_API_TOKEN           — bearer for CronJobs / machine callers (admin role)
#   REPAVE_GITHUB_APP_ID / REPAVE_GITHUB_APP_INSTALLATION_ID / REPAVE_GITHUB_APP_PRIVATE_KEY
#
# Usage:
#   export REPAVE_SESSION_SECRET="$(openssl rand -hex 32)"
#   export REPAVE_OIDC_CLIENT_SECRET='...'
#   export REPAVE_API_TOKEN="$(openssl rand -hex 24)"
#   ./deploy/k8s/hack/bootstrap-auth0-secrets.sh
set -euo pipefail

NAMESPACE="${REPAVE_NAMESPACE:-repave}"
SECRET_NAME="${REPAVE_SECRET_NAME:-repave-secrets}"

if [[ -z "${REPAVE_SESSION_SECRET:-}" ]]; then
  echo "set REPAVE_SESSION_SECRET (e.g. openssl rand -hex 32)" >&2
  exit 1
fi
if [[ -z "${REPAVE_OIDC_CLIENT_SECRET:-}" ]]; then
  echo "set REPAVE_OIDC_CLIENT_SECRET from the Auth0 Application" >&2
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is required" >&2
  exit 1
fi

args=(
  create secret generic "${SECRET_NAME}"
  --namespace "${NAMESPACE}"
  --dry-run=client
  -o yaml
  --from-literal=session-secret="${REPAVE_SESSION_SECRET}"
  --from-literal=oidc-client-secret="${REPAVE_OIDC_CLIENT_SECRET}"
)

if [[ -n "${GITHUB_TOKEN:-}" ]]; then
  args+=(--from-literal=github-token="${GITHUB_TOKEN}")
else
  args+=(--from-literal=github-token="")
fi

if [[ -n "${REPAVE_API_TOKEN:-}" ]]; then
  args+=(--from-literal=api-token="${REPAVE_API_TOKEN}")
fi

if [[ -n "${REPAVE_GITHUB_APP_ID:-}" ]]; then
  args+=(--from-literal=github-app-id="${REPAVE_GITHUB_APP_ID}")
fi
if [[ -n "${REPAVE_GITHUB_APP_INSTALLATION_ID:-}" ]]; then
  args+=(--from-literal=github-app-installation-id="${REPAVE_GITHUB_APP_INSTALLATION_ID}")
fi
if [[ -n "${REPAVE_GITHUB_APP_PRIVATE_KEY:-}" ]]; then
  args+=(--from-literal=github-app-private-key="${REPAVE_GITHUB_APP_PRIVATE_KEY}")
fi

kubectl "${args[@]}" | kubectl apply -f -

echo "Applied secret/${SECRET_NAME} in namespace ${NAMESPACE}"
echo "Point Helm at it: --set secrets.existingSecret=${SECRET_NAME}"
