# Portal screenshots

PNG captures for the root [README](../../README.md) and demos. Re-run after
major portal UI changes (see [Demo verification](../demo-verification.md)).

## Files

| File | Route | Shows |
| --- | --- | --- |
| `home-catalog.png` | `/` | Catalog, quick menu, search, hero |
| `blueprint-form.png` | `/blueprints/terraform-module-generic` | Governance rail + stepper form |
| `update-repo.png` | `/update` | Upgrade / re-render flow |
| `generate-result.png` | dry-run generate | Lineage, policy rules, gate dashboard |
| `generate-result-backstage.png` | dry-run + Backstage catalog | Backstage card + `catalog-info.yaml` preview |

## Refresh

From repo root (portal on `:8088` for static pages; generate capture uses TestClient):

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
./scripts/capture_portal_screenshots.sh
```

- Static routes use Playwright CLI (`npx playwright screenshot …`).
- `generate-result.png` uses `scripts/capture_generate_result.py` (`cd engine &&
  uv run --with playwright python ../scripts/capture_generate_result.py`).

Prefer **dark mode** (default) and ~1280×800 viewport. For blueprint forms use a
wide window so the governance split layout is visible.

## Manual serve

```bash
cd deploy/local && docker compose up --build
# or: make serve  →  http://127.0.0.1:8088
```
