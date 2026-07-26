# Policy customization

Version: 1.1.0

How teams choose **pack source**, **profile**, and **individual rules** at generate time, and how those choices flow into generated repos, gates, and upgrades.

Related: [`policy/catalog.json`](../../policy/catalog.json) · [Portal policy UX](../../docs/portal-design.md) · [Demo verification — policy step](../../docs/demo-verification.md)

---

## Concepts

| Input | Meaning |
| ----- | ------- |
| `policy_pack_source` | Registry row in `catalog.json` → `pack_sources` (which packs and default profile apply). |
| `policy_profile` | Named rule set (`profiles`) or `custom` for explicit toggles. |
| `policy_rules` | When profile is `custom`, comma-separated catalog rule IDs (required rules always on). |

The engine resolves selections to `.repave/policy-selection.json` in generated repos (Checkov skips, OPA Rego files, Azure definition files).

---

## Profiles (catalog)

Profiles are shared across artifact families; only rules whose `artifact_types` match the blueprint appear in the portal list.

| Profile | Typical use |
| ------- | ------------- |
| `estate-default` | Curated Checkov + OPA for Terraform modules (community-aligned). |
| `strict` | Every catalog rule for the artifact family. |
| `layout` | Terraform module structure / required inputs. |
| `security` | Secret, credential, provisioner, and output hygiene. |
| `terraform-full` | All Checkov + OPA for Terraform. |
| `opa-focused` | Plan-time Rego only. |
| `azure-community` | All shipped Azure Policy sample definitions. |
| `checkov-full` | All repave Checkov custom policies. |
| `custom` | Pick optional rules; required rules stay enabled. |

Pack-specific defaults: for example `repave-azure-samples` defaults to **`azure-community`**; `repave-checkov-pack` to **`checkov-full`**.

---

## Pack sources

`policy_pack_source` selects a row from `pack_sources`:

- **`repave-default`** — Checkov, OPA, and Azure samples for supported artifact types.
- **`repave-azure-samples`** — Azure Policy golden path only (`azure-policy-generic`).
- **`repave-checkov-pack`** / **`repave-opa-pack`** / Terraform-focused packs — narrow defaults for module repos.

Future org registries add rows without changing generated repo layouts.

---

## Portal workflow

On blueprints with policy inputs (Terraform modules, `azure-policy-generic`, `checkov-policy-generic`, `opa-policy-generic`):

1. Open the blueprint form → **Policy** section.
2. Choose **Policy pack source** (tooltip shows pack description / reference URL).
3. Choose **Policy profile** — summary line shows how many catalog rules are active.
4. Optional: open **Individual rules** — under non-custom profiles, rules reflect the profile; switch to **Custom** or use **Enable all optional** / **Match current profile** to tune.
5. Rule rows show **catalog titles**; hover for the stable rule id (for example `checkov:CKV2_REPAVE_1`).

The form loads `/blueprints/{name}/policy-catalog` to refresh packs and rules after catalog changes.

### Terraform module example

- Pack: `repave-default` · Profile: `estate-default` → required version pin, layout basics, plan-time OPA, core security checks.
- Switch profile to **Security baseline** before generate to emphasize credential/secret rules without OPA-only packs.

### Azure Policy example

- Pack: `repave-azure-samples` · Profile: `azure-community` → all sample definitions under `policy/azure/definitions/` vend into `policy/definitions/`.
- **Custom** profile: toggle optional samples (HTTPS, public blob, tags); **Sample audit storage account** stays on (required catalog rule).

---

## CLI and API

Same inputs as the portal:

```bash
uv run repave generate \
  --blueprint blueprints/terraform-module-generic \
  --input policy_pack_source=repave-default \
  --input policy_profile=estate-default \
  ...
```

HTTP generate accepts the same field names in the form body.

---

## Provenance and upgrades

`repave.yaml` records:

```yaml
spec:
  policy:
    profile: estate-default
    pack_source: repave-default
    enabled_rules: [...]
    pack_versions:
      checkov: "1.2.0"
      opa: "1.0.0"
      azurePolicy: "1.1.0"
```

`repave update` / operator upgrade plans include a **Policy changes** section when profile, pack source, or enabled rules differ from the target blueprint.

---

## Platform floors (`repave.config.yaml`)

Org-wide mitigations (see [`repave.config.yaml.example`](../../repave.config.yaml.example)):

- **`gates.checkov.skip_checks`** — cannot skip **required** catalog rules.
- **`gates.policy.required_rules`** — additional rule IDs that must always run (floor on top of catalog `required: true`).

Generated repos honor selection via `.repave/policy-selection.json`; gate runners read that file at generate and in CI (`repave gates --path .`).

---

## Community standards watch

External references (Checkov, Conftest, Terraform, Azure Policy) live in [`policy/standards-watch.json`](../../policy/standards-watch.json). Run `make policy-standards-watch` locally; the weekly GitHub workflow opens a PR when upstream content drifts.

---

## After generate

Teams may edit vendored `policy/` in the module repo. Re-run **generate** or **`repave update`** to refresh pins, selection, and provenance — ad-hoc edits without upgrade may fail **provenance-drift** or **docs-drift** gates.
