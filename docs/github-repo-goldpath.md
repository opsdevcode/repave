# GitHub repository provisioning goldpath

The `github-repo-generic` blueprint provisions a GitHub organization repository and
optionally grants org teams access. It does **not** scaffold Terraform, app, or Helm
content — use another golden path (or `repave import` / `repave add`) after the repo exists.

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
| Portal | Catalog **Platform** family → `github-repo-generic` form |
| CLI | `repave generate --blueprint blueprints/github-repo-generic --input ...` |
| Alias | `repave create-repo --name my-service --team platform-admins` |
| API | `POST /api/v2/generate` with `"blueprint": "github-repo-generic"` |
| Teams picker | `GET /api/v2/github/teams` (lists org teams for the form) |

Dry-run is the default. Apply needs GitHub credentials (see below).

## Teams

Pass `team_slugs` as a comma-separated list (or repeat `--team` on `create-repo`).
Every selected team receives the same `team_permission` (`pull` / `triage` / `push` /
`maintain` / `admin`). Teams must already exist; this path does not create teams.

## Auth requirements

PAT (`GITHUB_TOKEN`) or GitHub App installation token must be able to:

- Create repositories in the target org (`REPAVE_GITHUB_ORG` / `output.github_org`)
- Generate repositories from templates (template mode)
- Administer team repository permissions
- Read organization teams (portal/API team list)

See [GitHub App authentication](github-app-auth.md) for App permission guidance.

## Overlay files

Both modes push a thin governed overlay after remote create:

- `README.md` — usage and provenance
- `repave.yaml` — `artifactType: github-repo`
- `.github/CODEOWNERS` — when teams were selected (replace `ORG` with your org slug)

## Examples

```bash
# Selection + teams (dry-run)
repave create-repo --name platform-demo \
  --visibility private \
  --team platform-admins \
  --team developers

# From an org template (apply)
repave create-repo --name platform-demo \
  --mode template \
  --template my-org/template-service \
  --no-dry-run
```
