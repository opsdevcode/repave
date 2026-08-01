# repave-engine

**Gate-toolchain worker image** for the [repave](https://github.com/opsdevcode/repave) platform.

```text
ghcr.io/opsdevcode/repave-engine:<tag>
```

Built from [`deploy/local/Dockerfile`](../../local/Dockerfile) with `INSTALL_GATE_TOOLCHAIN=1` and
`INCLUDE_CORPUS=0`. Use this image where generation runs **must execute blueprint gates**
(Terraform, Checkov, OPA/conftest, tflint, infracost, ansible-lint, etc.) — not in the portal
process.

## Role in a deployment

| Workload | Typical chart values |
| --- | --- |
| Async run **worker** / per-run **Jobs** | `workerImage.repository`, `runJob.workerImage` |
| `kind: live_plan` terraform plan + OPA on plan JSON | Worker Job with optional Secret `envFrom` |
| Bundle or blueprint generation in **worker mode** | Claims runs from the queue; needs gate CLIs |

The **portal** Deployment should use [`repave-engine-portal`](../repave-engine-portal/README.md)
instead — slimmer, no gate binaries, lower attack surface.

## What is inside

- Python 3.12 + editable `repave-engine` (`repave` CLI, FastAPI portal backend)
- Pinned **gate toolchain** from [`deploy/local/install-gate-toolchain.sh`](../../local/install-gate-toolchain.sh)
- **No** embedded generation corpus — mount [`repave-corpus`](../repave-corpus/README.md) at
  `/app` (initContainer) or set `REPAVE_REPO_ROOT` to a volume with `blueprints/`, `standards/`,
  `policy/`, `schemas/`

## Pull and verify

```bash
crane digest ghcr.io/opsdevcode/repave-engine:v2.2.1
docker pull ghcr.io/opsdevcode/repave-engine:v2.2.1
docker run --rm ghcr.io/opsdevcode/repave-engine:v2.2.1 repave doctor --strict --repo-root /app
```

## Helm

Decomposed chart example: [`deploy/k8s/chart/values-decomposed.yaml`](../../k8s/chart/values-decomposed.yaml).

Digest pinning: [`values-digest-pinned.yaml`](../../k8s/chart/values-digest-pinned.yaml).

## Source

Monorepo: [opsdevcode/repave](https://github.com/opsdevcode/repave) · Engine package:
[`engine/`](../../../engine/)
