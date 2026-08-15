#!/bin/sh
# Guest-only unless AUTH0_CLIENT_ID is set (chart-smoke / local-first).
set -eu
mkdir -p /tmp/backstage-db
set -- --config app-config.yaml --config app-config.production.yaml
if [ -n "${AUTH0_CLIENT_ID:-}" ]; then
  set -- "$@" --config app-config.auth0.yaml
fi
exec node packages/backend "$@"
