# In-cluster upgrade and rollback

Safe Helm upgrades for the repave portal/API chart ([`deploy/k8s/chart/`](../k8s/chart/)).
Assumes a single replica or shared run/session store when scaling — see
[`docs/durability.md`](../durability.md).

## Pre-upgrade checklist

1. **Smoke the target image** (same tag/digest you will deploy):

   ```bash
   CHART_SMOKE_IMAGE_TAG=your-tag make chart-smoke
   ```

2. **Pin the image by digest** in production overlays (not only `:latest`).

3. **Note the current revision** for rollback:

   ```bash
   helm history repave -n repave
   ```

4. **Drain or wait** if long async runs are in flight (`GET /readyz` → `run_queue_inflight`).

## Rolling upgrade

The chart defaults to `maxUnavailable: 0`, startup/liveness/readiness probes, PDB
`minAvailable: 1`, `terminationGracePeriodSeconds: 120`, and `lifecycle.preStop` sleep
so endpoints drop the pod before SIGTERM.

```bash
helm upgrade repave ./deploy/k8s/chart \
  --namespace repave \
  --set image.repository=ghcr.io/your-org/repave-engine \
  --set image.tag=1.85.0 \
  --wait --timeout 10m
kubectl rollout status deployment/repave -n repave
```

On SIGTERM the engine:

1. Stops accepting new async runs (`/readyz` → 503, `not_shutting_down: false`).
2. Drains in-flight queue work for `REPAVE_SHUTDOWN_DRAIN_SECONDS` (chart default **105**).
3. Exits when the queue is empty or grace elapses.

## Rollback

```bash
helm rollback repave <revision> -n repave --wait --timeout 10m
kubectl rollout status deployment/repave -n repave
```

Re-run the port-forward smoke (`curl /health`, `/readyz`, catalog) after rollback.

## Config and schema compatibility

- **Minor chart/app upgrades:** `repave.config.yaml` keys remain backward compatible within
  a minor engine release; breaking config changes ship with migration notes in release notes.
- **Durability / runs DB:** SQLite schema migrations are forward-only in Phase 1; roll back
  the **image** only if the DB file was not migrated by a newer version (check release notes).

## Related

- [Service operations runbooks](README.md)
- [Helm chart README](../k8s/chart/README.md)
