# ADR 002: v2 service decomposition and repository strategy

**Status:** Proposed (Phase 0–2 implemented on branch)
**Date:** 2026-07-29  
**Scope:** engine, portal, operator, `deploy/k8s/chart` (v2.0.0 platform GA)

## Context

v2.0.0 promises an authenticated multi-user service and freezes the HTTP and CRD
contracts around it. Today the runtime is two deployables that do not match that promise:

- **Engine portal** — `create_app()` in
  [`engine/src/repave_engine/api.py`](../../engine/src/repave_engine/api.py) serves HTML,
  auth, catalog reads, and the JSON API from one process, and calls
  `pipeline.generate_from_blueprint` in that same process. `api.py` imports the pipeline,
  gates, fleet, audit, auth, and every catalog module.
- **Operator** — a thin CLI orchestrator that execs `repave plan-upgrade` /
  `apply-upgrade` against a monorepo checkout baked into the image
  ([`operator/internal/repave/plan.go`](../../operator/internal/repave/plan.go),
  [`operator/Dockerfile.e2e`](../../operator/Dockerfile.e2e)).

Three properties block scaling that shape:

1. **Gate execution dominates the image and the request.** `gates.run_gates` shells out via
   `gate_runners.run_command` to terraform, tflint, checkov, conftest, helm, yamllint,
   promtool, hadolint, ansible-lint, molecule, go, and pytest. That toolchain is installed
   into [`deploy/local/Dockerfile`](../../deploy/local/Dockerfile) under
   `INSTALL_GATE_TOOLCHAIN=1`, so the portal image carries binaries it never executes.
2. **State is on local disk.** Audit and fleet are JSONL, runs are SQLite at
   `data/runs.sqlite`, sessions fall back to a per-process secret, and Prometheus counters
   are per-process. Replicas cannot share any of it.
3. **The generation corpus is read from the repo root at runtime** — `blueprints/`,
   `standards/`, `policy/`, `schemas/`, `observability/`, `ansible/`.

Durability Phase 1 already drew the execution boundary: `run_queue.py` runs
`generate_api.run_generate_api` on a `ThreadPoolExecutor` with SQLite run records and SSE
events. Phase 3 of that entry names Kubernetes Job workers. This ADR settles the topology
those phases land into, and answers whether the split implies separate repositories.

A hard product constraint frames every option: repave is **local-first**. The full loop must
keep running on a laptop via Compose and `make serve`, so the target cannot be services that
are unable to collapse back into a single process.

## Decision

### 1. One repository through v2

repave stays a monorepo for the v2 line. The seams that a repository split would follow do
not exist in the code yet, the generation corpus is shared by every candidate service, and
release automation is a single `python-semantic-release` tag driving both the PyPI package
and the chart `appVersion`.

Instead of splitting repositories, make the monorepo **split-ready**: independently built and
published images, per-component image tags, and an HTTP contract between components. With
those in place, extracting a directory later is mechanical.

Revisit at v3.0.0, and only on a concrete trigger: an independent release cadence someone
actually wants, external contributors who need a narrower blast radius, or a component
written in another language.

### 2. One image family, role selected by configuration

Services are **roles of one codebase**, not separate codebases. Two image variants differ
only by whether the gate toolchain is installed — the split already prototyped by
`INSTALL_GATE_TOOLCHAIN` and
[`deploy/k8s/chart/values-portal.yaml`](../../deploy/k8s/chart/values-portal.yaml).

| Role | Image variant | Owns | Scaling |
| --- | --- | --- | --- |
| `portal` | toolchain-free | HTML, OIDC and sessions, catalog reads, read models | stateless, N replicas |
| `api` | toolchain-free | `/api/v2` JSON, enqueue, run status and SSE | stateless, N replicas |
| `worker` | gate toolchain | render → gates → publish, verify, upgrade plans | queue depth |
| `operator` | Go, distroless | CRD reconcile; calls `/api/v2` | single, leader-elected |

`portal` and `api` ship as one image with the role chosen by `REPAVE_SERVICE_MODE`, deployed
together until their scaling profiles actually diverge. Local mode runs every role in one
process, so Compose and `make serve` are unchanged.

### 3. Postgres is the queue as well as the store

The out-of-process queue is Postgres with `SELECT … FOR UPDATE SKIP LOCKED`, behind the
existing `run_queue` interface. Durability Phase 2 already requires Postgres for runs, audit,
fleet, and sessions; reusing it keeps the hosted dependency set at one service and the local
dependency set at zero (SQLite keeps backing local mode).

### 4. No shared filesystem between roles

Generated trees, dry-run previews, and run artifacts travel through the run record or an
S3-compatible object store. A shared `ReadWriteMany` volume between portal and worker is
explicitly rejected: it re-creates the coupling this ADR removes and does not survive
multi-zone scheduling.

**Addendum ([002-addendum-run-artifact-rehydrate.md](002-addendum-run-artifact-rehydrate.md)):**
portal rehydrate **defaults** to a bounded `rendered_files` snapshot in `result_json`. Object
storage is **optional** for full staging-tree retention.

The generation corpus becomes a **versioned OCI artifact pinned by digest**, mounted
read-only into `portal` and `worker`. It is static and already pinned by blueprint and
standard versions, so a service in front of it would add hops and a failure mode without
adding a capability.

### 5. The operator becomes an API client

At `repave.dev/v1beta1` — the CRD promotion the v2 contract freeze already schedules — the
reconciler calls `/api/v2` instead of exec'ing the CLI. The Python venv and the monorepo
corpus leave the operator image, and `Dockerfile.e2e` collapses into the production image.

## Non-goals

- **Gates as a service separate from the pipeline.** Gates operate on the staging tree on
  local disk; a network hop per gate means shipping that tree around for no isolation gain.
  Gates stay in the worker process.
- **Fleet, audit, and registry as services.** They are read models over Postgres. Separate
  deployments would add hops without a boundary worth having.
- **Splitting the CLI.** `repave` stays one package that can run every role locally.
- **Multi-tenancy.** v2 remains authenticated single-tenant; per-run Job isolation is a
  prerequisite for tenancy, not a delivery of it.
- **A service mesh or in-cluster git hosting.**

## Sequencing

Each phase is independently shippable and leaves the tree working.

| Phase | Content | Blocked by |
| --- | --- | --- |
| **0** | Postgres store (durability Phase 2); subprocess timeouts (A2); unified toolchain pins (A1); build and push digest-pinned images in CI | — |
| **1** | Postgres-backed queue; `worker` role and chart Deployment; `execution.mode: inprocess \| worker` | Phase 0 |
| **2** | Toolchain-free portal/api image; corpus as OCI artifact; object store for artifacts and previews | Phase 1 |
| **3** | `repave.dev/v1beta1` + conversion webhook; operator calls `/api/v2`; drop CLI exec | Phase 1, `/api/v2` |
| **4** | Optional: per-run Kubernetes Jobs (durability Phase 3); optional portal/api Deployment split | Phase 2 |

Phases 0–2 carry nearly all of the value. If v2 scope tightens, cut Phase 4 and leave the
operator on the CLI path.

## Alternatives considered

| Option | Rejection |
| --- | --- |
| Split into separate repositories now | No module boundaries to lift; shared corpus; rebuilds release automation for no delivery gain. |
| Physically distinct services per role | Breaks local-first; duplicates read models across codebases. |
| Redis, Celery, or NATS for the queue | Second stateful dependency when Postgres is already required. |
| Shared RWX PVC for staging and previews | Re-introduces filesystem coupling; poor multi-zone behavior. |
| Corpus as a catalog service | Static, digest-pinned data; a service adds a hop and an outage mode. |
| Keep gates in the request path and only scale replicas | Multi-minute runs still occupy a request slot; portal image stays large. |

## Consequences

- **Positive:** the portal scales on a small image; gate load scales independently; the
  operator stops shipping a Python runtime; run state survives a pod restart.
- **Negative:** hosted mode gains a required Postgres; two image variants to build, scan, and
  pin; the internal call path becomes a network boundary that needs service-to-service auth.
  Object storage is **optional** (see
  [002 addendum](002-addendum-run-artifact-rehydrate.md)).
- **Contract risk:** `/api/v2` is simultaneously the frozen public surface and the internal
  transport. Design it as a public API and treat the operator as one more client, or internal
  convenience gets frozen into it.
- **Idempotency risk:** publish mutates GitHub. Behind a retryable queue, the existing
  `client_request_id` idempotency must extend through publish, keyed on target repo plus
  content hash, or a retried run can double-publish.
- **Local mode:** unchanged. `execution.mode: inprocess` and the SQLite/JSONL stores remain
  the default outside service mode.

## Acceptance

- `helm install` brings up portal and worker Deployments where the portal image contains no
  gate binaries, and a generation submitted to the portal is executed by the worker.
- Killing a worker mid-run leaves the run replayable, and a second portal replica reports the
  same run status.
- `docker compose up` and `make serve` still complete a full generate → gates → publish loop
  with no Postgres and no object store.
- The operator reconciles a `GoldenPathRepo` with no `repave` CLI on its image.

## References

- [Roadmap — service decomposition for hosted scale](../roadmap.md#service-decomposition-for-hosted-scale)
- [Roadmap — durability and concurrency](../roadmap.md#durability-and-concurrency-for-hosted-use)
- [`docs/durability.md`](../durability.md)
- [ADR 002 addendum — run artifact rehydrate](002-addendum-run-artifact-rehydrate.md)
- [ADR 001](001-goldenpathrepo-repo-url-inventory.md)
- Fat controller: `engine/src/repave_engine/api.py`; pipeline: `pipeline.py`; gates:
  `gates.py`, `gate_runners.py`; queue: `run_queue.py`
