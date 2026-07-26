# Policy customization

Version: 1.0.0

## Profiles

Generation inputs `policy_profile` and optional `policy_rules` resolve against
[`policy/catalog.json`](../../policy/catalog.json):

| Profile | Behavior |
| ------- | -------- |
| `estate-default` | Curated community-aligned rule set |
| `strict` | All catalog rules for the artifact family |
| `custom` | Explicit rule IDs (required rules always on) |

## Pack source

`policy_pack_source` selects the vendored pack registry entry (default
`repave-default`). Future org registries add entries without changing artifact
layouts.

## Portal

On supported blueprints, the form shows a **Policy profile** dropdown and an
advanced **Customize individual rules** panel (search + checkboxes). Required
rules are locked.

## Provenance

`repave.yaml` records:

```yaml
spec:
  policy:
    profile: estate-default
    pack_source: repave-default
    enabled_rules: [...]
    pack_versions: { checkov: "1.2.0", opa: "1.0.0" }
```

Upgrade plans include a **Policy changes** section when profile or enabled rules
differ.

## Platform mitigations

`repave.config.yaml`:

- `gates.checkov.skip_checks` cannot skip **required** catalog rules.
- `gates.policy.required_rules` adds platform-mandatory rule IDs (floor).

Generated repos store `.repave/policy-selection.json` for gate runners (Checkov
skips, OPA/Azure file lists).

## After generate

Teams may still edit `policy/` in the module repo; re-run generate or
`repave update` to refresh pins and provenance.
