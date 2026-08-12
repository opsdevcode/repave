# repave documentation

Product and engineering docs for the repave monorepo. The [README](../README.md) is the
pitch (why the name, what the IDP is today, and what it is becoming). This index is depth —
start with [Concepts](concepts.md) for the product model.

## Start here

| Doc | Audience | Contents |
| --- | --- | --- |
| [Quickstart](quickstart.md) | New users | Docker Compose, `make serve`, first generate, CLI |
| [Concepts](concepts.md) | Everyone | IDP model, golden paths, gates, provenance, operator |
| [Hosted demo (EKS)](hosted-demo.md) | Live demos on repave-prod | Auth0, async workers, https://repave.opsdevco.de |
| [Hosted demo library seed](hosted-demo-library.md) | Seed opsdevcode estate | Publish TF/Ansible/policy repos + fleet registry |
| [Seven-minute demo (acts 1–6)](seven-minute-demo.md) | Live demos | Full portal arc for stakeholder meetings |
| [Sales demo runbook](sales-demo.md) | Field / leadership demos | Narrative, talking points, operator boundaries |
| [Policy golden paths demo](policy-golden-paths-demo.md) | Security / platform | Checkov, OPA, Azure Policy standalone paths |
| [Demo verification](demo-verification.md) | Maintainers / pre-release | Portal smoke checklist, screenshots, operator e2e |

## Platform model

| Doc | Contents |
| --- | --- |
| [Concepts](concepts.md) | IDP framing, lifecycle, blueprints, governance-by-construction |
| [Engine capabilities](engine-capabilities.md) | Gates, CLI, blueprints, CI |
| [Blueprint versioning](blueprint-versioning.md) | v2 schema freeze, `metadata.version` semver policy |
| [Module repositories](module-repositories.md) | `REPAVE_MODULES_ROOT`, GitHub org, naming |
| [Policy customization](../standards/policy/customization.md) | Profiles, catalog, portal, provenance, config floors |
| [FinOps enablement](finops.md) | Tags, estimates, showback, FOCUS boundaries (v1.90–v1.94) |
| [Portal design](portal-design.md) | Shell, catalog, forms, results |
| [Brand](brand/README.md) | Converge identity, palette, assets, UI/CLI accent rules |
| [Service catalog](service-catalog.md) | Maturity, teams, sandboxes, initiatives (ADR 006) |
| [API v2](api-v2.md) | Stable HTTP surface; v1 deprecation |
| [API v1 migration](api-v1-migration.md) | Sunset timeline and v1 → v2 endpoint map |
| [repave.config v1](repave-config-v1.md) | Config `apiVersion`, hosted SQL, JSONL export mirrors |
| [Roadmap](roadmap.md) | Open work, path overview, parking lot, v3/v4 boundaries |
| [Roadmap archive](roadmap-archive.md) | Historical shipped theme writeups |

## Day-2 and estate

| Doc | Contents |
| --- | --- |
| [Import an existing repo](import.md) | `repave import`, detection, destination rules, reviewable PR |
| [Add a component to a governed repo](add.md) | `repave add`, multi-component `repave.yaml`, portal add action |
| [Fleet registry](fleet-registry.md) | `repave register`, registry storage, fleet API |
| [Operator overview](operator-overview.md) | CRDs, drift, remediation PRs (`localPath` + `repoURL`) |
| [Operator local dev](operator-local-dev.md) | envtest, kind, running the controller locally |
| [Operator GA scope](operator-ga.md) | v1.17 GA criteria and slices |
| [Policy repos and operator](operator-policy-estate.md) | Policy artifacts, inventory, upgrade drift |
| [Operator standards](operator-standards.md) | CRD and controller conventions |
| [State custody and resource graph](state-graph.md) | Authoritative state store, graph, gate-blocked transactions |
| [Operations](operations/README.md) | Metrics, audit, k8s starter manifests |
| [Auth service mode](auth-service-mode.md) | OIDC, roles, session config |
| [Supply chain](supply-chain.md) | SHA-pinned Actions, digest-pinned images, Helm `image.digest` |
| [ADR index](adr/README.md) | Architecture decisions |

## Integrations

| Doc | Contents |
| --- | --- |
| [Backstage](backstage.md) | Catalog registration, HTTP generate API |

## Contributing

| Doc | Contents |
| --- | --- |
| [Releases](releases.md) | semantic-release, roadmap ↔ semver alignment, Release workflow |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Commits, quality gate, local dev |

## Portal and CLI screenshots

Marketing captures for the root README:

- Index and one-command refresh: [images/README.md](images/README.md)
- Portal UI: [images/portal/README.md](images/portal/README.md)
- CLI dry-run: [images/cli/README.md](images/cli/README.md)
