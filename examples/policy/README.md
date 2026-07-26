# Policy golden paths

Repave ships three first-class **policy** artifacts under `standards/policy/` (grouped as **Policy**
in the portal catalog):

| Blueprint | Kind | Artifact type | Enforcement |
| --------- | ---- | ------------- | ----------- |
| `checkov-policy-generic` | Checkov | `checkov-policy` | Custom Checkov pack + fixtures (`checkov` gate) |
| `opa-policy-generic` | OPA | `opa-policy` | Conftest / Rego (`opa` gate) |
| `azure-policy-generic` | Azure Policy | `azure-policy` | Definition JSON validation (`azure-policy` gate) |

Terraform module and stack blueprints still vend `policy/checkov/` and `policy/opa/policies` for
module-time scanning and plan-time Rego via the shared gates.

Every golden path (Terraform, Ansible, and policy) must satisfy
`standards/policy/governance-baseline.md`: `secrets`, `docs-drift`, and
`provenance-drift`, plus domain-specific security gates (Checkov, ansible-lint, etc.).

Provenance in generated repos records:

```yaml
spec:
  governance:
    baseline_source: standards/policy/governance-baseline.md
    baseline_version: "1.0.0"
```

## Plan-time OPA demo (destructive delete)

The shared Rego rule `destructive_changes.rego` blocks Terraform plans that delete
resources without replacement. Try it locally:

```bash
conftest test examples/policy/plan-destructive-delete.json -p policy/opa/policies
```

Expect a non-zero exit and a message containing `destructive delete`. In the portal,
failed **opa** gates show a plain-language **Publish blocked** preamble when this rule
fires during module generation.

Create-only fixture (passes): `blueprints/opa-policy-generic/template/tests/fixtures/plan-create-only.json`.

### Portal demo (destructive delete)

1. Open **opa-policy-generic** in the portal.
2. Set **plan demo** to `destructive_delete` and run a **dry-run** generate.
3. The **opa** gate fails with **Publish blocked** and the destructive plan detail.

CLI:

```bash
cd engine
uv run repave generate --repo-root .. \
  --blueprint blueprints/opa-policy-generic \
  --input policy_name=demo \
  --input organization=platform \
  --input description="Demo destructive plan" \
  --input plan_demo=destructive_delete
```

