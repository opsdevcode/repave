# github-repo-generic

Provision a GitHub organization repository from a **template** or a **selection** form,
then grant selected org teams a repository permission.

## When to use

- Bootstrap an empty or template-based repo before applying another golden path
- Standardize visibility, topics, and team access at create time

## Inputs

| Input | Notes |
| --- | --- |
| `create_mode` | `selection` (default) or `template` |
| `template_owner` / `template_repo` | Required when `create_mode=template` |
| `team_slugs` | Optional comma-separated org team slugs |
| `team_permission` | Applied to every selected team (`push` default) |

## Apply

Dry-run by default. Publish needs `GITHUB_TOKEN` or GitHub App credentials with permission
to create repositories, generate from templates, and manage team repository access.

```bash
repave generate --blueprint github-repo-generic \
  --input repo_name=my-service \
  --input create_mode=selection \
  --input visibility=private \
  --input team_slugs=platform-admins,developers

repave create-repo --name my-service --visibility private --team platform-admins
```

See [GitHub repository goldpath](../../docs/github-repo-goldpath.md) and
[repo provisioning standard](../../standards/github/repo-provisioning-standard.md).
