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

## Develop

```bash
make cli-install
make cli-test-fast     # skips the end-to-end HTTP server tests
make cli-quality
make cli-test
```
