# Auth0 portal access — deploy checklist

Turn on Auth0 so the hosted portal HTML and mutating APIs require login before a
shared cluster exposure (EKS recommended). Engine/Helm support shipped in #468;
this runbook is the operator path.

Config reference: [`docs/auth-service-mode.md`](../auth-service-mode.md).
Helm overlay: [`deploy/k8s/chart/values-auth0.yaml`](../../deploy/k8s/chart/values-auth0.yaml).
Post-Login Action source: [`deploy/k8s/auth0/post-login-groups.js`](../../deploy/k8s/auth0/post-login-groups.js).

## Prerequisites

- Postgres (`durability.database_url`) — required when `auth.service_mode` is on
- TLS-terminated Ingress to the portal Service
- Auth0 tenant admin access
- Portal hostname (example: `repave.example.com`)

## 1. Auth0 tenant

1. Create a **Regular Web Application** (confidential client).
2. Set:
   - **Allowed Callback URLs:** `https://<portal-host>/auth/callback`
   - **Allowed Logout URLs:** `https://<portal-host>/`
   - **Allowed Web Origins:** `https://<portal-host>`
3. Copy **Domain**, **Client ID**, **Client Secret**.
4. Issuer (trailing slash): `https://<tenant>.<region>.auth0.com/`
5. Enable **Sign Up** on Universal Login so `/auth/signup` (`screen_hint=signup`)
   can create accounts. Disable it only if the tenant is invite-only.

## 2. Roles and Action

1. Create Roles: `repave-admins`, `repave-generators`.
2. Assign roles to users (or sync from an enterprise connection).
3. Actions → Library → Build Custom → **Login / Post Login**.
4. Paste [`deploy/k8s/auth0/post-login-groups.js`](../../deploy/k8s/auth0/post-login-groups.js).
5. Add the Action to the Login flow.
6. Confirm a test login puts `groups` on the userinfo response (Auth0
   Monitoring / user profile debug, or a one-shot portal login).

## 3. Cluster secrets

```bash
export REPAVE_NAMESPACE=repave
export REPAVE_SESSION_SECRET="$(openssl rand -hex 32)"
export REPAVE_OIDC_CLIENT_SECRET='<auth0-client-secret>'
export REPAVE_API_TOKEN="$(openssl rand -hex 24)"
# optional: export GITHUB_TOKEN=...  (or GitHub App keys — see chart README)

./deploy/k8s/hack/bootstrap-auth0-secrets.sh
```

Store `REPAVE_SESSION_SECRET` / `REPAVE_API_TOKEN` in your secret manager; do not
commit them.

## 4. Helm upgrade

```bash
export REPAVE_OIDC_ISSUER='https://YOUR_TENANT.us.auth0.com/'
export REPAVE_OIDC_CLIENT_ID='YOUR_CLIENT_ID'
export PORTAL_HOST='repave.example.com'
export REPAVE_DATABASE_URL='postgresql://...'

helm upgrade --install repave ./deploy/k8s/chart \
  -n "${REPAVE_NAMESPACE:-repave}" \
  -f deploy/k8s/chart/values.yaml \
  -f deploy/k8s/chart/values-decomposed-day2.yaml \
  -f deploy/k8s/chart/values-auth0.yaml \
  --set secrets.existingSecret=repave-secrets \
  --set repave.durability.databaseUrl="${REPAVE_DATABASE_URL}" \
  --set repave.auth.oidc.issuer="${REPAVE_OIDC_ISSUER}" \
  --set repave.auth.oidc.clientId="${REPAVE_OIDC_CLIENT_ID}" \
  --set repave.auth.oidc.redirectUri="https://${PORTAL_HOST}/auth/callback" \
  --set repave.auth.oidc.logoutReturnTo="https://${PORTAL_HOST}/"
```

## 5. Verify

| Check | Expect |
| --- | --- |
| `curl -sI https://<portal-host>/library` | `302` → `/auth/login` (no cookie) |
| Browser open `/` | Product landing with Sign in and Create account |
| Browser open `/signup` | Create-account page, then Auth0 signup |
| User without roles | Full access when `coarse_rbac_enabled` is false (default); otherwise `viewer` |
| User with `repave-generators` | Full access (default); generate when coarse RBAC enabled |
| Sign out | Clears portal session **and** Auth0 SSO for the app |
| `curl https://<portal-host>/readyz` | `200` (no auth) |
| CronJob with `REPAVE_API_TOKEN` | Still authorized as admin bearer |

## Break-glass

See [OIDC / sign-in outage](README.md#oidc--sign-in-outage). Prefer restoring Auth0;
disabling `repave.auth.serviceMode` opens the portal — remove public Ingress first.

## Deferred

**Auth0 FGA** (resource-level authorization) is parked — coarse
`viewer` / `generator` / `admin` roles are enough for day-1. See roadmap parking lot.
