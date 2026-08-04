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
  # Secure cookies (Secure flag). Defaults to true when service_mode is on.
  session_https_only: true
  oidc:
    issuer: https://your-idp.example.com/oauth2/default
    client_id: repave-portal
    # client_secret via REPAVE_OIDC_CLIENT_SECRET
    redirect_uri: https://repave.example.com/auth/callback
    # Optional; defaults to origin of redirect_uri (https://repave.example.com/)
    logout_return_to: https://repave.example.com/
    scopes: [openid, profile, email, groups]
    groups_claim: groups
    roles:
      admin: [repave-admins]
      generator: [repave-generators]
```

Environment overrides: `REPAVE_SERVICE_MODE`, `REPAVE_SESSION_SECRET`,
`REPAVE_SESSION_HTTPS_ONLY`, `REPAVE_OIDC_ISSUER`, `REPAVE_OIDC_CLIENT_ID`,
`REPAVE_OIDC_CLIENT_SECRET`, `REPAVE_OIDC_REDIRECT_URI`.

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
- `POST /auth/logout` — clear session, then redirect to IdP logout when discovery
  exposes `end_session_endpoint` (Auth0 falls back to `/v2/logout`)

Public without auth: `/health`, `/readyz`, `/metrics`, `/static/*`, `/auth/*`.

## Hosted mode requirements

Service mode requires `durability.database_url` (or `REPAVE_DATABASE_URL`). JSONL audit
and fleet paths are optional **export mirrors** when SQL is configured — not the primary
store. Config shape and migration: [`repave-config-v1.md`](repave-config-v1.md).

## Auth0 for portal access (day-1)

Use Auth0 so the **hosted portal** (HTML UI) and mutating APIs require login before
you expose the service on a shared cluster (EKS or otherwise). Unauthenticated
browsers hitting `/`, `/library`, `/services/*`, etc. are redirected to
`/auth/login` → Auth0. Coarse RBAC (`viewer` / `generator` / `admin`) is enforced
today. **Auth0 FGA** (resource-level relationship checks) is deferred — see the
roadmap parking lot.

### What is protected

| Surface | Behavior with `auth.service_mode: true` |
| --- | --- |
| Portal HTML | Redirect to Auth0 login when no session |
| Mutating JSON APIs | `401` without session or `REPAVE_API_TOKEN` |
| Sign out | Clears portal session, then Auth0 logout |
| Probes / metrics | Public: `/health`, `/readyz`, `/metrics`, `/static/*`, `/auth/*` |

### 1. Auth0 application

1. Create a **Regular Web Application** (confidential client; authorization-code + secret).
2. **Allowed Callback URLs:** `https://<portal-host>/auth/callback`
3. **Allowed Logout URLs:** `https://<portal-host>/` (must match `logout_return_to`)
4. **Allowed Web Origins:** `https://<portal-host>`
5. Note **Domain**, **Client ID**, and **Client Secret**.

Issuer URL (include trailing slash): `https://<tenant>.<region>.auth0.com/`  
Example: `https://opsdevcode.us.auth0.com/`

### 2. Roles and groups claim

1. Create Auth0 Roles: `repave-admins`, `repave-generators`.
2. Assign roles to users (or sync from your enterprise connection).
3. Add a **Post-Login Action** so roles appear on **userinfo** under the claim
   configured as `groups_claim` (default `groups`):

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const roles = (event.authorization && event.authorization.roles) || [];
  if (roles.length) {
    api.idToken.setCustomClaim("groups", roles);
    api.accessToken.setCustomClaim("groups", roles);
  }
};
```

If you prefer a namespaced claim (Auth0 recommendation for custom APIs), set
`groups_claim` to that URI (for example `https://repave.opsdevcode/groups`) and use
the same name in `setCustomClaim`.

Repave reads **userinfo** after the code exchange (not ID-token validation). Ensure
the Action claim is available on the userinfo response for your tenant/API setup.

### 3. Helm values (EKS / Kubernetes)

Overlay [`deploy/k8s/chart/values-auth0.yaml`](../deploy/k8s/chart/values-auth0.yaml)
on top of the decomposed day-2 chart when deploying the portal to Kubernetes:

```bash
kubectl create secret generic repave-secrets -n repave \
  --from-literal=github-token="$GITHUB_TOKEN" \
  --from-literal=session-secret="$REPAVE_SESSION_SECRET" \
  --from-literal=oidc-client-secret="$REPAVE_OIDC_CLIENT_SECRET" \
  --from-literal=api-token="$REPAVE_API_TOKEN"

helm upgrade --install repave ./deploy/k8s/chart \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-decomposed-day2.yaml \
  -f deploy/k8s/chart/values-auth0.yaml \
  --set secrets.existingSecret=repave-secrets \
  --set repave.durability.databaseUrl="$REPAVE_DATABASE_URL" \
  --set repave.auth.oidc.issuer="https://YOUR_TENANT.us.auth0.com/" \
  --set repave.auth.oidc.clientId="$REPAVE_OIDC_CLIENT_ID" \
  --set repave.auth.oidc.redirectUri="https://repave.example.com/auth/callback" \
  --set repave.auth.oidc.logoutReturnTo="https://repave.example.com/"
```

Ingress must terminate TLS. `sessionHttpsOnly: true` sets the session cookie
`Secure` flag (also via `REPAVE_SESSION_HTTPS_ONLY`).

Machine callers (CronJobs, reclaim) use `REPAVE_API_TOKEN` / `secrets.apiToken` and
receive the **admin** role.

### 4. Break-glass

If Auth0 is down: see [OIDC / sign-in outage](operations/README.md#oidc--sign-in-outage).
Typical recovery is restore IdP access, or temporarily disable `auth.serviceMode`
(and accept an open portal) only with cluster network controls.

## IdP examples

**Okta / Entra:** set `issuer` to the issuer URL, map IdP groups to
`roles.generator` and `roles.admin`, ensure the groups claim appears in userinfo
(or adjust `groups_claim`).

**PingID:** same pattern; use the PingOne issuer and enable the groups scope your
tenant exposes.

**Auth0:** see [Auth0 for portal access](#auth0-for-portal-access-day-1) above.

## Backstage

Scaffolder actions should call `POST /api/v1/generate` with a service account or
user token after OIDC login, or run the CLI in a job with `REPAVE_ACTING_USER` set.
See [`docs/backstage.md`](backstage.md).
