# repave documentation

Product and engineering docs for the repave monorepo. The [README](../README.md)
is the front door; use this index when you need depth.

## Start here

| Doc | Audience | Contents |
| --- | --- | --- |
| [Quickstart](quickstart.md) | New users | Docker Compose, `make serve`, first generate, CLI |
| [Seven-minute demo (acts 1–6)](seven-minute-demo.md) | Live demos | Full portal arc for stakeholder meetings |
| [Policy golden paths demo](policy-golden-paths-demo.md) | Security / platform | Checkov, OPA, Azure Policy standalone paths |
| [Sales demo runbook](sales-demo.md) | Field / leadership demos | Narrative, talking points, operator boundaries |
| [Demo verification](demo-verification.md) | Maintainers / pre-release | Portal smoke checklist, screenshots, operator e2e |
| [Concepts](concepts.md) | Everyone | Golden paths, blueprints, governance-by-construction, provenance |
| [Blueprint versioning](blueprint-versioning.md) | Blueprint authors | v2 schema freeze, `metadata.version` semver policy |
| [Module repositories](module-repositories.md) | Adopters | `REPAVE_MODULES_ROOT`, GitHub org, naming |
| [Engine capabilities](engine-capabilities.md) | Platform engineers | Gates, CLI, blueprints, CI |
| [Policy customization](../standards/policy/customization.md) | Platform / security | Profiles, catalog, portal, provenance, config floors |
| [Roadmap](roadmap.md) | Planning | Shipped releases, planned themes, parking lot |
| [Portal design](portal-design.md) | UX / frontend | Shell, catalog, forms, results |

## Run and operate

| Doc | Contents |
| --- | --- |
| [Import an existing repo](import.md) | `repave import`, detection, destination rules, reviewable PR |
| [Fleet registry](fleet-registry.md) | `repave register`, registry storage, fleet API |
| [Operator overview](operator-overview.md) | CRDs, drift, remediation PRs |
| [Operator local dev](operator-local-dev.md) | envtest, kind, running the controller locally |
| [Operator GA scope](operator-ga.md) | v1.17 GA criteria and slices |
| [Policy repos and operator](operator-policy-estate.md) | Policy artifacts, inventory, upgrade drift |
| [ADR index](adr/README.md) | Architecture decisions (e.g. `repoURL` inventory) |
| [Operator standards](operator-standards.md) | CRD and controller conventions |
| [Operations](operations/README.md) | Metrics, audit, k8s starter manifests |
| [Auth service mode](auth-service-mode.md) | OIDC, roles, session config |
| [Supply chain](supply-chain.md) | SHA-pinned Actions, digest-pinned images, Helm `image.digest` |

## Integrations

| Doc | Contents |
| --- | --- |
| [Backstage](backstage.md) | Catalog registration, HTTP generate API |

## Contributing

| Doc | Contents |
| --- | --- |
| [Releases](releases.md) | semantic-release, Release workflow, maintainer tokens |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Commits, quality gate, local dev |

## Portal and CLI screenshots

Marketing captures for the root README:

- Index and one-command refresh: [images/README.md](images/README.md)
- Portal UI: [images/portal/README.md](images/portal/README.md)
- CLI dry-run: [images/cli/README.md](images/cli/README.md)
