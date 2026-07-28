# Fleet registry

The fleet registry is the list of repositories repave governs. Generation tells you what
repave *created*; the registry tells you what it is still responsible for, which is what
the operator and portal need in order to report drift across an estate.

Related: [operator overview](operator-overview.md), [roadmap](roadmap.md).

## Storage

An append-only JSONL log of `register` and `unregister` events. Current state is the fold
of those events, last write winning per repository, so re-registering a repo with new pins
updates it rather than duplicating it. This is the same shape as the
[audit sink](../repave.config.yaml.example) so the backend can move to a database later
without changing callers.

Enable it in `repave.config.yaml`:

```yaml
fleet:
  enabled: true
  file: ../repave-fleet/registry.jsonl
```

`REPAVE_FLEET_FILE` overrides the path. Relative paths resolve against the repo root. Keep
the file outside the repave repo so registry writes never dirty the working tree.

Commands fail with an explanatory error when no registry is configured, rather than
silently writing nowhere.

## CLI

Register a repository, reading its pins from a local checkout's `repave.yaml` provenance:

```bash
repave register https://github.com/acme/tf-vpc --path ~/modules/tf-vpc --owner platform
```

Provenance is the preferred source because it is exactly what the operator observes. When
you have no checkout, pass pins explicitly:

```bash
repave register https://github.com/acme/tf-vpc \
  --blueprint terraform-module-generic --blueprint-version 0.9.0
```

List and remove:

```bash
repave fleet                 # human-readable
repave fleet --format json   # scripting and CI
repave unregister https://github.com/acme/tf-vpc
```

`unregister` exits non-zero when the repository was not registered, so scripts can tell
"removed" from "was never there".

URL spellings collapse to one entry: `https://github.com/acme/tf-vpc.git`, the same URL
with a trailing slash, and the bare form are one repository. Register and unregister
therefore agree regardless of which form a caller uses.

## API

| Method | Path | Role |
| --- | --- | --- |
| `GET` | `/api/v1/fleet` | any authenticated role (`viewer` and up) |
| `POST` | `/api/v1/fleet` | `admin` |
| `DELETE` | `/api/v1/fleet?repo_url=...` | `admin` |

Roles apply in service mode only; local single-user mode has no auth. See
[service mode](auth-service-mode.md).

```bash
curl -X POST localhost:8000/api/v1/fleet \
  -H 'content-type: application/json' \
  -d '{"repo_url": "https://github.com/acme/tf-vpc", "path": "/repos/tf-vpc"}'

curl localhost:8000/api/v1/fleet
```

`GET` returns `{"count": N, "repos": [...]}`. Registration returns `201` with the stored
entry, including the normalized URL and the acting user recorded as `registered_by`.

A missing or disabled registry returns `404` rather than an empty list, so a
misconfiguration cannot be mistaken for an empty fleet.

## Not in this slice

- Portal fleet page (the API is in place; the view is a follow-up)
- Operator sync that emits a `GoldenPathRepo` per registered entry
