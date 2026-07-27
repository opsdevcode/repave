# CLI screenshots

Terminal-style captures for the root [README](../../README.md). Output is from a real
`repave generate --dry-run` run (gates + file list), rendered for readability.

## Files

| File | Shows |
| --- | --- |
| `generate-dry-run.png` | `repave generate` dry-run — blueprint, gates, generated paths |

## Refresh

Included in the all-in-one script from [../README.md](../README.md):

```bash
export REPAVE_GITHUB_ORG=your-org
export REPAVE_MODULES_ROOT=$HOME/repave-modules
./scripts/capture_portal_screenshots.sh
```

CLI PNG only:

```bash
cd engine && uv run --with playwright python ../scripts/capture_cli_screenshot.py
```
