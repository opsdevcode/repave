# Blueprint versioning and schema policy

Repave **v2.0.0 contract freeze** treats blueprint manifests and JSON Schemas as
stable integrator contracts. This document is the policy operators and blueprint
authors follow when changing golden paths under `blueprints/`.

Related: [concepts](concepts.md), [CONTRIBUTING.md](../CONTRIBUTING.md),
[`schemas/`](../schemas/), [config v1 extra roots](repave-config-v1.md#extra-blueprint-catalog-roots),
[roadmap — Platform GA](roadmap-archive.md#v200--platform-ga).

## Frozen schemas (v2 line)

The following schemas are **frozen for the v2.0.x line**. Integrators (portal,
CLI, operator, conformance harness) may rely on their shapes until **v3.0.0**:

| Schema | Purpose |
| --- | --- |
| [`schemas/blueprint.schema.json`](../schemas/blueprint.schema.json) | `blueprint.yaml` manifest |
| [`schemas/bundle.schema.json`](../schemas/bundle.schema.json) | Composite bundle manifests |
| [`schemas/golden-path-artifact.schema.json`](../schemas/golden-path-artifact.schema.json) | Generated `repave.yaml` provenance |
| [`schemas/inputs.schema.json`](../schemas/inputs.schema.json) | Headless generate / API input envelope |

**Rules for schema changes during v2:**

- Treat any incompatible change as **breaking** — open an issue or ADR first.
- Prefer additive, backward-compatible JSON Schema updates (new optional properties
  only) when the v2 line must evolve; document the migration in the PR.
  Example: optional `guided_from` on `inputs` (portal Guided identity fill).
- Reserved breaking changes (new required fields, renames, enum removals) ship in
  **v3** with a published migration guide — see
  [breaking at v3.0.0](roadmap.md#breaking-at-v300).

CI validates every shipped `blueprints/*/blueprint.yaml` against
`blueprint.schema.json` on load (`load_blueprint`).

## `metadata.version` semver policy

Each blueprint and bundle declares **`metadata.version`** as semver
`MAJOR.MINOR.PATCH`. That version is copied into generated `repave.yaml`
(`spec.blueprint.version`), fleet desired pins, operator drift detection, and
audit records — bump it when downstream repos should see a new pin target.

### When to bump

| Change | Bump | Examples |
| --- | --- | --- |
| Template or gate output change that **breaks** existing generated repos (removed files, renamed inputs, stricter defaults, dropped gates) | **MAJOR** | Remove an input; rename `module_name` → `name`; change default cloud provider |
| **Additive** behavior: new optional input, new output file, new opt-in gate, new template section that existing repos ignore | **MINOR** | Add optional `tags` input; add `.github/dependabot.yml` to template |
| **Non-breaking** fixes: typo in template comments, docs-only README template text, conformance snapshot refresh with no user-visible diff | **PATCH** | Fix README wording; refresh `conformance.manifest.json` hashes only |

Also bump **`metadata.version`** when:

- **`spec.standard.version`** or policy pack pins change in ways that alter rendered
  output (operator `OutOfDate` remediation targets the catalog pin).
- **Copier template** changes modify files that `provenance-drift` or `docs-drift`
  gates compare (even if inputs are unchanged).

Do **not** bump `metadata.version` for:

- Engine-only fixes that do not change blueprint manifests or template output.
- Conformance manifest updates where output is intentionally unchanged (refresh
  without a version bump is OK — see [CONTRIBUTING.md](../CONTRIBUTING.md)).

### Bundles

Composite bundles under `blueprints/bundles/*/` follow the same semver rules on
`metadata.version`. When a **member** blueprint bumps, evaluate whether the bundle
needs a **MINOR** (new member, new shared input) or **PATCH** (member pin-only
update with no bundle manifest change).

## Author workflow

1. Decide the semver bump using the table above.
2. Update `metadata.version` in `blueprint.yaml` (or `bundle.yaml`).
3. Update `conformance.yaml` fixture inputs if inputs changed.
4. Run generation locally; fix gates.
5. If the blueprint uses conformance snapshots (`snapshot: true`), refresh:
   `make blueprint-conformance-update`
6. Note the bump in the PR description; fleet/operator consumers use the new pin
   via `repave update` or desired pins on `GoldenPathRepo`.

## Operator and fleet impact

- **Drift:** Observed pins in `repave.yaml` vs desired catalog pins →
  `GoldenPathRepo` `OutOfDate`.
- **Upgrade:** `repave plan-upgrade` / operator upgrade plans target the catalog
  blueprint version on `main`.
- **Remediation:** Operator opens PRs only when pins drift; semver **MAJOR**
  blueprint changes may need manual input migration in target repos.

## Extra catalog roots

The engine always loads `./blueprints`. Forks and vendor packs add more local
roots via `blueprints_root` / `blueprint_sources` (or
`REPAVE_BLUEPRINTS_ROOT` / `REPAVE_BLUEPRINT_SOURCES`), or git URL packs via
`blueprint_packs`. See
[`repave-config-v1.md`](repave-config-v1.md#extra-blueprint-catalog-roots).

## Fork workflow

1. Fork or copy the repave repo (or keep upstream and add a sibling pack repo).
2. Add org golden paths as `blueprints/my-org-*` **or** keep them in a separate
   tree and list that tree in `blueprint_sources`.
3. Pin org standards from `standards/` (or a path your blueprint `spec.standard.source`
   can resolve from the engine repo root).
4. `repave list` and `repave generate --blueprint my-org-vpc` should see the extra
   pack with no engine code changes.
5. Point `blueprint_packs.sources[]` at a git URL + ref (shallow clone) or
   `oci://registry/repository` + tag/digest (`oras pull` into
   `data/blueprint-packs`). Copy or submodule still works.

## v3 and beyond

Schema removals and mandatory gate policy changes are scheduled for v3 — not
during the v2 freeze. When v3 planning opens a schema revision, this document
will gain an explicit migration section; until then, treat v2 schemas as stable.
