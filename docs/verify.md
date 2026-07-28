# repave verify

Score repositories repave did not necessarily generate: run the same gate registry used at
generation time and compare provenance pins to the current catalog blueprint — without
rendering, publishing, or modifying the tree.

Related: [fleet registry](fleet-registry.md), [roadmap](roadmap.md).

## CLI

```bash
repave verify /path/to/module-repo
repave verify https://github.com/org/tf-aws-vpc.git
repave verify git@github.com:org/tf-aws-vpc.git --ref v1.2.0
repave verify /path/to/repo --blueprint terraform-module-generic
repave verify /path/to/repo --format json
```

Exit code `0` when all gates pass (skips allowed) **and** provenance pins match the catalog
blueprint. Exit `1` when gates fail or pins drift. Exit `2` for usage or clone errors
(missing path, unknown blueprint, unreachable remote).

`--require-run` matches dry-run generation: optional gates that skip because a tool is
missing become failures when they would normally skip.

Remote targets are shallow-cloned into a temporary directory (read-only). For private
HTTPS remotes, set `GITHUB_TOKEN` (or pass a token through the API — see below).

## Report

**Gates:** each blueprint gate from `repave.yaml` `spec.ci.gates`, or from the catalog
blueprint when provenance is absent. If provenance exists but omits `spec.ci.gates`, gates
fall back to the catalog list.

**Pin drift:** when `repave.yaml` is present, fields that differ from the catalog blueprint
(blueprint version, standard source/version, governance baseline, policy pack versions) are
listed the same way as upgrade planning.

JSON output includes `"remote": true` when the target was cloned from a URL.

## Portal

**Verify repo** in the top navigation accepts a local path or git remote URL (optional
blueprint override and **require-run** checkbox). Results show gate outcomes and pin drift
vs the catalog. The portal process uses `GITHUB_TOKEN` for private HTTPS remotes when set.

## API

| Method | Path | Role (service mode) |
| --- | --- | --- |
| `POST` | `/api/v1/verify` | `viewer` and up |

```bash
curl -X POST localhost:8088/api/v1/verify \
  -H 'content-type: application/json' \
  -d '{"path": "/repos/tf-vpc", "require_run": false}'

curl -X POST localhost:8088/api/v1/verify \
  -H 'content-type: application/json' \
  -d '{"repo_url": "https://github.com/org/tf-vpc", "ref": "main"}'
```

Body fields: `path` or `repo_url` (required), optional `blueprint`, `require_run`, `ref`.

Returns the same JSON as `repave verify --format json`. HTTP `422` when gates fail or pins
drift; `400` for invalid input or clone failure.

## Not in this slice

- Standards clause diff beyond pin metadata (see `plan-upgrade` / standards diff for depth)
