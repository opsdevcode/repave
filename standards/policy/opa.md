# OPA policy artifact standard

Version: 1.0.0

Contract for `opa-policy` repositories (`opa-policy-generic` golden path) and for
`policy/opa/` directories copied into Terraform module repos.

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

## Rego

- Policies live under `policy/` (Conftest `-p policy`).
- Use `deny` (and optional `warn`) rules compatible with Conftest.
- Document expected input shapes (Terraform plan JSON vs Kubernetes YAML).

## Fixtures

- `tests/fixtures/` holds inputs that must **pass** at generate time.
- Gate command: `conftest test tests/fixtures -p policy`.

## Versioning

- Pin pack version in blueprint `spec.opa.policy_version` and in provenance `spec.opa`.
