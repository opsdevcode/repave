# GitHub App authentication

Hosted publish and operator remediation can authenticate with a **GitHub App**
instead of a long-lived personal access token (PAT).

## Environment variables

| Variable | Purpose |
| --- | --- |
| `GITHUB_TOKEN` | PAT fallback (local dev and legacy deploys) |
| `GITHUB_APP_ID` | GitHub App ID |
| `GITHUB_APP_INSTALLATION_ID` | Installation ID for the target org/account |
| `GITHUB_APP_PRIVATE_KEY` | PEM private key (`\\n` escapes allowed inline) |
| `GITHUB_APP_PRIVATE_KEY_FILE` | Path to PEM file (alternative to inline key) |

**Precedence:** explicit CLI/API token → `GITHUB_TOKEN` → minted installation token.

Installation tokens are cached in-process and refreshed before expiry.

## Required App permissions

Typical repave usage (adjust for your org policy):

| Surface | Permissions |
| --- | --- |
| Engine publish (create/push module repos) | Repository administration, contents read/write |
| Operator remediation (clone/push/PR) | Contents read/write, pull requests read/write |
| Private repo verify/clone | Contents read |

Install the App on the org that owns generated module repositories.

## Helm chart

When `secrets.create: true`, optional keys are written alongside `github-token`:

- `github-app-id`
- `github-app-installation-id`
- `github-app-private-key`

Values: `secrets.githubAppId`, `secrets.githubAppInstallationId`, `secrets.githubAppPrivateKey`.

Portal, worker, and per-run Job pods receive the corresponding `GITHUB_APP_*` env vars.

## Operator

Set the same env vars on the operator Deployment. Remediation and remote inventory
clone resolve a fresh installation token on each reconcile (cached until expiry).

PAT remains supported for `make operator-e2e` and local development.
