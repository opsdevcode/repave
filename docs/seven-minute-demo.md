# Seven-minute demo (acts 1–6)

Live script for stakeholder demos of the repave **IDP** — paved roads today, estate
upgrades in the same shell. Everything is **dry-run** unless you explicitly enable apply.
Pair with [Sales demo runbook](sales-demo.md) for talking points. Product model:
[Concepts](concepts.md) · [What repave is](../README.md#what-repave-is).

**Prep:** [Demo verification](demo-verification.md) · `make serve` or
[Docker Compose](../deploy/local/README.md) → http://localhost:8088

**Automated smoke (maintainers):**

```bash
cd engine && uv run pytest tests/test_demo_acts.py -v
```

---

## Act 1 — Catalog (~1 min)

1. Open **http://localhost:8088/**
2. Confirm golden paths group by family (Terraform, Ansible, Policy, …).
3. Use search or scroll to **terraform-module-generic** and open it.

**Say:** “This is the IDP catalog — platform owns blueprints and pins; builders pick a golden path.”

---

## Act 2 — Governed generate (~2 min)

1. **Identity:** module name `demo`, short description, leave defaults → **Next**.
2. **Services:** cloud **AWS**, select **ec2** and **s3** (at least one required).
3. Click **Dry run preview** (sticky footer — works on this step; no need to open Delivery).

**Say:** “Plan mode runs the same gates as publish, without writing disk.”

---

## Act 3 — Proof on the result page (~1 min)

On the result page confirm:

- Banner **Plan only** (not publish).
- **Lineage & receipt** (blueprint, standards, governance baseline).
- Policy rules with catalog **titles** (not only raw IDs).
- **Gate dashboard** (pass / fail / skip).
- **Generated files** tree — open `repave.yaml`, README, `.tf` files.

**Say:** “Same inputs → same artifact; lineage is the receipt for auditors.”

---

## Act 4 — Existing estate (~1 min)

1. Open Backstage **Upgrade** (`/upgrade`), or run
   `repave plan-upgrade --target-repo operator/testdata/modules/terraform-minimal`.
2. HTML `/update` is the upgrade form; preview and apply also stay on API/CLI.

**Say:** “We plan upgrades from provenance, not from guessing what's in git.”

---

## Act 5 — Policy block (~1 min)

1. Home → **opa-policy-generic**.
2. **policy_name** `demo`, **organization** `platform`, description e.g. `Demo OPA pack`.
3. **plan demo** → **destructive_delete**.
4. **Dry run preview**.

Expect **opa** gate failure and **Publish blocked** (or equivalent block messaging).

**Say:** “Policy isn't documentation — a failing gate stops the line.”

Details: [examples/policy](../examples/policy/README.md).

**Azure Policy (pass path):** [Policy golden paths demo — §3](policy-golden-paths-demo.md#3--azure-policy-definitions-2-min).
Full policy family walkthrough: [policy-golden-paths-demo.md](policy-golden-paths-demo.md).

---

## Act 6 — Catalog surface (~1 min)

1. Open **terraform-module-generic** again.
2. Fill Identity + Services as in act 2.
3. Switch the form to **Advanced** (top of the stepper) — Backstage and policy-pack
   fields are advanced-only on Terraform blueprints.
4. Set **Include Backstage catalog** → `true`, **owner** → `group:platform`
   (optional **system** / lifecycle).
5. **Dry run preview** → in **Generated files**, open **`catalog-info.yaml`**.

**Say:** “Same paved road emits catalog metadata for Backstage — one generate, multiple IDP surfaces.”

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No **Dry run preview** button | Hard refresh; confirm `data-dry-run-run` in page source; restart compose / `make serve` on current `main`. |
| **Backstage** fields missing on Terraform form | Switch to **Advanced** at the top of the form (v1.88 Guided/Advanced). |
| **Scaffold** hidden, can't submit | Stepper CSS/JS mismatch — same as above. |
| Gates all skip | Docker image missing terraform/checkov; use `docker compose up --build`. |
| OPA act inconclusive | Host needs `conftest` for real OPA gate; engine skips with message if missing. |

---

## After the meeting

- [Quickstart](quickstart.md) for hands-on follow-up.
- [Concepts](concepts.md) for the IDP model.
- [Roadmap](roadmap.md) for today vs becoming (FinOps v2.x, autonomous v3).
