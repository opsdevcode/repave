# Azure Policy artifact standard

Version: 1.0.0

Contract for `azure-policy` repositories (`azure-policy-generic` golden path).

See also [governance-baseline.md](governance-baseline.md).

## Layout

```text
.
├── README.md
├── repave.yaml
└── policy/
    └── definitions/
        └── *.json          # Azure Policy definition documents
```

## Definition JSON

Each file must be a valid Azure Policy **definition** document:

- Top-level `properties` object
- Required properties: `displayName`, `policyType`, `mode`, `description`, `policyRule`
- `policyType` is typically `Custom` for estate-owned definitions
- `mode` must be one of: `All`, `Indexed`, `Microsoft.Kubernetes.Data`
- `policyType` must be `Custom` or `Static` for generated definitions
- `policyRule` must include `if` and `then`; `then` must include `effect`
- Optional `parameters` and `metadata` must be JSON objects when present

The **`azure-policy` gate** enforces the above at generate time (structural validation,
not Azure Resource Manager deployment).

- Pin starter pack version in blueprint `spec.azure_policy.policy_version` when vendoring
  shared definitions from the repave monorepo (`policy/azure/definitions/` — storage HTTPS,
  public blob, tag audit, and required storage audit samples; see `policy/catalog.json`).
- Record organization and policy set name in provenance `spec.azurePolicy`.
