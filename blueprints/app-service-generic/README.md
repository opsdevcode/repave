# app-service-generic

Golden path for a governed **Python application service** repository: Dockerfile,
`src/` layout, pytest, Backstage `catalog-info.yaml`, and generated CI via repave v1.24.

```bash
cd engine
uv run repave generate ../blueprints/app-service-generic \
  --input service_name=checkout-api \
  --input description="Checkout HTTP API" \
  --input owner=team:payments \
  --input port=8080
```
