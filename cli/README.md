# repave-cli (`repave-tf`)

The repave state and execution client. Runs where cloud credentials already live —
a CI runner or a developer machine — and speaks HTTP to the repave state store.

See [ADR 004](../docs/adr/004-state-custody-and-the-resource-graph.md) for why this is a
separate package from `repave-engine`, and [`docs/state-graph.md`](../docs/state-graph.md)
for the operator guide.

## Why a separate package

`repave-engine` owns the `repave` console script and is installed by every generated
repository's CI, so the client needs its own name: **`repave-tf`**.

More importantly, this is the first repave tool that mutates production
infrastructure. A bug in `repave generate` produces a bad file; a bug in `repave-tf
apply` destroys a database. It gets its own release gate and its own test bar.

## The boundary

This package **never** opens a database connection. It does not import `psycopg`,
`sqlite3`, or `repave_engine.sql_store`, and it never holds a DSN. Clients holding
database credentials is precisely the failure mode of Terraform's `pg` backend that
the repave state store exists to avoid.

`tests/test_boundary.py` enforces this by parsing every module's imports. The engine's
`server` extra is installed in the dev environment on purpose, so that test fails
loudly instead of passing vacuously.

## Install

```bash
pip install repave-cli
```

Versions stay lockstep with `repave-engine`.

## Configure

| Variable | Meaning | Default |
| --- | --- | --- |
| `REPAVE_STATE_URL` | State server base URL | required |
| `REPAVE_STATE_TOKEN` | Bearer token | none |
| `REPAVE_STATE_TENANT` | Tenant to operate in | `default` |
| `REPAVE_STATE_TIMEOUT` | Request timeout, seconds | `60` |
| `REPAVE_IAC_BINARY` | Pin `tofu` or `terraform` | auto (`tofu` preferred) |

## Use

```bash
repave-tf state list
repave-tf state show prod
repave-tf state versions prod

# Reversible by design: export returns the original bytes.
repave-tf state import prod terraform.tfstate
repave-tf state export prod --out terraform.tfstate
```

### Query the resource graph

Every accepted write rebuilds a normalized index of the current state, so these are
SQL queries rather than another Terraform run.

```bash
repave-tf graph inventory prod                  # resource counts by type
repave-tf graph resources prod --type aws_instance
repave-tf graph show prod                       # nodes and edges as JSON

# What else breaks if this resource changes?
repave-tf graph blast-radius prod aws_vpc.main

# ...and what does that radius cost?
infracost breakdown --path . --format json --out-file infracost.json
repave-tf graph blast-radius prod aws_vpc.main --cost infracost.json
```

Drift compares stored attributes against a state you refreshed yourself. Repave never
holds your cloud credentials, so the refresh runs on your side and only the result is
uploaded:

```bash
tofu refresh && tofu state pull > refreshed.tfstate
repave-tf graph drift prod refreshed.tfstate
```

Attributes marked sensitive are redacted before they reach the queryable index, so a
changed secret will not show as drift. To widen redaction beyond the built-in name
denylist, upload your provider schemas once per provider version:

```bash
tofu providers schema -json > schema.json
repave-tf graph cache-provider-schema schema.json --provider hashicorp/aws \
  --provider-version 5.0.0
```

### Plan and apply through a transaction

`tofu` runs on your machine, in your working directory, with your cloud credentials. The
store receives a plan summary, your gate results, and the resulting state document — never
a credential.

```bash
repave-tf tf plan prod --chdir infra/prod
repave-tf tf apply prod --chdir infra/prod
```

`apply` opens a transaction, plans, previews, and only then applies. A preview that reports
a conflict or a blocking gate stops before the apply, so a governance failure costs a plan
rather than a half-applied change.

Concurrency is optimistic: transactions that touch different resources commit
independently, and one that overlaps another gets refused with the transaction that won.

```
conflict: aws_subnet.web changed since serial 12; conflicting transaction(s): 9f3c...
  Re-plan against current state and retry
```

Gate results come from a JSON file, so whatever produced them — `repave gates`, your own
pipeline — can feed the decision:

```bash
repave gates --path . --json > gates.json
repave-tf tf apply prod --gates gates.json
```

A gate named in the server's `required_gates` must be reported passing. Missing counts as
blocking: "nobody ran it" cannot be read as "it passed".

```bash
repave-tf tf status prod          # transactions for a state
repave-tf tf abort <tx-id>        # release one that was left open
```

Exit codes: `0` success, `1` error, `2` blocked by a conflict or a gate.

## Develop

```bash
make cli-install
make cli-test-fast     # skips the end-to-end HTTP server tests
make cli-quality
make cli-test
```
