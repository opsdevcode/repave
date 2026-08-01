# Published container images (`ghcr.io/opsdevcode`)

OCI images built from [`.github/workflows/container.yml`](../../.github/workflows/container.yml)
on `main` and semver tags (`v*.*.*`). Pin by digest in Helm — see
[`docs/supply-chain.md`](../../docs/supply-chain.md).

| Package | Image | README |
| --- | --- | --- |
| **repave-engine** | `ghcr.io/opsdevcode/repave-engine` | [repave-engine/README.md](repave-engine/README.md) |
| **repave-engine-portal** | `ghcr.io/opsdevcode/repave-engine-portal` | [repave-engine-portal/README.md](repave-engine-portal/README.md) |
| **repave-corpus** | `ghcr.io/opsdevcode/repave-corpus` | [repave-corpus/README.md](repave-corpus/README.md) |
| **repave-operator** | `ghcr.io/opsdevcode/repave-operator` | [repave-operator/README.md](repave-operator/README.md) |

Each image sets `org.opencontainers.image.source` to this repository and a package-specific
`org.opencontainers.image.description` at publish time.
