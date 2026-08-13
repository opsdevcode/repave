# Portal screenshots

PNG captures for the root [README](../../README.md) and demos. Re-run after
major portal UI changes (see [Demo verification](../demo-verification.md)).

## Files

| File | Route | Shows |
| --- | --- | --- |
| `home-catalog.png` | `/` | Open family card grid, search, compact header |
| `library-catalog.png` | `/library` | Labeled family drawers that open a quiet shelf |
| `blueprint-form.png` | `/blueprints/terraform-module-generic` | Governance rail + stepper form |
| `update-repo.png` | `/update` | Upgrade / re-render flow |
| `import-repo.png` | `/import` | Adopt an existing repo into a golden path |
| `generate-result.png` | dry-run generate | Lineage, policy rules, gate dashboard |
| `generate-result-backstage.png` | dry-run + Backstage catalog | Backstage card + `catalog-info.yaml` preview |

See [../README.md](../README.md) for the combined refresh command (`capture_portal_screenshots.sh`).

## Refresh (portal routes only)

From repo root (portal on `:8088` for static pages; generate capture uses TestClient):

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
./scripts/capture_portal_screenshots.sh
```

The script at repo root also writes [../cli/generate-dry-run.png](../cli/generate-dry-run.png).
For CLI-only refresh, see [../cli/README.md](../cli/README.md).

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
