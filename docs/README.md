# repave documentation

Product and engineering docs for the repave monorepo. The [README](../README.md)
is the front door; use this index when you need depth.

## Start here

| Doc | Audience | Contents |
| --- | --- | --- |
| [Quickstart](quickstart.md) | New users | Docker Compose, `make serve`, first generate, CLI |
| [Concepts](concepts.md) | Everyone | Golden paths, blueprints, governance-by-construction, provenance |
| [Module repositories](module-repositories.md) | Adopters | `REPAVE_MODULES_ROOT`, GitHub org, naming |
| [Engine capabilities](engine-capabilities.md) | Platform engineers | Gates, CLI, blueprints, CI |
| [Roadmap](roadmap.md) | Planning | Shipped releases, planned themes, parking lot |
| [Portal design](portal-design.md) | UX / frontend | Shell, catalog, forms, results |

## Run and operate

| Doc | Contents |
| --- | --- |
| [Operator overview](operator-overview.md) | CRDs, drift, remediation PRs |
| [Operator local dev](operator-local-dev.md) | envtest, kind, running the controller locally |
| [Operator GA scope](operator-ga.md) | v1.17 GA criteria and slices |
| [Operator standards](operator-standards.md) | CRD and controller conventions |
| [Operations](operations/README.md) | Metrics, audit, k8s starter manifests |
| [Auth service mode](auth-service-mode.md) | OIDC, roles, session config |

## Integrations

| Doc | Contents |
| --- | --- |
| [Backstage](backstage.md) | Catalog registration, HTTP generate API |

## Contributing

| Doc | Contents |
| --- | --- |
| [Releases](releases.md) | semantic-release, Release workflow, maintainer tokens |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Commits, quality gate, local dev |

## Portal screenshots

Marketing captures for the root README: [images/portal/README.md](images/portal/README.md)

Refresh with a running portal on `:8088`:

```bash
./scripts/capture_portal_screenshots.sh
```
