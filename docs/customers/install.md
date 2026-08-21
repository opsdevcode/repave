# Customer install (self-hosted)

Paid **repave control plane** on your cluster. You get image pull access and a
JSON license file, not a source checkout.

Sales and SKUs: [sales.md](sales.md). Terms: [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

## What you receive

1. GitHub identity (org or machine user) allowed to pull:
   - `ghcr.io/opsdevcode/repave-engine`
   - `ghcr.io/opsdevcode/repave-engine-portal`
   - `ghcr.io/opsdevcode/repave-corpus`
   - `oci://ghcr.io/opsdevcode/charts/repave`
   - operator / Backstage images only if those add-ons are on the invoice
2. `license.json` (`product`, `organization`, `sku`, `expires`)

## Prerequisites

- Kubernetes cluster and Helm 3
- `gh auth login` (or a PAT) for `ghcr.io`
- Postgres (or the chart's supported SQL URL) because **service mode requires a database**
- OIDC (Auth0 or equivalent) for the portal

## Install

```bash
echo "$GHCR_TOKEN" | helm registry login ghcr.io -u TOKEN --password-stdin

kubectl create secret generic repave-license \
  --from-file=license.json=./license.json

helm upgrade --install repave oci://ghcr.io/opsdevcode/charts/repave \
  --version <chart-version> \
  --set repave.auth.serviceMode=true \
  --set repave.license.existingSecret=repave-license \
  --set secrets.existingSecret=repave-secrets
# plus OIDC and database values — see deploy/k8s/chart/README.md
```

The portal Deployment mounts the secret at `/var/run/secrets/repave/license.json`
and sets `REPAVE_LICENSE_FILE`. Missing or expired files fail boot with a
message that names that variable.

## Local demo (not a customer grant)

`make serve` / Docker Compose with `auth.service_mode` off does **not** require
a license file. That path is for the vendor's development, not production.

## Support

Email the address on your invoice. Upgrade PRs stay on **your** GitHub via the
operator when that add-on is licensed.
