# Platform console — local dev bundle

Sample fleet, FinOps, adoption, and feedback data for walking through `/platform/*`
in the portal without Prometheus, a live operator, or cloud cost APIs.

## Quick start

From the repo root:

```bash
make platform-dev-setup   # copies examples/platform-dev/repave.config.platform-dev.yaml → repave.config.yaml
make serve                # http://127.0.0.1:8089
```

Open **More** in the header (or links in the footer) for Fleet, Ops, FinOps, Adoption,
Feedback, and the rest of the platform console.

## What is enabled

| Config block | Pages / behavior |
| --- | --- |
| `fleet` | `/platform/fleet`, library catalog entities, campaigns (with operator snapshot) |
| `audit` | Activity funnel, adoption time-to-first-artifact |
| `platform_metrics` | `/platform/adoption`, `/platform/compliance`, `/platform/value-stream`, `/platform/feedback` |
| `portal.cost_reader: focus` + `cost_focus.file` | L30D actuals on library + FinOps rollup |
| `portal.cost_snapshots` | Sparklines, WoW/MoM anomaly evaluation on `/platform/finops` |
| `portal.cost_budgets` | Budget vs actual badges and over-budget sorting |

Prometheus is **not** required — `/metrics` gauges update in-process when you visit
FinOps or adoption pages; scrape them only if you want external dashboards.

## Sample data

| Path | Role |
| --- | --- |
| `fixtures/fleet/registry.jsonl` | Three governed repos (tf-vpc, opa-guardrails, checkout-api) |
| `fixtures/fleet/operator-status.json` | Drift + active upgrade campaign for `/platform/campaigns` |
| `fixtures/focus/export.json` | FOCUS-shaped billing rows for cost actuals |
| `fixtures/fleet/cost-snapshots.jsonl` | Trend series (includes a WoW spike on tf-vpc) |
| `fixtures/audit/generation.jsonl` | Plan/apply funnel sample events |
| `fixtures/platform-metrics/feedback.jsonl` | CSAT + friction events for `/platform/feedback` |

Full enablement matrix: [`docs/platform-console.md`](../../docs/platform-console.md).

## Customize

Edit `repave.config.yaml` at the repo root (gitignored) or change paths in
`examples/platform-dev/repave.config.platform-dev.yaml` and re-run `make platform-dev-setup`.

To reset sample JSONL files, restore them from git — they are committed fixtures, not
runtime state (except snapshots/feedback grow when you use the portal).
