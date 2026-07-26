# Portal screenshots

PNG captures for the root [README](../../README.md) and demos. Re-run after
major portal UI changes.

## Files

| File | Route | Shows |
| --- | --- | --- |
| `home-catalog.png` | `/` | Catalog, quick menu, search, hero |
| `blueprint-form.png` | `/blueprints/terraform-module-generic` | Governance rail + stepper form |
| `update-repo.png` | `/update` | Upgrade / re-render flow |

Optional fourth capture for results (dry-run gate dashboard):

- Generate from the form with **Dry-run preview**, then save as `generate-result.png`.

## Refresh locally

1. Start the portal (requires `REPAVE_GITHUB_ORG` and `REPAVE_MODULES_ROOT`):

   ```bash
   export REPAVE_GITHUB_ORG=your-org
   export REPAVE_MODULES_ROOT=$HOME/repave-modules
   cd engine && uv run repave serve --repo-root .. --host 127.0.0.1 --port 8088
   ```

   Or: `cd deploy/local && docker compose up --build` then open http://localhost:8088.

2. Capture at **1280×800** (or full-page for home) and overwrite the PNGs above.

3. Prefer **dark mode** (default night-ops theme) and a wide viewport so the
   governance split layout is visible on blueprint forms.

## Script

```bash
./scripts/capture_portal_screenshots.sh
```

Requires Node.js and [Playwright](https://playwright.dev/) CLI:

```bash
# one-time
npx playwright install chromium

./scripts/capture_portal_screenshots.sh
```
