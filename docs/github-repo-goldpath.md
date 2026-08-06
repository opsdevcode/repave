# GitHub repository provisioning goldpath

The `github-repo-generic` blueprint provisions a GitHub organization repository, optionally
applies a ruleset profile, syncs team membership from a source org team, grants org teams
access, and registers the repo in the fleet so operator fleetsync / `fleet-manifests` can
emit a `GoldenPathRepo`. It does **not** scaffold Terraform, app, or Helm content — use
another golden path (or `repave import` / `repave add`) after the repo exists.

Standard: [`standards/github/repo-provisioning-standard.md`](../standards/github/repo-provisioning-standard.md).

## Create modes

| Mode | Behavior |
| --- | --- |
| `selection` (default) | Create a repository with visibility, description, and topics |
| `template` | Create from an org template repository (`POST .../generate`) |

Template mode requires `template_owner` and `template_repo`.

## Surfaces

| Surface | How |
| --- | --- |
| Portal | Catalog **Platform** family → `github-repo-generic` form (destination teams datalist, membership sync toggle, source-team member preview, ruleset profile) |
| CLI | `repave generate --blueprint blueprints/github-repo-generic --input ...` |
| Alias | `repave create-repo --name my-service --team platform-admins` |
| API | `POST /api/v2/generate` with `"blueprint": "github-repo-generic"` |
| Teams picker | `GET /api/v2/github/teams` (lists org teams for the form) |
| Team members preview | `GET /api/v2/github/teams/{slug}/members` (viewer+; portal source-team preview) |

Dry-run is the default. Apply needs GitHub credentials (see below).

## Rulesets

Optional `ruleset_profile` (`none` | `default-pr`). After a successful create and overlay
push, `default-pr` upserts a repository ruleset on `~DEFAULT_BRANCH` that requires pull
requests and blocks force-push (no required status checks). Dry-run plans
`Would apply ruleset profile default-pr`.

## Teams and membership sync

Pass `team_slugs` as a comma-separated list (or repeat `--team` on `create-repo`).
Every selected team receives the same `team_permission` (`pull` / `triage` / `push` /
`maintain` / `admin`).

When `membership_source_team` is set (or `sync_team_membership=true`):

1. Create each destination team if it is missing
2. Add members from the source team that are not already on the destination (**additive only**)
3. Grant `team_permission` on the new repository

`membership_source_team` must already exist. Set `--no-sync-team-membership` to grant
permissions without copying members.

## Fleet → GoldenPathRepo

On successful apply, when the fleet registry is enabled, the engine registers the new
repository (same path as import). Operator fleetsync or `repave fleet-manifests` then emit
a `GoldenPathRepo`. The engine never calls Kubernetes directly. See
[Fleet registry](fleet-registry.md).

## Auth requirements

PAT (`GITHUB_TOKEN`) or GitHub App installation token must be able to:

- Create repositories in the target org (`REPAVE_GITHUB_ORG` / `output.github_org`)
- Generate repositories from templates (template mode)
- Administer repository rulesets (when `ruleset_profile` is not `none`)
- Create org teams and manage memberships (when membership sync is enabled)
- Administer team repository permissions
- Read organization teams (portal/API team list and member preview)

See [GitHub App authentication](github-app-auth.md) for App permission guidance.

## Overlay files

Both modes push a thin governed overlay after remote create:

- `README.md` — usage and provenance
- `repave.yaml` — `artifactType: github-repo`
- `.github/CODEOWNERS` — when teams were selected (replace `ORG` with your org slug)

## Examples

```bash
# Selection + teams + membership sync + default-pr ruleset (dry-run)
repave create-repo --name platform-demo \
  --visibility private \
  --team platform-admins \
  --team developers \
  --membership-source-team platform \
  --ruleset-profile default-pr

# From an org template (apply)
repave create-repo --name platform-demo \
  --mode template \
  --template my-org/template-service \
  --no-dry-run
```
