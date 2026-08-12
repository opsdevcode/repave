# Deploy pipeline OIDC and GitOps promotion

Operators wire trust **once per organization**. Generated repositories ship
`.github/workflows/repave-deploy.yml` and `docs/DEPLOY-OIDC.md` when
`enable_deploy_pipeline` is `"true"` at generate time.

## What gets generated

| Blueprint | Workflow behavior |
| --- | --- |
| `app-service-generic` | Build and push container image to `container_registry` using GitHub OIDC (`id-token: write`) — no cloud access keys in workflow YAML |
| `helm-chart-generic` | Read `Chart.yaml` version, open a PR in `gitops_repo` updating the v1.79 manifest (`targetRevision` or Flux `version`) — no `helm upgrade` in CI |

Both paths run `actionlint` via the existing `repave-gates` workflow.

## GitHub App secret (`REPAVE_GITOPS_APP_TOKEN`)

Helm chart promotion checks out the GitOps repository and opens a pull request.
Use a **GitHub App installation token**, not a long-lived cloud credential:

1. Create a GitHub App with repository **Contents** and **Pull requests** write
   access on the GitOps repo (and the chart repo when private).
2. Install the app on the organization.
3. Add `REPAVE_GITOPS_APP_TOKEN` to the chart repository — prefer the
   **Environment** secret for `deploy_environment` (`dev`, `staging`, `prod`).
4. Enable required reviewers on production environments before merge.

## GHCR push (app service)

Ensure workflow permissions include **read and write packages** when using
`ghcr.io`. The deploy workflow uses `secrets.GITHUB_TOKEN` for registry login — no
separate registry password.

## Optional AWS ECR

For ECR instead of GHCR, configure GitHub OIDC → IAM role trust and pass
`role-to-assume` to `docker/login-action`. Example trust policy shape is in each
generated repo's `docs/DEPLOY-OIDC.md`.

## Related

- [GitOps delivery golden path](../roadmap-archive.md#v179--gitops-delivery-golden-path) (v1.79)
- [Module repository layout](module-repositories.md)
- [Supply chain pinning](supply-chain.md)
