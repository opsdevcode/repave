# Application service standard (v1.0.0)

Governed application repositories from the `app-service-generic` golden path.

## Layout

- `Dockerfile` — container image for the service
- `src/` — application source (Python first runtime)
- `tests/` — unit tests run in CI and locally
- `catalog-info.yaml` — Backstage component metadata
- `repave.yaml` — golden-path provenance and CI gate contract

## CI

Generated repos run the same gates as generate time via GitHub Actions (`repave gates`).
Toolchain versions align with `deploy/local/Dockerfile` where applicable.
