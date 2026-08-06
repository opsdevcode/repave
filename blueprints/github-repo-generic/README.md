# github-repo-generic

Provision a GitHub organization repository from a **template** or a **selection** form,
optionally apply a **ruleset** profile, sync membership from a **source org team** into
destination teams (creating them if needed), then grant repository permissions.

## When to use

- Bootstrap an empty or template-based repo before applying another golden path
- Standardize visibility, topics, team access, and default-branch PR rules at create time
- Register the new repo into the fleet so operator fleetsync / `fleet-manifests` can emit
  a `GoldenPathRepo`

## Inputs

| Input | Notes |
| --- | --- |
| `create_mode` | `selection` (default) or `template` |
| `template_owner` / `template_repo` | Required when `create_mode=template` |
| `team_slugs` | Optional comma-separated destination org team slugs |
| `team_permission` | Applied to every selected team (`push` default) |
| `membership_source_team` | Existing org team to copy members from (additive) |
| `sync_team_membership` | `true`/`false`; defaults on when source team is set |
| `ruleset_profile` | `none` (default) or `default-pr` |

## Apply

Dry-run by default. Publish needs `GITHUB_TOKEN` or GitHub App credentials with permission
to create repositories, manage rulesets, administer teams/memberships, and grant team
repository access. With fleet enabled, a successful apply registers the repo for
`GoldenPathRepo` emission.

```bash
repave generate --blueprint github-repo-generic \
  --input repo_name=my-service \
  --input create_mode=selection \
  --input visibility=private \
  --input team_slugs=platform-admins,developers \
  --input membership_source_team=platform \
  --input ruleset_profile=default-pr

repave create-repo --name my-service --visibility private \
  --team platform-admins \
  --membership-source-team platform \
  --ruleset-profile default-pr
```

See [GitHub repository goldpath](../../docs/github-repo-goldpath.md) and
[repo provisioning standard](../../standards/github/repo-provisioning-standard.md).
