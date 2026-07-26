# app-service-generic

Golden path for a governed **Python application service** repository: Dockerfile,
`src/` layout, pytest, engine-written Backstage `catalog-info.yaml`, and generated CI.

See [`docs/backstage.md`](../../docs/backstage.md).

```bash
cd engine
uv run repave generate ../blueprints/app-service-generic \
  --input service_name=checkout-api \
  --input description="Checkout HTTP API" \
  --input owner=group:payments \
  --input system=commerce \
  --input catalog_lifecycle=experimental \
  --input port=8080
```
