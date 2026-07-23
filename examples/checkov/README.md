# Repave Checkov policy pack

Custom Checkov policies enforce the [Terraform module standard](../standards/terraform-module-standard.md)
on generated and hand-maintained module repositories.

## Layout

```text
examples/checkov/
├── policies/                 # Copied into generated modules at policy/checkov/
│   ├── custom_001_*.yaml     # Terraform version constraints (graph checks)
│   ├── custom_002_*.yaml
│   ├── repave_module_layout.py
│   └── repave_null_resource_locals.py
└── tests/
    ├── fixtures/             # Pass/fail Terraform fixtures
    └── test_repave_policies.py
```

Policy pack version is pinned in `blueprints/terraform-module-generic/blueprint.yaml` under
`spec.checkov.policy_version`.

## Running locally

From the repo root (requires `checkov` on PATH or in the engine venv):

```bash
cd engine && .venv/bin/pytest tests/test_checkov_policies.py -q
```

Or scan a module directory directly:

```bash
export REPAVE_CHECKOV_SCAN_ROOT=/path/to/module
checkov -d /path/to/module \
  --config-file .checkov.yml \
  --external-checks-dir policy/checkov \
  --check CKV2_REPAVE_1,CKV2_REPAVE_2,CKV2_REPAVE_3,CKV2_REPAVE_4,CKV2_REPAVE_5,CKV2_REPAVE_6,CKV2_REPAVE_7
```

Repave sets `REPAVE_CHECKOV_SCAN_ROOT` when running the checkov gate so layout policies can
resolve module files reliably.

## Adding org-specific rules

1. Add a Python policy under `examples/checkov/policies/` (or YAML graph check for attribute rules).
2. Assign a unique ID (`CKV2_REPAVE_*` for upstream repave rules; use your org prefix locally).
3. Add pass/fail fixtures under `examples/checkov/tests/fixtures/`.
4. Extend `engine/tests/test_checkov_policies.py` if the rule should guard the golden path.
5. Bump `policy_version` in the blueprint and regenerate modules to pick up the new pack.

Generated module repos receive a copy of the pack at render time. Teams can add supplemental
policies under `policy/checkov/` without modifying repave, but standard enforcement travels
with the pinned pack version.
