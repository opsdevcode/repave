# Seven-minute demo (acts 1–6)

Live script for stakeholder demos. Everything is **dry-run** unless you explicitly
enable apply. Pair with [Sales demo runbook](sales-demo.md) for talking points.

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

**Say:** “Platform owns blueprints and pins; builders pick a golden path.”

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

1. Nav: **Update repo** (shell link).
2. Click **Use terraform-minimal** (or paste path to
   `operator/testdata/modules/terraform-minimal`).
3. **Preview upgrade** — pin diff table and file-level upgrade diff.

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

---

## Act 6 — Developer portal (~1 min)

1. Open **terraform-module-generic** again.
2. Fill Identity + Services as in act 2.
3. On the form (Delivery step or governance section): **Include Backstage catalog**
   → `true`, **owner** → `group:platform` (optional **system** / lifecycle).
4. **Dry run preview** → in **Generated files**, open **`catalog-info.yaml`**.

**Say:** “Same generate path emits catalog metadata for Backstage import.”

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No **Dry run preview** button | Hard refresh; confirm `data-dry-run-run` in page source; restart compose / `make serve` on current `main`. |
| **Scaffold** hidden, can't submit | Stepper CSS/JS mismatch — same as above. |
| Gates all skip | Docker image missing terraform/checkov; use `docker compose up --build`. |
| OPA act inconclusive | Host needs `conftest` for real OPA gate; engine skips with message if missing. |

---

## After the meeting

- [Quickstart](quickstart.md) for hands-on follow-up.
- [Roadmap](roadmap.md) for maturity themes (operator, SSO, v2).
