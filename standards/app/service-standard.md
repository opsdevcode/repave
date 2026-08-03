# Application service standard (v1.0.0)

Version: 1.0.0

Governed application repositories from the `app-service-generic` golden path.

## Layout

- `Dockerfile` — container image for the service
- `src/` — application source (Python first runtime)
- `tests/` — unit tests run in CI and locally
- `catalog-info.yaml` — Backstage component metadata ([catalog standard](../../standards/backstage/catalog-standard.md))
- `repave.yaml` — golden-path provenance and CI gate contract

## CI

Generated repos run the same gates as generate time via GitHub Actions (`repave gates`),
including `actionlint` on `.github/workflows/` to catch invalid workflow YAML before merge.
When `enable_deploy_pipeline` is true, repos also ship `repave-deploy.yml` (container
build/push with GitHub OIDC) and `docs/DEPLOY-OIDC.md` for operator trust wiring.
Toolchain versions align with `deploy/local/gate-toolchain-pins.env`.
