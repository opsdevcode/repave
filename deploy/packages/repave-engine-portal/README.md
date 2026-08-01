# repave-engine-portal

**Portal and API-only image** for the [repave](https://github.com/opsdevcode/repave) platform.

```text
ghcr.io/opsdevcode/repave-engine-portal:<tag>
```

Built from [`deploy/local/Dockerfile`](../../local/Dockerfile) with `INSTALL_GATE_TOOLCHAIN=0` and
`INCLUDE_CORPUS=0`. Runs `repave serve` — the web UI, `/api/v1`, and `/api/v2` — without
shipping Terraform, Checkov, or other gate CLIs.

## Role in a deployment

| Workload | Typical chart values |
| --- | --- |
| Portal **Deployment** (multi-replica safe) | `image.repository` in `values-portal.yaml` / decomposed overlays |
| Enqueue-only async runs | Portal submits to the queue; **workers** execute gates |

Set `executionMode: worker` (or `durability.external_workers`) so generation and
`kind: live_plan` runs execute in [`repave-engine`](../repave-engine/README.md) Jobs, not in
this container.

## What is inside

- Python 3.12 + `repave-engine` (portal templates, static assets, API routers)
- **No** gate toolchain (`repave doctor --strict` is not run at image build)
- **No** embedded corpus — pair with [`repave-corpus`](../repave-corpus/README.md) when the
  chart uses a corpus initContainer

## Pull

```bash
docker pull ghcr.io/opsdevcode/repave-engine-portal:v2.2.1
docker run --rm -p 8088:8088 ghcr.io/opsdevcode/repave-engine-portal:v2.2.1
```

Open http://localhost:8088 (read-only catalog works without `GITHUB_TOKEN`; publish requires a
token).

## Helm

[`deploy/k8s/chart/values-portal.yaml`](../../k8s/chart/values-portal.yaml) ·
[`values-decomposed.yaml`](../../k8s/chart/values-decomposed.yaml)

## Source

Monorepo: [opsdevcode/repave](https://github.com/opsdevcode/repave)
