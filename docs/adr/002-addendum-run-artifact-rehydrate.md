# ADR 002 addendum: async run rehydrate via run-record snapshots

**Status:** Accepted — Phase 2b implements snapshot default on `main` follow-up  
**Date:** 2026-07-29  
**Amends:** [ADR 002 — v2 service decomposition](002-v2-service-decomposition.md) §4 (artifact transport)  
**Scope:** `run_queue.py`, `generate_api.py`, `run_store.py`, portal `/runs/{id}/result`

## Context

[ADR 002 §4](002-v2-service-decomposition.md#4-no-shared-filesystem-between-roles) states that
generated trees, dry-run previews, and run artifacts travel through the run record **or** an
S3-compatible object store. [Phase 2](../roadmap-archive.md#service-decomposition-for-hosted-scale)
([PR #300](https://github.com/opsdevcode/repave/pull/300)) implemented the object-store path
first: workers stage on local disk, upload to `s3://…`, and the portal materializes the tree
for rehydrate.

That implementation is correct but **over-scoped for the portal's actual need**.

When a user opens a completed async run, `generation_result_from_stored_run` rebuilds a
`GenerationResult` without re-running gates. Most fields already live in `result_json`:

| Field | Source today |
| --- | --- |
| Gate outcomes | `result.gates` in run record |
| PR message | `result.pr_message` in run record |
| Blueprint / dry-run flag | run record columns + `result` metadata |
| Rendered file previews | **Re-read from staging tree** via `collect_rendered_files` |

The staging tree re-read exists only to populate `rendered_files` for the result template.
For **publish runs** (`dry_run: false`), rehydrate never collects rendered files — the artifact
tree is unused. For **dry-run previews**, `collect_rendered_files` already enforces hard caps
(100 files, 32 KiB per file, gate-artifact paths excluded) — roughly **3 MiB** worst case.

Requiring S3 (or any shared filesystem) for that bounded preview adds:

- A second hosted dependency and credential surface (IRSA, bucket policy, lifecycle rules).
- Download latency and failure modes on every portal result view.
- Divergence from local mode, where `result_json` in SQLite is already the source of truth.

Postgres (or SQLite locally) is **already required** for decomposed async runs. Storing the
preview payload in the run record reuses that dependency instead of adding another.

## Decision

### 1. Default: bounded preview snapshot in `result_json`

On successful async run completion, the **worker** serializes a preview snapshot into the
stored run result **before** marking the run `succeeded`:

```yaml
# result_json (illustrative)
gates: [...]           # existing
gates_outcome: passed  # existing
pr_message: "..."      # existing (dry-run and publish)
rendered_files:
  - path: main.tf
    content: |
      # generated ...
    truncated: false
  - path: variables.tf
    content: "..."
    truncated: true
artifact_uri: null     # optional; see §2
```

Serialization uses the same `collect_rendered_files` limits already applied at render time
([`render.py`](../../engine/src/repave_engine/render.py)). The snapshot is written only when
`dry_run: true`; publish runs omit `rendered_files` (current behavior).

**Portal rehydrate** reads the snapshot from `result_json` and does **not** touch the
filesystem or object store when `rendered_files` is present.

### 2. Optional: full staging tree in object storage

`durability.artifact_store_uri` / `REPAVE_ARTIFACT_STORE_URI` remains supported for operators
who need:

- Full unstaged tree retention beyond the preview caps.
- Artifact lifecycle independent of run-record retention.
- Phase 4 per-run Kubernetes Jobs with ephemeral worker pods and long-lived artifacts.

When configured, the worker **still** writes the §1 snapshot (portal default path). Object
storage holds the **full tree** as an optional supplement, not the only copy of preview data.

### 3. Rehydrate resolution order

`generation_result_from_stored_run` resolves preview data in this order:

1. **`result.rendered_files`** — array snapshot in run record (preferred).
2. **`result.artifact_uri`** — materialize from S3-compatible store (optional).
3. **`result.artifact_root`** — local path (single-process / dev only).

Steps 2–3 are fallbacks for runs completed before snapshotting shipped, or when the operator
explicitly disables snapshotting and relies on object storage.

### 4. Hosted decomposition dependency set (revised)

| Dependency | Required for decomposed async runs? |
| --- | --- |
| Postgres (runs, audit, fleet, sessions) | **Yes** |
| Corpus OCI artifact (read-only mount) | **Yes** (Phase 2) |
| S3-compatible object store | **No** (optional) |
| Shared RWX volume between portal and worker | **No** (rejected) |

ADR 002 §4 stands: no shared filesystem between roles. This addendum clarifies that **the run
record is the default transport for portal rehydrate**, and object storage is an opt-in
retention layer for the full staging tree.

## Non-goals

- **Storing the full staging tree in Postgres** — preview caps stay; large blobs belong in
  object storage or not at all.
- **Replacing object storage for Phase 4 Job workers** — ephemeral pods may still upload the
  full tree when snapshot caps are insufficient.
- **Changing the `/api/v1/runs/{id}` JSON shape** — snapshot lives inside the existing
  `result` object; no new endpoint required.

## Alternatives considered

| Option | Verdict |
| --- | --- |
| S3 as the only cross-pod transport (Phase 2 initial) | Works, but mandates object storage for a ~3 MiB preview; rejected as **default**. |
| Bounded snapshot in `result_json` | **Accepted as default** — one store, local-first parity, multi-replica safe. |
| Shared RWX PVC | Rejected in ADR 002. |
| Worker HTTP “fetch artifact” API | Extra auth and failure mode; rejected. |
| Postgres `bytea` / large-object for full tree | Blob storage with worse ops than S3; rejected. |

## Consequences

- **Positive:** hosted decomposition no longer **requires** object storage; portal rehydrate
  is a single DB read; local SQLite and hosted Postgres behave the same; fewer credentials
  and fewer outage modes at v2 GA.
- **Positive:** Phase 2 S3 work ([`artifact_store.py`](../../engine/src/repave_engine/artifact_store.py))
  remains valid as an optional retention path.
- **Negative:** `result_json` rows grow for dry-run async runs (bounded by existing preview
  caps); DB backup size increases slightly.
- **Migration:** runs completed with only `artifact_uri` / `artifact_root` continue to
  rehydrate via fallbacks (§3); no backfill required.

## Sequencing

| Step | Content | Blocked by |
| --- | --- | --- |
| **2a (shipped)** | Corpus OCI mount; split portal/worker images; optional S3 artifact store | Phase 1 |
| **2b (this addendum)** | Worker writes `rendered_files` snapshot; rehydrate prefers snapshot over object store | 2a |
| **Chart default** | `artifactStoreUri` empty in `values-decomposed.yaml`; document S3 as opt-in | 2b |

Phase 2 acceptance for portal rehydrate **does not** require S3 once 2b ships.

## Acceptance

- Worker completes a dry-run async run; `result_json` contains `rendered_files` with capped
  content; portal `/runs/{id}/result` renders without filesystem or S3 access.
- Publish async run: rehydrate succeeds with gates and `pr_message` only (no artifact access).
- `artifact_store_uri` unset: decomposed helm install (Postgres + corpus + split images)
  completes dry-run preview across portal and worker pods.
- `artifact_store_uri` set: full tree uploaded; rehydrate still uses snapshot when present.
- `docker compose up` / `make serve`: unchanged (local `artifact_root` fallback).

## References

- [ADR 002 — v2 service decomposition](002-v2-service-decomposition.md)
- [`docs/durability.md`](../durability.md)
- [`generation_result_from_stored_run`](../../engine/src/repave_engine/generate_api.py)
- [`collect_rendered_files`](../../engine/src/repave_engine/render.py)
