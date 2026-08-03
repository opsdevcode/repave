# Published container images (`ghcr.io/opsdevcode`)

OCI images built from [`.github/workflows/container.yml`](../../.github/workflows/container.yml)
on `main` and semver tags (`v*.*.*`). Pin by digest in Helm — see
[`docs/supply-chain.md`](../../docs/supply-chain.md).

Helm charts publish as OCI artifacts from
[`.github/workflows/chart-publish.yml`](../../.github/workflows/chart-publish.yml) on semver tags
only (`oci://ghcr.io/opsdevcode/charts`).

| Package | Image / chart | README |
| --- | --- | --- |
| **repave-engine** | `ghcr.io/opsdevcode/repave-engine` | [repave-engine/README.md](repave-engine/README.md) |
| **repave-engine-portal** | `ghcr.io/opsdevcode/repave-engine-portal` | [repave-engine-portal/README.md](repave-engine-portal/README.md) |
| **repave-corpus** | `ghcr.io/opsdevcode/repave-corpus` | [repave-corpus/README.md](repave-corpus/README.md) |
| **repave-operator** | `ghcr.io/opsdevcode/repave-operator` | [repave-operator/README.md](repave-operator/README.md) |
| **repave** (Helm) | `oci://ghcr.io/opsdevcode/charts/repave` | [deploy/k8s/chart/README.md](../k8s/chart/README.md) |
| **repave-operator** (Helm) | `oci://ghcr.io/opsdevcode/charts/repave-operator` | [deploy/k8s/operator-chart/README.md](../k8s/operator-chart/README.md) |

Each image sets `org.opencontainers.image.source` to this repository and a package-specific
`org.opencontainers.image.description` at publish time.
