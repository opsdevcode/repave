# Sales demo runbook (portal)

Use this script in **live calls**, executive briefings, and internal enablement.
It complements the hands-on [Quickstart — Five-minute demo](quickstart.md#five-minute-demo-portal)
and the click-by-click **[Seven-minute demo (acts 1–6)](seven-minute-demo.md)**.
Before a big meeting, run the [Demo verification checklist](demo-verification.md).

**Audience:** platform leads, engineering managers, security/governance stakeholders.  
**Duration:** ~5 minutes core; +3 minutes optional (OPA block, Backstage).  
**Setup:** Laptop with Docker or `uv`; no Kubernetes required for the portal loop.

---

## Before the call (2 minutes)

1. Start the portal: `cd deploy/local && docker compose up --build` → http://localhost:8088
   **or** `make serve` → http://127.0.0.1:8089 (native dev; gate toolchain not guaranteed).
2. Confirm the home catalog loads and search works.
3. Optional: open [README portal screenshots](../README.md#portal-primary-ux) in a tab as backup if live demo fails.

**Environment:** Default `REPAVE_GITHUB_ORG=opsdevcode` and `REPAVE_MODULES_ROOT=~/repave-modules` are fine. You do not need `GITHUB_TOKEN` unless you demo real publish.

---

## Narrative arc

**One sentence:** repave is an **internal developer platform** for golden-path estates —
platform standards become a **form**, every generate runs **gates**, **provenance** records
what was pinned, and day-2 upgrades keep the estate on the current road.

Product model: [Concepts](concepts.md) · Today vs becoming: [README](../README.md#what-repave-is)

| Step | What to show | What to say |
| --- | --- | --- |
| 1 — Catalog | Home, families (Terraform, Ansible, Policy) | “This is the IDP catalog — builders pick a golden path; platform owns the blueprint and pins.” |
| 2 — Governed generate | **terraform-module-generic**, module `demo`, AWS, **ec2 + s3**, **Dry-run preview** on | “Pins for standards and policy packs are visible before generate — no surprise drift.” |
| 3 — Proof | Result: **Lineage & receipt**, policy rules, gate dashboard | “Same inputs → same artifact; gates ran in-process; this is what would land in `repave.yaml`.” |
| 4 — Existing estate | **Update repo** → **Use terraform-minimal** → **Preview upgrade** | “The control plane doesn’t only create repos — we plan upgrades from provenance and can open remediation PRs.” |
| 5 — Optional block | **opa-policy-generic**, **plan demo** = `destructive_delete`, dry-run | “Policy isn’t documentation — a failing gate blocks publish.” See [examples/policy](../examples/policy/README.md). |
| 6 — Optional catalog | Terraform form → **Advanced** → **Include Backstage catalog**, owner `group:platform` | “Same generate path registers `catalog-info.yaml` and lineage annotations for Backstage — one paved road, multiple IDP surfaces.” |
| 7 — Optional sandbox | **My services** → **Sandbox** → pick deployment set → Plan only | “Named workload profiles vend ephemeral environments via GitOps — TTL reclaim, no apply credentials in repave.” See [service catalog](service-catalog.md). |

Keep **Dry-run preview** enabled unless you explicitly demo disk write or GitHub publish.

---

## Talking points by stakeholder

**Platform / SRE**

- IDP control plane: portal + CLI + API today; operator for fleet drift ([operator overview](operator-overview.md)).
- Blueprints are versioned; standards and Checkov/OPA packs are pinned in `blueprint.yaml`.
- Gates are mandatory per blueprint — not optional CI add-ons.
- [Engine capabilities](engine-capabilities.md) lists the full gate registry.

**Security / compliance**

- Provenance in `repave.yaml` (`GoldenPathArtifact`) ties repos to blueprint, standard, and governance baseline versions.
- Policy family blueprints and Terraform modules can vend OPA Rego for plan-time checks.
- Secrets scan and Checkov ship on Terraform paths today.

**Developers**

- Portal is the default UX; CLI and [Backstage HTTP API](backstage.md) for automation.
- Local-first: full loop on a laptop without a cluster.

---

## Kubernetes operator (if asked)

The **operator** (GA for inventory, upgrade planning, dry-run remediation) watches `GoldenPathRepo` resources and compares `repave.yaml` pins to desired pins. Local proof: `make operator-test` / `make operator-e2e`.

**Do not over-promise:**

- Remote git inventory and remediation from **`spec.repoURL`** are **GA** when a token/secret is
  configured; local-only demos can still use `spec.localPath` ([Operator GA](operator-ga.md)).
- Remediation PRs to GitHub need token material and reachable `repoURL`; portal **Update repo** +
  CLI cover the same engine contracts today.

Scope: [Operator GA](operator-ga.md) · [Operator overview](operator-overview.md)

---

## After the demo

| Follow-up | Link |
| --- | --- |
| Try themselves | [Quickstart](quickstart.md) |
| Concepts / IDP model | [Concepts](concepts.md) |
| Roadmap / maturity | [Roadmap](roadmap.md) |
| FinOps path | [FinOps enablement](finops.md) |
| Module naming and GitHub | [Module repositories](module-repositories.md) |

---

## Troubleshooting live

| Symptom | Fix |
| --- | --- |
| Portal blank / no CSS | Hard refresh; for native `make serve`, use **http://127.0.0.1:8089** (Compose uses 8088). |
| Gate fails unexpectedly | Dry-run still shows failures — use it to explain “blocked by design.” |
| OPA step skipped | Dry-run no longer skips missing Conftest — install it or use `deploy/local` compose. With tooling, a destructive plan demo shows **FAIL** on the `opa` gate. |
| Compose slow first time | Pre-build before the meeting; keep the stack running. |

After major portal UI changes, refresh README PNGs: [images/README.md](images/README.md).
