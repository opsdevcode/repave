# Service mode and OIDC authentication

Hosted repave instances can require OIDC login before the portal or mutating API
calls are allowed (roadmap v1.27–v1.28). Local development stays **open** when
`auth.service_mode` is false (default).

## Configuration

```yaml
portal:
  density: compact   # optional: default | compact (Backstage-friendly layout)

auth:
  service_mode: true
  # Prefer REPAVE_SESSION_SECRET in production (32+ random bytes)
  oidc:
    issuer: https://your-idp.example.com/oauth2/default
    client_id: repave-portal
    # client_secret via REPAVE_OIDC_CLIENT_SECRET
    redirect_uri: https://repave.example.com/auth/callback
    scopes: [openid, profile, email, groups]
    groups_claim: groups
    roles:
      admin: [repave-admins]
      generator: [repave-generators]
```

Environment overrides: `REPAVE_SERVICE_MODE`, `REPAVE_SESSION_SECRET`,
`REPAVE_OIDC_ISSUER`, `REPAVE_OIDC_CLIENT_ID`, `REPAVE_OIDC_CLIENT_SECRET`,
`REPAVE_OIDC_REDIRECT_URI`.

## Roles

| Role | Portal / API |
| --- | --- |
| `viewer` | Read catalog and forms (default when no group match) |
| `generator` | Dry-run/publish generate, update preview, `POST /api/v1/generate` |
| `admin` | Same as generator (future: inventory/register) |

Authenticated identity is stored in the audit log (`acting_user`) via the session.

## Routes

- `GET /auth/login` — redirect to IdP
- `GET /auth/callback` — OAuth code exchange
- `POST /auth/logout` — clear session

Public without auth: `/health`, `/readyz`, `/metrics`, `/static/*`, `/auth/*`.

## IdP examples

**Okta / Auth0 / Entra:** set `issuer` to the issuer URL, map IdP groups to
`roles.generator` and `roles.admin`, ensure the groups claim appears in userinfo
(or adjust `groups_claim`).

**PingID:** same pattern; use the PingOne issuer and enable the groups scope your
tenant exposes.

## Backstage

Scaffolder actions should call `POST /api/v1/generate` with a service account or
user token after OIDC login, or run the CLI in a job with `REPAVE_ACTING_USER` set.
See [`docs/backstage.md`](backstage.md).
