# State graph — operator guide

Repave can act as the authoritative store for Terraform/OpenTofu state, and build a
queryable resource graph on top of it. Design and rationale live in
[ADR 004](adr/004-state-custody-and-the-resource-graph.md); this page is how to run it.

**Off by default.** With no `state_store` block and no `REPAVE_STATE_STORE_URL`, repave
behaves exactly as it did before: no state routes are mounted and nothing is stored.

## The credential boundary

Two halves, and the split is the whole design.

| | Holds | Never holds |
| --- | --- | --- |
| **Server** (`repave-engine[server]`) | State, the graph, transactions | Cloud credentials; it never runs a provider |
| **Client** (`repave-cli`, `repave-tf`) | Cloud credentials, the working directory | A database connection |

`tofu` runs on the engineer's machine or in the repository's CI, with that caller's
credentials. The server receives a plan summary, gate results, and the resulting state
document. This is enforced by a test that fails if `repave_cli` imports database code.

## Enable it

```yaml
# repave.config.yaml
state_store:
  enabled: true
  database_url: postgresql://repave@db/repave
  default_tenant: acme
  required_gates: [checkov, opa]
```

Environment overrides, which win over the file:

| Variable | Meaning |
| --- | --- |
| `REPAVE_STATE_STORE_URL` | Database URL; setting it enables the store |
| `REPAVE_STATE_STORE_TENANT` | Default tenant |
| `REPAVE_STATE_REQUIRED_GATES` | Comma-separated gates that must pass to commit |
| `REPAVE_STATE_KEK` | 32-byte key-encryption key, base64 — **set this** |
| `REPAVE_STATE_KEK_ID` | Key label recorded with each blob, for rotation |
| `REPAVE_IAC_BINARY` | Pin `tofu` or `terraform`; `tofu` is preferred |

SQLite works and is for local development only. Postgres is the supported deployment.

### Set a KEK before anyone stores real state

State contains provider secrets in plaintext. With `REPAVE_STATE_KEK` set, blobs are
envelope-encrypted (AES-256-GCM, per-state data key wrapped by the KEK), so a database
dump is not a secret dump. Without it the store starts, logs a warning, and writes
plaintext. That is acceptable on a laptop and is not acceptable anywhere shared.

Separately, normalized attributes are redacted on ingest using provider schema sensitivity
plus a name-based denylist, so sensitive values never land in a queryable column. One
consequence worth knowing: a changed secret does not show up as drift, because the
redacted value compares equal to itself. Detecting it would mean storing it.

Run `repave-tf graph cache-provider-schema` after adding a provider so redaction knows
what that provider considers sensitive.

## Point Terraform at it

```hcl
terraform {
  backend "http" {
    address        = "https://repave.example.com/api/state/v1/backend/acme/prod"
    lock_address   = "https://repave.example.com/api/state/v1/backend/acme/prod"
    unlock_address = "https://repave.example.com/api/state/v1/backend/acme/prod"
    lock_method    = "LOCK"
    unlock_method  = "UNLOCK"
  }
}
```

This is the stock `http` backend, so a plain `tofu init` works with no client installed.
Whole-state locking applies on this path, exactly as with any other backend. Resource-level
concurrency requires `repave-tf` (below), because the backend protocol has no way to
express it.

## Move existing state in

```bash
repave-tf state import prod terraform.tfstate
repave-tf state export prod --out roundtrip.tfstate
diff terraform.tfstate roundtrip.tfstate    # byte-identical
```

Import once; export any time. The file is never co-authoritative — dual-writing a file and
a database with no shared transaction is not a solvable correctness problem. Export is the
escape hatch and is exercised on every write path, so adopting the store does not trap the
estate.

## Query the graph

```bash
repave-tf graph inventory prod
repave-tf graph resources prod --type aws_instance
repave-tf graph blast-radius prod aws_vpc.main
repave-tf graph drift prod refreshed.tfstate
```

Blast radius walks dependency edges backwards: everything a change to that address can
reach. Edges come from state `depends_on` plus, on a transaction preview/commit path,
plan-JSON `configuration` expression references (`kind: reference`). That enrichment is
entry-condition prep for partitioning; it is still **not** a go for Phase 4 parallel
apply — see the recorded decision in the [Phase 4 gate](state-graph-phase4-review.md).
Direct backend/import writes remain state-derived only.

Pass `--cost infracost.json` to `blast-radius` to price the radius before approving it.

## Plan and apply through a transaction

```bash
repave gates --path . --json > gates.json
repave-tf tf apply prod --chdir infra/prod --gates gates.json
```

The sequence bails out at every step:

```
open tx -> tofu plan -> preview (write set + gates) -> tofu apply -> commit
```

A preview that reports a conflict or a blocking gate stops **before** the apply, so a
governance failure costs a plan rather than a half-applied change. Exit code `2` means
blocked; `1` means error.

**Concurrency is optimistic.** A transaction pins the serial it read and declares the
resources its plan touches. Two transactions touching different resources both commit. One
that overlaps another gets refused, naming the transaction that won:

```
conflict: aws_subnet.web changed since serial 12; conflicting transaction(s): 9f3c...
  Re-plan against current state and retry
```

Only write-write overlap conflicts; two plans that merely read the same resource do not.
Locks are not held during planning, because holding one across a multi-minute plan would
be worse than the whole-state lock Terraform already takes.

**Required gates are enforcing.** Any gate named in `required_gates` must be reported
passing. Missing blocks, and skipped blocks: "nobody ran it" cannot be read as "it passed".
The client runs the gates, because the client holds the working directory — so this stops
accident and CI drift, not a determined operator who could apply out of band anyway.

Left-over transactions:

```bash
repave-tf tf status prod
repave-tf tf abort <tx-id>
```

## Roll out to generated repositories

Terraform-family blueprints now emit a step that installs `repave-tf` in CI, guarded by
`if: vars.REPAVE_STATE_URL != ''`. It is inert until a repository sets that variable, so
the workflow change can ship fleet-wide before any repository moves its state.

## Operational obligations

State is the most critical data repave holds. Before enabling this in a shared deployment,
complete the checklist in
[`docs/operations/state-store-enablement.md`](operations/state-store-enablement.md)
(Helm overlay [`values-state-store.yaml`](../deploy/k8s/chart/values-state-store.yaml),
KEK bootstrap [`bootstrap-state-store-secrets.sh`](../deploy/k8s/hack/bootstrap-state-store-secrets.sh)).

- **Point-in-time recovery and a rehearsed restore**, extending
  [`docs/operations/postgres-backup-restore.md`](operations/postgres-backup-restore.md).
  Byte-exact export is the last-resort escape hatch.
- **A named owner** for compatibility with each Terraform/OpenTofu release. The store pins
  state format `version 4` and rejects unknown formats rather than guessing, which turns a
  silent corruption into a loud refusal.
- **A KEK, stored somewhere other than the database it protects.**
- **Security review** of the posture reversal: repave previously persisted no state and no
  plan JSON. `live_plan.py` still scrubs; this change applies only to the state store, and
  only when it is enabled.

## Client and server versions

`repave-engine` and `repave-cli` ship lockstep under one release. The server advertises
`min_supported_client` and `current_client` at `GET /api/state/v1`; a client behind current
gets a `Warning` header, and one below the floor is rejected with `426 Upgrade Required`.
Stock `tofu` sends no version header and is always served, so the backend routes keep
working regardless.
