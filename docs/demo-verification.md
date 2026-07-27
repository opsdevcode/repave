# Demo verification checklist

Use before a release, a customer demo, or after portal/policy UX changes. Pair with
the [Five-minute demo](quickstart.md#five-minute-demo-portal) steps and the
[Sales demo runbook](sales-demo.md).

**Last verified on `main`:** 2026-07-27 (engine v1.62.3, terraform-module-generic v0.12.0).

---

## Portal smoke (≈5 minutes)

1. Start: `make serve` or [Docker Compose](../deploy/local/README.md) → http://localhost:8088
2. **Home:** catalog loads; search finds `terraform-module-generic`.
3. **Generate (dry-run):** module `demo`, AWS, **ec2 + s3** → **Dry run preview** → confirm **Lineage & receipt**, policy rules (catalog **titles**), gate dashboard, **Generated files**.
4. **Policy (optional):** on Terraform form, confirm profile **Estate default** and pack **repave-default** without changing rules.
5. **OPA block (optional):** `opa-policy-generic`, plan demo `destructive_delete` → **opa** fails with publish blocked ([examples/policy](../examples/policy/README.md)).
6. **Update repo:** **Use terraform-minimal** → **Preview upgrade** returns a plan.
7. **Backstage (optional):** Include catalog + owner → `catalog-info.yaml` in file preview.

Record blockers in an issue; fix or note in the sales runbook troubleshooting table.

---

## Screenshots (when UI changed)

Only open a docs PR if PNGs drift from production UI.

```bash
export REPAVE_GITHUB_ORG=opsdevcode
export REPAVE_MODULES_ROOT=$HOME/repave-modules
./scripts/capture_portal_screenshots.sh
```

Details: [images/portal/README.md](images/portal/README.md). Commit updated PNGs under `docs/images/portal/`.

---

## Operator smoke (optional, ≈10 minutes)

When operator or blueprint pins changed:

```bash
make operator-test
make operator-e2e   # Docker + kind
```

Expect `OutOfDate`, `UpgradePlanned`, and `upgradePlan.blueprintVersion` matching catalog
`terraform-module-generic` (see [Operator GA](operator-ga.md)).

---

## After verification

- Bump **Last verified** date and engine/blueprint versions in this file.
- Link fresh screenshots in the root [README](../README.md#portal-primary-ux) (portal + CLI) if updated.
