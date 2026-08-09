# repave import

Adopt a repository repave did not generate: rearrange its files into a golden path layout,
add the governance scaffold it is missing, and open a pull request on the source repo.

Import is the brownfield counterpart to generate. Use it once per repository; after the PR
merges the repo carries `repave.yaml` and moves to [`verify`](verify.md) and
[`update`](../README.md#update-an-existing-repository) like any generated artifact. To layer a
second golden path onto that repository later, use [`repave add`](add.md).

Related: [verify](verify.md), [add](add.md), [fleet registry](fleet-registry.md), [roadmap](roadmap.md).

## What import does and does not change

**Never rewrites content.** Files move with `git mv`, so history follows them and the layout
commit contains zero content edits. Every moved file is SHA-256 hashed before and after the
move; a mismatch aborts the import rather than shipping a silent corruption.

**Your source code wins.** Import adds only files the reorganized tree is missing. When your
repo already supplies the artifact's primary content — `*.tf` for a Terraform module,
`tasks/` for an Ansible role, `templates/` for a Helm chart — the blueprint's generated
version of that content is skipped entirely. Import adds governance (`repave.yaml`, gate
config, policy packs, CI workflow, tests scaffold), not resources.

**Conflicts fail the plan.** If two files map to the same destination (`a/main.tf` and
`b/main.tf` both wanting `main.tf`), import reports both and refuses to guess.

**Unmapped files stay put.** Anything no rule matched is listed in the preview and left
exactly where it is.

## Two commits, on purpose

A PR that moves 200 files has to earn trust, so the branch carries two commits:

1. **`refactor(repave): move files into <blueprint> layout`** — pure `git mv`. `git show
   --numstat` reports `0 0` for every path, so a reviewer verifies it mechanically.
2. **`feat(repave): add <blueprint> scaffold`** — the added files, which is the only commit
   that needs reading.

The move commit SHA is appended to `.git-blame-ignore-revs` so a mass move does not destroy
`git blame` for the whole repository.

## Blueprint detection

Import scores every catalog blueprint against the repository's marker files and pre-selects
the best match, with the matched paths shown as evidence:

| Golden path | Markers |
| --- | --- |
| `terraform-module` | `*.tf`, `variables.tf`, `outputs.tf`; no `backend.tf` |
| `terraform-environment-stack` | `backend.tf` or `*.tfbackend`, `envs/`, `environments/` |
| `ansible-role` | `meta/main.yml` + `tasks/main.yml`; no `galaxy.yml` |
| `ansible-collection` | `galaxy.yml`, `plugins/`, `meta/runtime.yml` |
| `ansible-playbook-project` | `ansible.cfg`, `playbooks/`, `inventory/` |
| `helm-chart` | `Chart.yaml` + `values.yaml` + `templates/` |
| `gitops-deployment` | `application.yaml`, `kustomization.yaml`, `helmrelease.yaml`, `apps/`, `clusters/`; no `Chart.yaml` |
| `app-service` | `Dockerfile`, `pyproject.toml`, `package.json`, `go.mod` |
| `opa-policy` | `*.rego` |
| `checkov-policy` | `checks/`, `.checkov.yml` |
| `azure-policy` | `policy.json`, `definitions/` |
| `observability` | `dashboards/`, `monitors/`, dashboard/monitor JSON |

Markers tolerate one level of nesting, so a repo that keeps its Terraform under
`terraform/` is still detected. Pass `--blueprint` (CLI) or pick from the dropdowns (portal)
to override.

## Destination rules

Each blueprint may declare `spec.import` in `blueprint.yaml`; blueprints that do not fall
back to per-family defaults, so every shipped golden path can be imported today.

```yaml
spec:
  import:
    rules:
      - match: ["**/*.tf"]
        exclude: ["examples/**", "modules/**", "tests/**"]
        destination: "."
      - match: ["examples/**"]
        preserveTree: true
      - match: ["**/*.tftest.hcl"]
        destination: "tests/"
      - match: ["README*"]
        destination: "README.md"
    keep: ["LICENSE", "CHANGELOG.md", ".github/**"]
    unmapped: keep-in-place
```

- `destination: "."` or a trailing-slash directory keeps the source basename.
- Any other `destination` is an exact path (`README.rst` → `README.md`).
- `preserveTree: true` leaves matched paths exactly where they are — the subtree is already
  correct.
- `keep` globs are never moved.
- `unmapped: quarantine` collects unmatched files under `.repave/unmapped/` instead of
  leaving them in place.

Rules are evaluated in order; the first match wins.

## Preview before the PR

Planning is read-only and separate from applying, the same split as `plan-upgrade` /
`apply-upgrade`. The preview reports:

- **Scorecard delta** — the same five dimensions the [library](portal-design.md) grades,
  scored against the repo as it is today and against the reorganized tree
  ("2 of 5 today, 4 of 5 after this PR").
- **Gate results** — gates run against the reorganized tree, so nobody is handed a red PR on
  their own repository without warning. A plan with failing gates opens the PR as a **draft**.
- **File plan** — every move with the rule that produced it, every added file, and everything
  left in place.

## CLI

```bash
repave import /path/to/legacy-repo
repave import https://github.com/acme/legacy-vpc
repave import https://github.com/acme/legacy-vpc --blueprint terraform-module-generic
repave import https://github.com/acme/legacy-vpc --skip-gates --format json
repave import https://github.com/acme/legacy-vpc --open-pr
```

Exit code `0` when a plan is produced (or the PR opens with `--open-pr`), `1` when the plan
has conflicts or the repo already conforms, `2` for usage errors, clone failures, or a repo
that is already governed.

| Flag | Purpose |
| --- | --- |
| `--blueprint` | Skip detection and use this golden path |
| `--ref` | Branch or tag when the target is a remote URL |
| `--skip-gates` | Skip the gate run for a faster preview |
| `--open-pr` | Apply on a branch, push, and open the pull request |
| `--git-branch` | Branch name (default `repave/import/<blueprint>-<version>`) |
| `--base-branch` | PR base (default: the source repo's default branch) |
| `--github-token` | Token for `--open-pr` (falls back to `GITHUB_TOKEN` or GitHub App auth) |

## Portal

**Import repo** under **More** in the top navigation, and **Import existing repo** on the
home page. Step 1 takes the repository URL or path; the category and golden path dropdowns
cascade and arrive pre-selected from detection. Step 2 shows the scorecard delta, gate
results, and file plan with an **Open pull request** button.

Deep links work: `/import?repo=https://github.com/acme/x&blueprint=ansible-role-generic`.

A repository that already has `repave.yaml` is not an import candidate; the portal says so
and links to [`/update`](../README.md#update-an-existing-repository).

## API

| Method | Path | Role (service mode) |
| --- | --- | --- |
| `POST` | `/api/v2/imports/plan` | `generator` and up |
| `POST` | `/api/v2/imports/apply` | `generator` and up |

```bash
curl -X POST localhost:8088/api/v2/imports/plan \
  -H 'content-type: application/json' \
  -d '{"target_repo": "https://github.com/acme/legacy-vpc", "with_gates": false}'

curl -X POST localhost:8088/api/v2/imports/apply \
  -H 'content-type: application/json' \
  -d '{"target_repo": "https://github.com/acme/legacy-vpc"}'
```

Body fields: `target_repo` (required), optional `blueprint`, `ref`, `inputs`, `with_gates`,
and for apply `git_branch`, `base_branch`, `github_token`.

`409` when the target already carries `repave.yaml`; `400` for invalid input, clone failure,
or a plan with conflicts.

## Closing the loop

Each import writes an `import` audit event, so it appears in `/activity` alongside every
other action, and registers remote targets in the [fleet registry](fleet-registry.md) so the
repository lands in the library once the PR merges.

The scaffolded `repave.yaml` records `spec.import` with the source, timestamp, and a
`pre_import_layout_hash` of the original tree, so later drift detection has a baseline that
does not assume the tree was generated from the blueprint.

## Per-file destination overrides

When a single classification is wrong, fix it in the preview instead of abandoning the import.
Each moved or unmapped file has an editable destination in the portal file plan. Values:

- A destination path (for example `network/main.tf`)
- `keep-in-place` — leave the file where it is
- `quarantine` — move under `.repave/unmapped/`

Overrides are persisted to `spec.import.overrides` in `repave.yaml` when the pull request
merges, so a later re-import respects them.

CLI:

```bash
repave import ./legacy-vpc --overrides '{"terraform/main.tf":"main.tf"}'
```

API: include an `overrides` object on `POST /api/v2/imports/plan` and `/apply`.

## Remote preview without cloning

For `github.com` HTTPS URLs, preview uses the GitHub trees API by default — no clone until
apply. The preview is marked `preview_limited`: file moves and scaffold are shown, but
scorecard and gates run when you open the pull request (apply shallow-clones the repo).

Force a clone for preview (full scorecard and gates up front):

```bash
repave import https://github.com/acme/legacy-vpc --force-clone
```

## Batch import

Plan or open pull requests for many repositories at once.

Portal: [`/import/batch`](/import/batch) — scan a GitHub organization (with artifact-family
and GitHub search filters), or paste a URL list.

CLI:

```bash
repave import placeholder --batch-file repos.txt --org acme --topic terraform
repave import placeholder --batch-file repos.txt --org acme --language HCL --pushed-since 2026-01-01
```

(`placeholder` is ignored when `--batch-file` is set.)

Optional discovery flags with `--org` or when the batch file is combined with org search:

| Flag | Purpose |
| --- | --- |
| `--topic` | GitHub topic filter |
| `--language` | GitHub language filter (for example `HCL` for Terraform) |
| `--pushed-since` | Repos pushed after `YYYY-MM-DD` |
| `--include-archived` | Include archived repositories (default: excluded) |
| `--include-forks` | Include fork repositories (default: excluded) |

API:

- `POST /api/v2/imports/batch/plan` — body includes `targets`, optional `org`, `topic`,
  `language`, `pushed_since`, `exclude_archived`, `exclude_forks`
- `POST /api/v2/imports/batch/apply` — same fields plus `github_token`

Batch planning respects GitHub rate limits: the engine tracks `X-RateLimit-*` headers per
installation and backs off when quota is low or GitHub returns 429.

## Organization scan

Classify repositories in a GitHub organization by artifact family before batch import.

Portal: on [`/import/batch`](/import/batch), use **Scan organization** to enqueue an async
job (when `durability.async_generation` is enabled). Progress appears on the run console;
results open on a dedicated result page with an **Add all to batch import** action.

API:

- `POST /api/v2/github/org-scan` — synchronous JSON by default; pass `async: true` for a
  **202** response with `run_id` when async generation is enabled
- `POST /api/v2/runs` with `kind: "org_scan"` and scan filters in `inputs` (same fields as
  org-scan)

Sync example:

```bash
curl -sS -X POST "$REPAVE_URL/api/v2/github/org-scan" \
  -H "Content-Type: application/json" \
  -d '{"org":"acme","families":["terraform"],"language":"HCL","limit":100}'
```

Async example (requires async generation):

```bash
curl -sS -X POST "$REPAVE_URL/api/v2/github/org-scan" \
  -H "Content-Type: application/json" \
  -d '{"org":"acme","families":["terraform"],"async":true}'
```

Poll `GET /api/v1/runs/{run_id}` or open `/runs/{run_id}` in the portal until status is
`succeeded`; results are on `/runs/{run_id}/result`.

## Per-family blueprint mapping (batch)

When a batch mixes Terraform, Ansible, Helm, and other artifact types, map each repository
to the right golden path in one preview:

Portal: on [`/import/batch`](/import/batch), choose **Map by artifact family** in the golden
path dropdown. After an org scan, **Add all to batch import** on the result page carries
per-repository blueprint picks from classification when available.

CLI:

```bash
repave import placeholder --batch-file repos.txt --map-by-family
repave import placeholder --batch-file repos.txt \
  --family-blueprints '{"terraform":"terraform-module-generic","ansible":"ansible-role-generic"}'
```

API batch plan/apply:

- `use_family_blueprints: true` — default catalog map per artifact family
- `family_blueprints` — override or extend the map (`terraform` → blueprint name)
- `target_blueprints` — per-repository overrides (`https://github.com/acme/vpc` → blueprint)
- `blueprint: "__family_map__"` — same as `use_family_blueprints` with catalog defaults

Resolution order per repository: explicit `blueprint` (all repos) → `target_blueprints` →
`family_blueprints` by detected family → detect per repository.

## Pre-flight guards

All of these run before the expensive work:

- **Already governed** — a repo with `repave.yaml` routes to upgrade.
- **No-op** — an empty plan reports "already conforms" and opens no PR.
- **Duplicate** — an existing open PR on the import branch is reported rather than duplicated.
- **Permission** — the resolved token's push access to the source repo is checked before
  anything is committed.
