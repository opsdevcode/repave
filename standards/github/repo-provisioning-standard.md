# GitHub repository provisioning standard v1.1.0

Version: 1.1.0

Governed creation of organization repositories from the `github-repo-generic` golden path.
This path provisions the **remote GitHub repository** (template or selection), optional
ruleset and team membership sync, and team repository access; it does not scaffold
Terraform, app, or Helm artifact content.

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

## Rulesets

Optional `ruleset_profile`:

| Profile | Behavior |
| --- | --- |
| `none` (default) | No ruleset applied |
| `default-pr` | Active ruleset on `~DEFAULT_BRANCH`: require pull requests and block force-push |

Profiles are baked into the engine (`default-pr` has no required status checks). Applied after
the overlay push so the default branch exists. Upserts by ruleset name when one already exists.

## Teams and membership

Optional `team_slugs` (comma-separated) receive a single `team_permission` on the new repo:
`pull`, `triage`, `push`, `maintain`, or `admin`. Default permission is `push`.

When `membership_source_team` is set (or `sync_team_membership` is true):

1. Ensure each destination team exists (create if missing)
2. Copy members from the source team **additively** (do not remove extras)
3. Grant `team_permission` on the new repository

`membership_source_team` must already exist. Cross-org / IdP SCIM sync is out of scope.

## Fleet registration

On successful non-dry-run apply, the engine best-effort registers the new repo in the fleet
registry (when enabled). Operator fleetsync or `repave fleet-manifests` emit
`GoldenPathRepo` CRs — the engine does not call Kubernetes APIs.

## Required overlay files

| File | Purpose |
| --- | --- |
| `README.md` | Human summary and **Provenance** section |
| `repave.yaml` | Generation provenance (`artifactType: github-repo`) |
| `.github/CODEOWNERS` | Stub listing provisioned team slugs when any teams were selected |

## Auth

Apply requires a PAT or GitHub App installation token that can create repositories in the
target org, generate from templates when used, administer repository rulesets, manage org
teams and memberships when sync is enabled, and administer team repository permissions.
See [GitHub App authentication](../../docs/github-app-auth.md).

## Out of scope

- Legacy `branches/{branch}/protection` API (use repository rulesets)
- Removing members not present on the source team
- Cross-org membership sync / IdP SCIM
- Engine calling Kubernetes APIs directly
- Auto-applying a second artifact golden path into the new repository
