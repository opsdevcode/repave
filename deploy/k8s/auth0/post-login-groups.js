/**
 * Auth0 Post-Login Action: map Authorization API Roles into a `groups` claim
 * that repave reads from userinfo (`auth.oidc.groups_claim`, default `groups`).
 *
 * Install:
 *   1. Auth0 Dashboard → Actions → Library → Build Custom → Login / Post Login
 *   2. Paste this file (or sync from repo)
 *   3. Add to the Login flow
 *   4. Create Roles: repave-admins, repave-generators
 *   5. Assign roles to users
 *
 * Namespaced claim alternative: change "groups" below and set
 * repave.auth.oidc.groupsClaim to the same URI in Helm values.
 *
 * Docs: docs/auth-service-mode.md, docs/operations/auth0-portal.md
 */
exports.onExecutePostLogin = async (event, api) => {
  const roles = (event.authorization && event.authorization.roles) || [];
  if (!roles.length) {
    return;
  }
  api.idToken.setCustomClaim("groups", roles);
  api.accessToken.setCustomClaim("groups", roles);
};
