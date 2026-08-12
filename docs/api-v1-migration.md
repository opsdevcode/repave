# Migrating from `/api/v1` to `/api/v2`

Published as part of the [v2.0.0 contract freeze](roadmap-archive.md#v200--platform-ga). New
integrations must use `/api/v2` only.

## Timeline

| Milestone | Date | Meaning |
| --- | --- | --- |
| **Deprecation announced** | v2.0.0 (Platform GA) | Every `/api/v1` JSON response includes deprecation headers |
| **Sunset** | **1 Aug 2027** | Planned removal on the **v3.0.0** line ([breaking at v3](roadmap.md#breaking-at-v300)) |
| **Stable successor** | Now | [`/api/v2`](api-v2.md) |

The sunset date is fixed in code as `V1_SUNSET_HTTP` in
[`engine/src/repave_engine/api_deprecation.py`](../engine/src/repave_engine/api_deprecation.py)
and echoed on every v1 response:

```http
Deprecation: true
Sunset: Sat, 01 Aug 2027 00:00:00 GMT
Link: </docs/api-v2>; rel="successor-version"
```

Monitor these headers in integration tests or API gateways so clients migrate before v3.

## Endpoint mapping

Most v1 routes have a direct v2 equivalent (same request body and JSON shape). Change only
the path prefix.

| v1 | v2 | Notes |
| --- | --- | --- |
| `POST /api/v1/generate` | `POST /api/v2/generate` | Same body; prefer v2 for new code |
| `POST /api/v1/runs` | `POST /api/v2/runs` | Async enqueue |
| `GET /api/v1/runs` | `GET /api/v2/runs` | List runs |
| `GET /api/v1/runs/{id}` | `GET /api/v2/runs/{id}` | Poll status |
| `GET /api/v1/runs/{id}/events` | `GET /api/v2/runs/{id}/events` | SSE progress |
| `POST /api/v1/runs/{id}/replay` | `POST /api/v2/runs/{id}/replay` | Admin replay |
| `POST /api/v1/verify` | `POST /api/v2/verify` | Verify existing repo |
| `GET /api/v1/catalog/entities` | `GET /api/v2/catalog/entities` | Service catalog |
| `GET /api/v1/catalog/entities/{id}` | `GET /api/v2/catalog/entities/{id}` | Entity detail |
| `GET /api/v1/audit` | `GET /api/v2/audit` | Audit query |
| `GET /api/v1/fleet` | `GET /api/v2/fleet` | Fleet registry |
| `POST /api/v1/fleet` | `POST /api/v2/fleet` | Register repo |
| `DELETE /api/v1/fleet` | `DELETE /api/v2/fleet` | Unregister (`repo_url` query) |
| `GET /api/v1/estate` | `GET /api/v2/estate` | Estate map tiles (fleet + audit sparklines) |
| `GET /api/v1/governance/annotations/{blueprint}` | `GET /api/v2/governance/annotations/{blueprint}` | Governance preflight previews |

v2-only surfaces (no v1 equivalent):

| v2 | Purpose |
| --- | --- |
| `GET /api/v2` | Engine version and endpoint index |
| `POST /api/v2/upgrades/plan` | Operator plan-upgrade HTTP |
| `POST /api/v2/upgrades/apply` | Operator apply-upgrade HTTP |
| `POST /api/v2/imports/*` | Repo import plan/apply/batch |

All JSON routes listed in the endpoint mapping above have v2 parity. v1 remains available
with deprecation headers until the v3 sunset.

## Migration checklist

1. Replace path prefix `/api/v1` → `/api/v2` for mapped routes above.
2. Confirm `auth.service_mode` clients still send session cookies or Bearer tokens (same roles).
3. For operator HTTP mode, set `REPAVE_API_URL` to the portal base URL; plan/apply use
   `/api/v2/upgrades/*` ([api-v2.md](api-v2.md#operator-upgrades)).
4. Add a CI check that fails if `Deprecation: true` appears on responses your client still
   treats as long-lived (optional but recommended).
5. Remove v1 paths from client code before **Aug 2027**.

## Authentication and hosted mode

v2 uses the same OIDC session roles as v1 when `auth.service_mode` is enabled. Hosted mode
also requires a SQL durability store — see [`repave-config-v1.md`](repave-config-v1.md).

## Related

- [`docs/api-v2.md`](api-v2.md) — v2 reference
- [`docs/backstage.md`](backstage.md) — Scaffolder integration
- [`docs/roadmap.md`](roadmap.md#breaking-at-v300) — v3 breaking changes
