# Checkov policy artifact standard

Version: 1.0.0

Contract for `checkov-policy` repositories (`checkov-policy-generic` golden path) and for
`policy/checkov/` directories copied into Terraform module repos.

See also [governance-baseline.md](governance-baseline.md).

## Layout (standalone `checkov-policy` repo)

```text
.
├── README.md
├── repave.yaml
├── .checkov.yml
├── policy/
│   └── checkov/              # Custom Checkov policies (Python/YAML)
└── tests/
    └── fixtures/
        └── pass/             # Compliant Terraform module scanned at generate time
```

## Policy pack

- Policies are vendored from the repave monorepo at `policy/checkov/policies/` (pinned version
  in blueprint `spec.checkov.policy_version`).
- Rule IDs use the `CKV2_REPAVE_*` namespace (version bounds, module layout, security hygiene).
- Teams may add org-specific policies alongside the vendored pack.

## Fixtures

- `tests/fixtures/pass/` is a minimal Terraform module that must pass all enabled catalog rules
  when generating.
- Gate command: `checkov -d tests/fixtures/pass --config-file .checkov.yml --external-checks-dir policy/checkov`.

## Versioning

- Pin pack version in blueprint `spec.checkov.policy_version` and in provenance `spec.checkov`.
- Record organization and policy set name in provenance `spec.checkovPolicy`.
