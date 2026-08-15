# repave-backstage

Hosted [Backstage](https://backstage.io/) IDP UI for
[repave](https://github.com/opsdevcode/repave) ([ADR 011](../../../docs/adr/011-hosted-backstage-idp.md)).

```text
ghcr.io/opsdevcode/repave-backstage:<tag>
```

Image from [`backstage/packages/backend/Dockerfile`](../../../backstage/packages/backend/Dockerfile)
with context `backstage/` after `yarn tsc && yarn build:backend`. Guest auth by
default; set `AUTH0_CLIENT_ID` to load Auth0. Talks to the engine over `/api/v2`
only.

## What it does

- Scaffolder action `repave:generate` → `POST /api/v2/generate`
- Catalog provider + lineage from `GET /api/v2/catalog/entities`
- Sandbox, runs, and upgrade preview pages via the Backstage proxy

Does **not** scrape HTML forms or call `/api/v1`. CLI and `/api/v2` stay the
control plane. Chart flag `repave.backstage.enabled` stays **default off**.

## Deploy

Helm overlay: [`deploy/k8s/chart/values-backstage.yaml`](../../k8s/chart/values-backstage.yaml)

```bash
docker pull ghcr.io/opsdevcode/repave-backstage:<tag>
helm upgrade --install repave deploy/k8s/chart \
  -f deploy/k8s/chart/values-backstage.yaml \
  --set repave.output.githubOrg=your-org \
  --set secrets.existingSecret=repave-secrets
```

Local kind smoke still builds the image: `make chart-smoke-backstage`.

## Docs

- [`docs/backstage.md`](../../../docs/backstage.md)
- [`docs/supply-chain.md`](../../../docs/supply-chain.md)

## Source

Monorepo: [opsdevcode/repave](https://github.com/opsdevcode/repave) ·
[`backstage/`](../../../backstage/)
