# Python package boundaries (v3 engine split)

Pre-extraction package manifests for [ADR 007](../docs/adr/007-v3-multi-repo-decomposition.md).
Code still lives under `engine/src/repave_engine/`; these directories define ownership, future
PyPI package names, and import-boundary rules enforced by
[`engine/tests/test_package_boundaries.py`](../engine/tests/test_package_boundaries.py).

| Package | Future repo | Owns (modules) | Must not import |
| --- | --- | --- | --- |
| [repave-core](repave-core/MANIFEST.yaml) | `opsdevcode/repave-core` | `blueprint`, `pipeline`, `gates`, `gate_runners`, `provenance_*` | `fastapi`, `api`, `api_v2` |
| [repave-server](repave-server/MANIFEST.yaml) | `opsdevcode/repave-server` | `api`, `api_v1`, `api_v2`, `auth`, portal templates | `gate_runners` (enqueue only) |
| [repave-worker](repave-worker/MANIFEST.yaml) | `opsdevcode/repave-worker` | `generate_api`, `run_queue` worker path, `worker_mode` | portal HTML routers |

Local dev: all packages resolve from the monorepo `engine/` tree until Phase 3 extraction
completes.
