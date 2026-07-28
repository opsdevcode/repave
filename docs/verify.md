# repave verify

Score repositories repave did not necessarily generate: run the same gate registry used at
generation time and compare provenance pins to the current catalog blueprint — without
rendering, publishing, or modifying the tree.

Related: [fleet registry](fleet-registry.md), [roadmap](roadmap.md).

## CLI

```bash
repave verify /path/to/module-repo
repave verify /path/to/repo --blueprint terraform-module-generic
repave verify /path/to/repo --format json
```

Exit code `0` when all gates pass (skips allowed) **and** provenance pins match the catalog
blueprint. Exit `1` when gates fail or pins drift. Exit `2` for usage errors (missing path,
unknown blueprint, remote URL).

`--require-run` matches dry-run generation: optional gates that skip because a tool is
missing become failures when they would normally skip.

Remote `repo-url` targets are not cloned yet; check out the repository locally first.

## Report

**Gates:** each blueprint gate from `repave.yaml` `spec.ci.gates`, or from the catalog
blueprint when provenance is absent. If provenance exists but omits `spec.ci.gates`, gates
fall back to the catalog list.

**Pin drift:** when `repave.yaml` is present, fields that differ from the catalog blueprint
(blueprint version, standard source/version, governance baseline, policy pack versions) are
listed the same way as upgrade planning.

## Portal

**Verify repo** in the top navigation accepts a local path (optional blueprint override and
**require-run** checkbox). Results show gate outcomes and pin drift vs the catalog.

## API

| Method | Path | Role (service mode) |
| --- | --- | --- |
| `POST` | `/api/v1/verify` | `viewer` and up |

```bash
curl -X POST localhost:8088/api/v1/verify \
  -H 'content-type: application/json' \
  -d '{"path": "/repos/tf-vpc", "require_run": false}'
```

Returns the same JSON as `repave verify --format json`. HTTP `422` when gates fail or pins
drift; `400` for invalid input.

## Not in this slice

- Remote clone from a repo URL in CLI, portal, or API
- Standards clause diff beyond pin metadata (see `plan-upgrade` / standards diff for depth)
