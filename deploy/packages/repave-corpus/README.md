# repave-corpus

**Versioned generation corpus** OCI artifact for [repave](https://github.com/opsdevcode/repave).

```text
ghcr.io/opsdevcode/repave-corpus:<tag>
```

Built from [`deploy/local/Dockerfile.corpus`](../../local/Dockerfile.corpus) (Alpine + static
tree). Contains only:

- `blueprints/`
- `standards/`
- `policy/`
- `schemas/`

No Python runtime, no gate CLIs, no portal code.

## Role in a deployment

Decomposed portal/worker charts mount this image as an **initContainer** (or sidecar volume
source) so [`repave-engine`](../repave-engine/README.md) and
[`repave-engine-portal`](../repave-engine-portal/README.md) stay small and corpus updates ship
independently of application code.

| Setting | Chart field |
| --- | --- |
| Corpus image | `corpus.repository`, `corpus.tag`, optional `corpus.digest` |
| Mount path | `/app` (overlays `blueprints`, `standards`, `policy`, `schemas`) |

Pin **`corpus.digest`** in production so blueprint/policy changes are deliberate — see
[`docs/supply-chain.md`](../../../docs/supply-chain.md).

## Pull

```bash
crane digest ghcr.io/opsdevcode/repave-corpus:v2.2.1
docker pull ghcr.io/opsdevcode/repave-corpus:v2.2.1
docker run --rm ghcr.io/opsdevcode/repave-corpus:v2.2.1 ls /app/blueprints
```

## Local development

Compose and the all-in-one engine image embed the corpus at build time (`INCLUDE_CORPUS=1`).
Kubernetes decomposed mode splits it out for faster portal/worker rollouts.

## Source

Monorepo: [opsdevcode/repave](https://github.com/opsdevcode/repave)
