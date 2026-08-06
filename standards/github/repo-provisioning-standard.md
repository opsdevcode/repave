# GitHub repository provisioning standard v1.0.0

Version: 1.0.0

Governed creation of organization repositories from the `github-repo-generic` golden path.
This path provisions the **remote GitHub repository** (template or selection) and team
access; it does not scaffold Terraform, app, or Helm artifact content.

## Naming

- Repository name comes from the `repo_name` input (blueprint `name_template: "{repo_name}"`).
- Prefer lowercase kebab-case names that match org conventions.
- Do not reuse names of archived or deleted repositories without an explicit org exception.

## Create modes

| Mode | Behavior |
| --- | --- |
| `template` | `POST /repos/{template_owner}/{template_repo}/generate` — copy an org template repository |
| `selection` | Create an empty (or metadata-only) repository with visibility, description, and topics |

Template mode requires `template_owner` and `template_repo`. Selection mode ignores them.

## Visibility

Allowed values: `public`, `private`, `internal`. Default for new governed repos is `private`.
`internal` requires a GitHub Enterprise Cloud organization that supports internal visibility.

## Teams

Optional `team_slugs` (comma-separated) receive a single `team_permission` on the new repo:
`pull`, `triage`, `push`, `maintain`, or `admin`. Default permission is `push`.

This path does **not** create teams or sync membership. Teams must already exist in the org.

## Required overlay files

| File | Purpose |
| --- | --- |
| `README.md` | Human summary and **Provenance** section |
| `repave.yaml` | Generation provenance (`artifactType: github-repo`) |
| `.github/CODEOWNERS` | Stub listing provisioned team slugs when any teams were selected |

## Auth

Apply requires a PAT or GitHub App installation token that can create repositories in the
target org, generate from templates when used, and administer team repository permissions.
See [GitHub App authentication](../../docs/github-app-auth.md).

## Out of scope

- Branch protection and rulesets
- Creating or renaming GitHub teams
- Auto-applying a second artifact golden path into the new repository
