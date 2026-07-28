# OPA policy artifact standard

Version: 1.2.0

Contract for `opa-policy` repositories (`opa-policy-generic` golden path) and for
`policy/opa/` directories copied into Terraform module and observability repos.

See also [governance-baseline.md](governance-baseline.md).

## Layout (standalone `opa-policy` repo)

```text
.
├── README.md
├── repave.yaml
├── policy/
│   └── *.rego
└── tests/
    └── fixtures/
        └── *.json          # Terraform plan JSON or other conftest inputs
```

## Rego and Conftest

- Policies live under `policy/` (Conftest `-p policy`).
- Pin Conftest **0.68.x** in CI and local toolchain (`deploy/local/install-gate-toolchain.sh`).
- Use **`package main`** for inputs Conftest evaluates directly (Terraform plan JSON,
  standalone JSON/YAML fixtures). The engine runs `conftest test <file> -p policy`;
  plan JSON is **not** wrapped under an `input` key in the file.
- Every `.rego` file **must** declare `import rego.v1` and write rules as
  `deny contains msg if { ... }` and `helper(args) if { ... }`.
  OPA 1.0 made `if` and `contains` mandatory, so classic `deny[msg] { ... }` rules fail to
  load on any current toolchain. `import rego.v1` is accepted from OPA 0.59 onward, so one
  syntax works on both the older pin and OPA 1.x — do not write version-conditional policy.
- Document expected input shapes in file headers (Terraform plan JSON vs native
  Datadog/Grafana JSON vs Prometheus rules YAML).

### Terraform plan JSON

- Required top-level fields include `resource_changes` (see
  `policy/opa/fixtures/plan-create-only.json`).
- Shared rule: `destructive_changes.rego` denies deletes without replacement.

### Observability repos

Catalog rules under `opa:observability_*` apply when the observability blueprint
selects `repave-observability-pack` (default). Native mode runs Conftest on
JSON/YAML paths from blueprint `gate_config.opa.native_globs`; Terraform mode uses
plan JSON when credentials allow, otherwise vendored
`tests/fixtures/plan-create-only.json`.

## Fixtures

- `tests/fixtures/` holds inputs that must **pass** at generate time for `opa-policy` repos.
- Gate command: `conftest test tests/fixtures -p policy`.
- Terraform module and observability repos also receive `plan-create-only.json` for
  CI without cloud credentials.

## Versioning

- Pin pack version in blueprint `spec.opa.policy_version` and in provenance `spec.opa`.
- Bump `policy/catalog.json` → `version` when profiles, pack sources, or rules change.
