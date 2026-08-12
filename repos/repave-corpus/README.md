# repave-corpus (extraction target)

Future home of the versioned generation corpus. Today these paths live in the umbrella monorepo:

- `blueprints/`
- `standards/`
- `policy/`
- `schemas/`
- `ansible/`
- `observability/`

Published as `ghcr.io/opsdevcode/repave-corpus` — see
[`deploy/packages/repave-corpus`](../../deploy/packages/repave-corpus/README.md).

## CI (post-extraction)

- `scripts/check_blueprint_conformance_manifests.py`
- Render-only conformance matrix (no full engine pytest)
- Triggered on any change under corpus paths only

## Extract

```bash
./scripts/extract-repos/extract-corpus.sh /path/to/repave-corpus.git
```
