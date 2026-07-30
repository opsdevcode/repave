# Demo verification checklist

Use before a release, a customer demo, or after portal/policy UX changes. Pair with
the [Seven-minute demo (acts 1–6)](seven-minute-demo.md), [Five-minute demo](quickstart.md#five-minute-demo-portal),
and the [Sales demo runbook](sales-demo.md).

**Last verified on `main`:** 2026-07-27 (engine v1.96.0, terraform-module-generic v0.12.0).

---

## Portal smoke (acts 1–6)

Run automated checks: `cd engine && uv run pytest tests/test_demo_acts.py -v`

Manual pass (≈7 minutes) — detail in [seven-minute-demo.md](seven-minute-demo.md):

1. Start: `make serve` or [Docker Compose](../deploy/local/README.md) → http://localhost:8088
2. **Act 1 — Home:** catalog loads; open **terraform-module-generic**.
3. **Acts 2–3 — Generate:** module `demo`, AWS, **ec2 + s3** → **Dry run preview** → **Plan only**, lineage, gates, **Generated files**.
   Optional (when `durability.async_generation` or `REPAVE_ASYNC_GENERATION=true`): enable **Live run console** on the form and confirm `/runs/{id}` streams gate rows before the full result.
4. **Act 4 — Update repo:** **Use terraform-minimal** → **Preview upgrade**.
5. **Act 5 — OPA block:** **opa-policy-generic**, **plan demo** `destructive_delete` → dry-run → publish blocked.
6. **Act 6 — Backstage:** Terraform form, **Include Backstage catalog** `true`, **owner** `group:platform` → dry-run → **`catalog-info.yaml`** in preview.

**Policy family (optional add-on):** [policy-golden-paths-demo.md](policy-golden-paths-demo.md) — Checkov, OPA (`destructive_delete`), Azure samples; `pytest tests/test_policy_golden_paths.py`.

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
