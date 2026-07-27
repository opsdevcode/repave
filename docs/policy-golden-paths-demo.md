# Policy golden paths demo

Three standalone **Policy** family blueprints share the portal customization model
(profiles, pack sources, rule catalog) documented in
[standards/policy/customization.md](../standards/policy/customization.md).

| Blueprint | Gate | Demo outcome |
| --------- | ---- | -------------- |
| `checkov-policy-generic` | `checkov` | Custom Python/YAML Checkov pack + pass fixtures |
| `opa-policy-generic` | `opa` | Rego + Conftest; **`destructive_delete`** blocks publish |
| `azure-policy-generic` | `azure-policy` | Azure definition JSON validated from catalog samples |

Terraform module/stack blueprints **vendor** Checkov and OPA from the same
`policy/catalog.json` — act 2 of the [seven-minute demo](seven-minute-demo.md) shows
profile **Estate default** on the module form without changing rules.

## Prep

```bash
cd deploy/local && docker compose up --build
# or: make serve  →  http://localhost:8088
```

Use **Dry run preview** on every generate unless you rehearsed publish with `GITHUB_TOKEN`.

**Automated smoke:**

```bash
cd engine && uv run pytest tests/test_policy_golden_paths.py tests/test_demo_acts.py -v -k "act5 or policy_golden"
```

---

## 1 — Checkov policy pack (~2 min)

1. Home → **checkov-policy-generic**.
2. **policy_name** `estate`, **organization** `platform`, description e.g. `Estate Checkov rules`.
3. Leave pack **repave-checkov-pack** and profile **checkov-full** (or pick **custom** rules).
4. **Dry run preview** → confirm **Generated files** include `policy/checkov/`, fixtures under
   `tests/fixtures/pass/`, and `repave.yaml` with `checkovPolicy` provenance.

**Say:** “Policy packs are versioned artifacts — same catalog drives Terraform modules and
standalone Checkov repos.”

---

## 2 — OPA block (~2 min)

1. Home → **opa-policy-generic**.
2. **policy_name** `demo`, **organization** `platform`, short description.
3. **plan demo** → **destructive_delete**.
4. **Dry run preview**.

Expect **opa** failure and **Publish blocked** (requires **conftest** in the runtime — Docker
Compose image, not a minimal local venv).

Repeat with **plan demo** → **pass** to show a green gate dashboard and vendored Rego under
`policy/`.

CLI reference: [examples/policy](../examples/policy/README.md).

---

## 3 — Azure Policy definitions (~2 min)

1. Home → **azure-policy-generic**.
2. **policy_name** `demo`, **organization** `platform`, description e.g. `Platform baseline defs`.
3. Pack **repave-azure-samples**, profile **azure-community** (defaults).
4. **Dry run preview** → open **`policy/definitions/`** JSON in **Generated files**; **azure-policy**
   gate should pass.

**Say:** “Definitions are validated before publish — expand to initiatives and assignments in your
estate pipeline.”

---

## Optional — Terraform module plan-time OPA

From **terraform-module-generic** dry-run (seven-minute acts 2–3): generated tree includes
`policy/opa/policies` and a create-only plan fixture; module CI runs **opa** when `terraform plan`
is unavailable.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| OPA always skipped | Install **conftest** or use Docker Compose. |
| Azure gate fails on samples | Regenerate from current `main`; samples live under `policy/azure/definitions/`. |
| Policy rules show raw IDs on form | Hard refresh; catalog titles come from `policy/catalog.json`. |

Related: [Demo verification](demo-verification.md) · [Engine capabilities — policy](engine-capabilities.md)
