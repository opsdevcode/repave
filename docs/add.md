# repave add

Layer a second golden-path artifact onto a repository repave already governs. Add is the
brownfield complement to [generate-time bundles](concepts.md): instead of composing blueprints
only when scaffolding a new repo, you extend an existing checkout after import or generate.

Use [import](import.md) when the repository has no `repave.yaml`. Use add when it does and
you need another blueprint in the same tree (for example `helm-chart-generic` alongside
`app-service-generic`).

Related: [verify](verify.md), [import](import.md), [fleet registry](fleet-registry.md),
[roadmap](roadmap.md).

## What add does and does not change

**Requires governance.** The target must already contain `repave.yaml`. Ungoverned paths fail
with a message pointing at `repave import`.

**Appends a component record.** The primary blueprint stays at the top level of
`repave.yaml` for backward compatibility. Each add appends an entry to `spec.components[]`
with its own `id`, `artifactType`, blueprint pins, standard pins, and CI gate list.

**Renders new files only.** Add runs the selected blueprint's Copier template into a staging
directory and copies the planned paths into the repository. Paths that already exist and
differ from the generated scaffold are reported as conflicts unless you pass `--force`.

**Shared governance is preserved.** When the repository already has `README.md`, `RUNBOOK.md`,
`.yamllint`, or `.github/workflows/repave-gates.yml`, add skips overwriting them so the
primary component's docs and CI stay authoritative.

**Local apply today.** `--apply` creates a git branch and commit in the local checkout (under
`REPAVE_MODULES_ROOT` for fleet-registered services). Remote clone and `--open-pr` publish
parity with import is a follow-on — push the branch and open a PR manually for now.

## Input inference

When you omit `--input`, add derives blueprint inputs from the on-disk provenance document.
The common case is adding `helm-chart-generic` to an `app-service-generic` primary: service
name, chart name, and image repository are inferred from `spec.generation.inputs` and metadata.

Pass explicit `--input key=value` (repeatable) to override inference or when the primary
artifact type does not supply enough context.

## CLI

```bash
# Plan only (default)
repave add /path/to/checkout-api --blueprint helm-chart-generic

# JSON plan
repave add /path/to/checkout-api --blueprint helm-chart-generic --format json

# Apply locally on branch repave/add/helm-<version>
repave add /path/to/checkout-api --blueprint helm-chart-generic --apply

# Overwrite differing scaffold files
repave add /path/to/checkout-api --blueprint helm-chart-generic --apply --force

# Custom component id recorded in repave.yaml
repave add /path/to/checkout-api --blueprint helm-chart-generic --component-id helm
```

Exit code `0` when the plan is clean (or apply succeeded). Exit `1` when conflicts block the
plan. Exit `2` for usage errors or ungoverned targets.

Branch and commit message follow [governed PR conventions](supply-chain.md) (`branch_prefix_add`,
`add_pull_request_title`). An audit event `component_add` is appended when audit logging is
enabled.

## Verify after add

[`repave verify`](verify.md) scores the primary blueprint at the top level and each entry in
`spec.components[]` independently. JSON output includes a `components` array with per-component
gate outcomes and pin drift vs the catalog.

```bash
repave verify /path/to/checkout-api --format json
```

Overall `ok` is false when any component fails gates or has pin drift.

## Portal

On a fleet-registered service detail page (`/services/{entity_id}`), **Add component** lists
blueprints not already recorded in provenance. **Plan add** previews files and conflicts;
**Apply locally** runs the same path as `repave add --apply` against the entity checkout
under `REPAVE_MODULES_ROOT`.

The form requires a local checkout path configured for the entity; remote-only fleet entries
show the section only when a modules-root mirror exists.

Backstage `/add` calls the same `/api/v2/components/plan` and `/apply` endpoints with an
explicit checkout path. Apply still commits locally — it does not open a pull request.

## API

| Method | Path | Role | Body |
| --- | --- | --- | --- |
| `POST` | `/api/v2/components/plan` | generator, admin | `target_repo`, `blueprint`, optional `component_id`, `inputs`, `force` |
| `POST` | `/api/v2/components/apply` | generator, admin | same fields; optional `git_branch` |

`target_repo` is a local filesystem path (resolved server-side). HTTP `409` when the repository
is not governed (`NotGovernedError`) or when the plan has unresolved conflicts. Apply returns
`git_branch`, `commit_sha`, and the plan document.

Portal form posts to `POST /services/{entity_id}/add-component` with `action=plan|apply`.

## Not in this slice

- Remote shallow-clone + push + open PR (see import's `--open-pr`)
- Per-component `repave plan-upgrade` / `update` selector (upgrade still targets the primary
  blueprint)
- Fleet library tiles showing multiple blueprint pins per repository
