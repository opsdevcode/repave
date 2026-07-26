# Terraform environment stack standard (v0.1.0)

Environment stacks are **root modules** that compose pinned child module versions for
a single cloud and deployment environment. They are not published as reusable modules.

## Repository naming

- Pattern: `env-{cloud_provider}-{stack_name}` (for example `env-aws-platform-dev`).

## Layout

- `versions.tf` — Terraform and provider constraints.
- `variables.tf` — stack identity (`stack_name`, `environment`, `cloud_provider`) and tags.
- `locals.tf` — shared tagging and naming prefix.
- `main.tf` — `module` blocks referencing **version-pinned** sources (registry `version`
  or git `ref` in the source URL).
- `outputs.tf` — stack-level outputs; pass through child module outputs where useful.
- `modules/` — optional local modules; replace `_example` with your estate modules or
  point `main.tf` at git/registry sources.
- `repave.yaml` — golden path provenance (`terraformEnvironmentStack`).

## Module pins

- Every child module must pin a version or ref. Do not use floating `main` in production
  stacks.
- Record pins in `repave.yaml` under `spec.terraformEnvironmentStack.pinned_modules` so
  upgrades and operator inventory can detect drift.

## Gates

Same Terraform gate suite as module golden paths: fmt, validate, tflint, checkov,
secrets, docs-drift, provenance-drift.
