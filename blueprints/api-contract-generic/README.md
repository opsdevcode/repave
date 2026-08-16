# api-contract-generic

Golden path for **API contracts**: an OpenAPI or AsyncAPI spec, Spectral lint,
and oasdiff breaking-change detection against `baseline/`.

## Example

```bash
cd engine
uv run repave generate \
  --repo-root .. \
  --blueprint api-contract-generic \
  --input spec_name=checkout \
  --input organization=platform \
  --input description="Checkout HTTP API" \
  --input spec_kind=openapi \
  --input api_title="Checkout API" \
  --dry-run
```

Requires `spectral` and `oasdiff` on PATH for generate-time gates. Generated
repo CI installs pinned versions and runs `repave gates --path .`.

AsyncAPI packs skip oasdiff (OpenAPI only). See
[`standards/api/contract-standard.md`](../../standards/api/contract-standard.md).
