# Hosted Backstage (repave)

In-repo Backstage app for the hosted IDP ([ADR 011](../docs/adr/011-hosted-backstage-idp.md)).
Operator guide: [`docs/backstage.md`](../docs/backstage.md).

```bash
yarn install
export REPAVE_API_BASE_URL=http://127.0.0.1:8088   # optional; catalog provider idles if unset
yarn start
```

`make serve` / `repave generate` do **not** require this tree.

```bash
# after yarn tsc && yarn build:backend
docker build -f packages/backend/Dockerfile -t ghcr.io/opsdevcode/repave-backstage:local .
```

Quality: `make backstage-lint` from the monorepo root, or `yarn tsc && yarn lint:all && yarn test --watch=false` here.
