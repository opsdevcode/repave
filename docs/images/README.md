# README and demo screenshots

PNG captures for the [root README](../../README.md) and [sales demo](../sales-demo.md).

| Path | What it shows |
| --- | --- |
| [portal/](portal/README.md) | Live portal UI (catalog, forms, plan result) |
| [cli/](cli/README.md) | `repave generate --dry-run` terminal output |

## Update all captures

From repo root with the portal reachable at **http://127.0.0.1:8088** (`make serve` or
`deploy/local` Docker Compose):

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
./scripts/capture_portal_screenshots.sh
```

That script refreshes portal PNGs (Playwright against `:8088`), generate-result pages
(TestClient), and the CLI dry-run PNG. See [portal/README.md](portal/README.md) and
[cli/README.md](cli/README.md) for individual steps.
