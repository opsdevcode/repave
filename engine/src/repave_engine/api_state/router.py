"""`/api/state/v1` — Terraform http backend protocol plus the repave-tf surface.

Two audiences share this router and they authenticate differently:

* A stock `tofu`/`terraform` binary calls `/backend/...` and can only send HTTP Basic
  credentials or mTLS. It sends no client-version header.
* `repave-tf` calls everything else with a bearer token and a version header.
"""

from __future__ import annotations

import base64
import binascii
import json
import logging
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from repave_engine.auth import (
    ROLE_ADMIN,
    ROLE_GENERATOR,
    ROLE_VIEWER,
    AuthConfig,
    AuthUser,
    authenticated_user,
    require_role,
    service_user_from_bearer,
)
from repave_engine.cost_estimate import parse_resource_costs, total_monthly_cost
from repave_engine.sql_store import connect
from repave_engine.state_contract import (
    CLIENT_HEADER,
    HTTP_CONFLICT,
    HTTP_LOCKED,
    HTTP_UPGRADE_REQUIRED,
    LOCK_ID_PARAM,
    STATE_API_PREFIX,
    contract_payload,
    evaluate_client_version,
    upgrade_required_detail,
)
from repave_engine.statestore.crypto import StateCryptoError, load_state_crypto
from repave_engine.statestore.settings import StateStoreConfig
from repave_engine.statestore.state_document import StateDocumentError
from repave_engine.statestore.store import (
    StateCorruptionError,
    StateStore,
    ensure_state_schema,
    parse_lock_body,
)
from repave_engine.statestore.transactions import (
    parse_gate_outcomes,
    resources_from_plan_json,
)

logger = logging.getLogger(__name__)

_ANONYMOUS = "anonymous"


def build_state_router(
    *,
    repo_root: Path,
    config: StateStoreConfig,
    auth_config: AuthConfig | None,
) -> APIRouter:
    """Build the state router. Callers mount this only when the store is configured."""
    router = APIRouter(prefix=STATE_API_PREFIX, tags=["state"])
    crypto = load_state_crypto()
    if crypto is None:
        logger.warning(
            "state store is enabled without %s: state blobs will be stored in plaintext. "
            "Set a KEK before enabling this in a shared deployment (ADR 004 decision 3)",
            "REPAVE_STATE_KEK",
        )
    _bootstrap_schema(config)

    @contextmanager
    def open_store() -> Iterator[StateStore]:
        conn = connect(config.database)
        try:
            yield StateStore(conn, crypto=crypto, required_gates=config.required_gates)
        finally:
            conn.close()

    def current_user(request: Request) -> AuthUser | None:
        """Resolve the caller without assuming SessionMiddleware is installed.

        A standalone `repave-statestore` deployment serves only machine clients and
        has no reason to mount portal session middleware (ADR 004 decision 6).
        """
        if "session" in request.scope:
            return authenticated_user(request, auth_config)
        if auth_config is None:
            return None
        return service_user_from_bearer(request, auth_config)

    def actor(request: Request) -> str:
        user = current_user(request)
        return user.email if user is not None else _ANONYMOUS

    def guard_client(request: Request) -> str:
        """Apply the warn-then-reject skew policy. Returns a Warning header value."""
        raw = request.headers.get(CLIENT_HEADER)
        outcome = evaluate_client_version(raw)
        if outcome.rejected:
            raise HTTPException(
                status_code=HTTP_UPGRADE_REQUIRED,
                detail=upgrade_required_detail(raw or ""),
            )
        return outcome.warning

    def require_client_role(request: Request, *roles: str) -> str:
        warning = guard_client(request)
        if auth_config is not None and auth_config.service_enabled:
            require_role(current_user(request), *roles)
        return warning

    def require_backend_auth(request: Request) -> None:
        """Authenticate a stock IaC binary via Basic auth, bearer, or session."""
        if auth_config is None or not auth_config.service_enabled:
            return
        if current_user(request) is not None:
            return
        if _basic_auth_ok(request, auth_config):
            return
        raise HTTPException(
            status_code=401,
            detail="state backend requires credentials",
            headers={"WWW-Authenticate": 'Basic realm="repave-state"'},
        )

    # -- discovery ----------------------------------------------------------

    @router.get("")
    async def describe(request: Request) -> JSONResponse:
        warning = guard_client(request)
        return _json(contract_payload(), warning=warning)

    # -- Terraform http backend protocol ------------------------------------

    backend_path = "/backend/{tenant}/{state}"

    @router.get(backend_path, include_in_schema=False)
    async def backend_get(request: Request, tenant: str, state: str) -> Response:
        require_backend_auth(request)
        with open_store() as store:
            raw = _read_bytes(store, tenant, state)
        if raw is None:
            # Terraform reads 404 as "no state yet" and proceeds with an empty state.
            raise HTTPException(status_code=404, detail="state not found")
        return Response(content=raw, media_type="application/json")

    @router.post(backend_path, include_in_schema=False)
    async def backend_post(request: Request, tenant: str, state: str) -> Response:
        require_backend_auth(request)
        body = await request.body()
        lock_id = request.query_params.get(LOCK_ID_PARAM) or None
        with open_store() as store:
            outcome = store.write_state(tenant, state, body, author=actor(request), lock_id=lock_id)
        return _write_response(outcome)

    @router.delete(backend_path, include_in_schema=False)
    async def backend_delete(request: Request, tenant: str, state: str) -> Response:
        require_backend_auth(request)
        with open_store() as store:
            removed = store.delete_state(tenant, state)
        if not removed:
            raise HTTPException(status_code=404, detail="state not found")
        return Response(status_code=200)

    @router.api_route(backend_path, methods=["LOCK", "UNLOCK"], include_in_schema=False)
    async def backend_lock(request: Request, tenant: str, state: str) -> Response:
        require_backend_auth(request)
        body = await request.body()
        lock = parse_lock_body(body)
        with open_store() as store:
            if request.method == "LOCK":
                if lock is None:
                    raise HTTPException(status_code=400, detail="LOCK requires lock info JSON")
                outcome = store.acquire_lock(tenant, state, lock)
                if outcome.status == "held" and outcome.holder is not None:
                    return JSONResponse(outcome.holder.to_payload(), status_code=HTTP_LOCKED)
                return JSONResponse(outcome.holder.to_payload() if outcome.holder else {})

            lock_id = lock.id if lock is not None else request.query_params.get(LOCK_ID_PARAM)
            outcome = store.release_lock(tenant, state, lock_id)
        if outcome.status == "mismatch" and outcome.holder is not None:
            return JSONResponse(outcome.holder.to_payload(), status_code=HTTP_LOCKED)
        return JSONResponse({"released": outcome.status == "released", "detail": outcome.detail})

    # -- repave-tf client surface -------------------------------------------

    @router.get("/states")
    async def list_states(request: Request, tenant: str | None = None) -> JSONResponse:
        warning = require_client_role(request, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        with open_store() as store:
            items = store.list_states(tenant)
        return _json({"states": [item.to_payload() for item in items]}, warning=warning)

    @router.get("/states/{tenant}/{state}")
    async def describe_state(request: Request, tenant: str, state: str) -> JSONResponse:
        warning = require_client_role(request, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        with open_store() as store:
            summary = store.summary(tenant, state)
            if summary is None:
                raise HTTPException(status_code=404, detail="state not found")
            lock = store.current_lock(tenant, state)
        payload = summary.to_payload()
        payload["lock"] = lock.to_payload() if lock is not None else None
        return _json(payload, warning=warning)

    @router.get("/states/{tenant}/{state}/export")
    async def export_state(request: Request, tenant: str, state: str) -> Response:
        require_client_role(request, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        with open_store() as store:
            raw = _read_bytes(store, tenant, state)
        if raw is None:
            raise HTTPException(status_code=404, detail="state not found")
        return Response(content=raw, media_type="application/json")

    @router.post("/states/{tenant}/{state}/import")
    async def import_state(request: Request, tenant: str, state: str) -> JSONResponse:
        warning = require_client_role(request, ROLE_GENERATOR, ROLE_ADMIN)
        body = await request.body()
        with open_store() as store:
            outcome = store.write_state(tenant, state, body, author=actor(request))
        if outcome.status == "invalid":
            raise HTTPException(status_code=400, detail=outcome.detail)
        if outcome.status in ("conflict", "locked"):
            raise HTTPException(status_code=409, detail=outcome.detail)
        return _json(
            {
                "status": outcome.status,
                "detail": outcome.detail,
                "version_id": outcome.version_id,
                "serial": outcome.serial,
            },
            warning=warning,
        )

    @router.get("/states/{tenant}/{state}/versions")
    async def list_versions(
        request: Request, tenant: str, state: str, limit: int = 100
    ) -> JSONResponse:
        warning = require_client_role(request, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)
        with open_store() as store:
            if not store.state_exists(tenant, state):
                raise HTTPException(status_code=404, detail="state not found")
            versions = store.list_versions(tenant, state, limit=limit)
        return _json(
            {"versions": [item.to_payload() for item in versions]},
            warning=warning,
        )

    # -- resource graph -----------------------------------------------------

    def read_scope(request: Request) -> str:
        return require_client_role(request, ROLE_VIEWER, ROLE_GENERATOR, ROLE_ADMIN)

    @contextmanager
    def open_existing(tenant: str, state: str) -> Iterator[StateStore]:
        with open_store() as store:
            if not store.state_exists(tenant, state):
                raise HTTPException(status_code=404, detail="state not found")
            yield store

    @router.get("/states/{tenant}/{state}/resources")
    async def list_state_resources(
        request: Request,
        tenant: str,
        state: str,
        type: str | None = None,
        mode: str | None = None,
    ) -> JSONResponse:
        warning = read_scope(request)
        with open_existing(tenant, state) as store:
            rows = store.resources(tenant, state, resource_type=type, mode=mode)
        return _json({"resources": [row.to_payload() for row in rows]}, warning=warning)

    @router.get("/states/{tenant}/{state}/inventory")
    async def state_inventory(request: Request, tenant: str, state: str) -> JSONResponse:
        warning = read_scope(request)
        with open_existing(tenant, state) as store:
            entries = store.inventory(tenant, state)
        return _json(
            {
                "inventory": [entry.to_payload() for entry in entries],
                "total": sum(entry.count for entry in entries),
            },
            warning=warning,
        )

    @router.get("/states/{tenant}/{state}/graph")
    async def state_graph(request: Request, tenant: str, state: str) -> JSONResponse:
        warning = read_scope(request)
        with open_existing(tenant, state) as store:
            rows = store.resources(tenant, state)
            edges = store.edges(tenant, state)
        return _json(
            {
                "nodes": [row.to_payload() for row in rows],
                "edges": [
                    {"from": edge.from_address, "to": edge.to_address, "kind": edge.kind}
                    for edge in edges
                ],
            },
            warning=warning,
        )

    @router.get("/states/{tenant}/{state}/blast-radius")
    async def state_blast_radius(
        request: Request, tenant: str, state: str, address: str
    ) -> JSONResponse:
        warning = read_scope(request)
        with open_existing(tenant, state) as store:
            affected = store.blast_radius(tenant, state, address)
            depends_on = store.dependencies(tenant, state, address)
        return _json(
            {
                "address": address,
                "affected": affected,
                "affected_count": len(affected),
                "depends_on": depends_on,
            },
            warning=warning,
        )

    @router.post("/states/{tenant}/{state}/blast-radius/cost")
    async def state_blast_radius_cost(
        request: Request, tenant: str, state: str, address: str
    ) -> JSONResponse:
        """Price a blast radius against an Infracost breakdown posted by the client.

        Infracost keys resources by the same address the graph does, so this is a join
        rather than a second pricing run.
        """
        warning = read_scope(request)
        try:
            payload = json.loads(await request.body())
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"infracost breakdown must be JSON: {exc}"
            ) from exc

        with open_existing(tenant, state) as store:
            affected = store.blast_radius(tenant, state, address)
        scope = [address, *affected]
        costs = parse_resource_costs(payload)
        total, unpriced = total_monthly_cost(costs, scope)
        currency = next(iter(costs.values())).currency if costs else "USD"
        return _json(
            {
                "address": address,
                "scope": scope,
                "currency": currency,
                "monthly_cost": f"{total:.2f}",
                "unpriced": list(unpriced),
                "resources": [costs[item].to_public_dict() for item in scope if item in costs],
            },
            warning=warning,
        )

    @router.post("/states/{tenant}/{state}/drift")
    async def state_drift(request: Request, tenant: str, state: str) -> JSONResponse:
        """Compare stored attributes against a refreshed state posted by the client.

        The refresh runs client-side because the cloud credentials live there
        (ADR 004 decision 4); the body is a state document, not a plan.
        """
        warning = read_scope(request)
        body = await request.body()
        with open_existing(tenant, state) as store:
            try:
                entries = store.drift(tenant, state, body)
            except StateDocumentError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        changed = [entry for entry in entries if entry.status != "unchanged"]
        return _json(
            {
                "drift": [entry.to_payload() for entry in changed],
                "changed_count": len(changed),
                "compared_count": len(entries),
            },
            warning=warning,
        )

    @router.post("/provider-schemas")
    async def cache_provider_schema(
        request: Request, provider: str, version: str = ""
    ) -> JSONResponse:
        """Cache `providers schema -json` so writes redact beyond the name denylist."""
        warning = require_client_role(request, ROLE_GENERATOR, ROLE_ADMIN)
        try:
            payload = json.loads(await request.body())
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"provider schema must be JSON: {exc}"
            ) from exc
        with open_store() as store:
            learned = store.cache_provider_schema(payload, provider=provider, version=version)
        return _json({"provider": provider, "version": version, "types": learned}, warning=warning)

    # -- transactions ---------------------------------------------------------

    def write_scope(request: Request) -> str:
        return require_client_role(request, ROLE_GENERATOR, ROLE_ADMIN)

    @router.post("/states/{tenant}/{state}/tx")
    async def open_transaction(
        request: Request, tenant: str, state: str, operation: str = "apply"
    ) -> JSONResponse:
        """Open a transaction pinned to the state's current serial."""
        warning = write_scope(request)
        with open_store() as store:
            tx = store.open_transaction(tenant, state, author=actor(request), operation=operation)
        return _json(tx.to_payload(), warning=warning)

    @router.get("/states/{tenant}/{state}/tx")
    async def list_transactions(
        request: Request, tenant: str, state: str, status: str | None = None, limit: int = 50
    ) -> JSONResponse:
        warning = read_scope(request)
        with open_existing(tenant, state) as store:
            items = store.list_transactions(tenant, state, status=status, limit=limit)
        return _json({"transactions": [tx.to_payload() for tx in items]}, warning=warning)

    @router.get("/tx/{tx_id}")
    async def describe_transaction(request: Request, tx_id: str) -> JSONResponse:
        warning = read_scope(request)
        with open_store() as store:
            tx = store.transactions.get(tx_id)
        if tx is None:
            raise HTTPException(status_code=404, detail=f"no such transaction: {tx_id}")
        return _json(tx.to_payload(), warning=warning)

    @router.post("/tx/{tx_id}/preview")
    async def preview_transaction(request: Request, tx_id: str) -> JSONResponse:
        """Record the plan's read/write set and gate results, then dry-run the commit.

        The body is `{"plan": <tofu show -json output>, "gates": [...]}`. Conflicts
        reported here are advisory — another transaction can still land before commit,
        which is why commit re-checks.
        """
        warning = write_scope(request)
        payload = await _json_body(request)
        with open_store() as store:
            transactions = store.transactions
            existing = transactions.get(tx_id)
            if existing is None:
                raise HTTPException(status_code=404, detail=f"no such transaction: {tx_id}")

            recorded = transactions.record_resources(
                tx_id, resources_from_plan_json(payload.get("plan"))
            )
            if not recorded.ok:
                raise HTTPException(status_code=409, detail=recorded.detail)

            gated = transactions.record_gates(tx_id, parse_gate_outcomes(payload.get("gates")))
            if not gated.ok:
                raise HTTPException(status_code=409, detail=gated.detail)

            transactions.transition(tx_id, "previewing", detail="plan recorded")
            outcome = transactions.prepare_commit(tx_id)
        return _json(outcome.to_payload(), warning=warning)

    @router.post("/tx/{tx_id}/commit")
    async def commit_transaction(request: Request, tx_id: str) -> JSONResponse:
        """Commit a transaction with the post-apply state as the body."""
        warning = write_scope(request)
        body = await request.body()
        lock_id = request.query_params.get(LOCK_ID_PARAM) or None
        with open_store() as store:
            outcome = store.commit_transaction(tx_id, body, author=actor(request), lock_id=lock_id)
        if outcome.status == "absent":
            raise HTTPException(status_code=404, detail=outcome.detail)
        if outcome.status == "invalid":
            raise HTTPException(status_code=400, detail=outcome.detail)
        if outcome.status in ("conflict", "blocked"):
            return JSONResponse(outcome.to_payload(), status_code=HTTP_CONFLICT)
        return _json(outcome.to_payload(), warning=warning)

    @router.post("/tx/{tx_id}/abort")
    async def abort_transaction(request: Request, tx_id: str) -> JSONResponse:
        warning = write_scope(request)
        with open_store() as store:
            outcome = store.transactions.abort(tx_id)
        if outcome.transaction is None:
            raise HTTPException(status_code=404, detail=outcome.detail)
        if not outcome.ok:
            raise HTTPException(status_code=409, detail=outcome.detail)
        return _json(outcome.to_payload(), warning=warning)

    return router


async def _json_body(request: Request) -> dict[str, Any]:
    raw = await request.body()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"body must be JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    return payload


def _bootstrap_schema(config: StateStoreConfig) -> None:
    conn = connect(config.database)
    try:
        ensure_state_schema(conn)
    finally:
        conn.close()


def _read_bytes(store: StateStore, tenant: str, state: str) -> bytes | None:
    try:
        return store.read_current_bytes(tenant, state)
    except StateCorruptionError as exc:
        logger.error("state corruption for %s/%s: %s", tenant, state, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except StateCryptoError as exc:
        logger.error("state decryption failed for %s/%s: %s", tenant, state, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _write_response(outcome: Any) -> Response:
    if outcome.status == "invalid":
        raise HTTPException(status_code=400, detail=outcome.detail)
    if outcome.status == "locked":
        raise HTTPException(status_code=HTTP_LOCKED, detail=outcome.detail)
    if outcome.status == "conflict":
        raise HTTPException(status_code=409, detail=outcome.detail)
    return JSONResponse(
        {"status": outcome.status, "serial": outcome.serial, "version_id": outcome.version_id}
    )


def _json(payload: dict[str, Any], *, warning: str = "") -> JSONResponse:
    headers = {"Warning": warning} if warning else None
    return JSONResponse(payload, headers=headers)


def _basic_auth_ok(request: Request, config: AuthConfig) -> bool:
    header = request.headers.get("Authorization", "")
    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded.strip():
        return False
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return False
    _, _, password = decoded.partition(":")
    if not password or not config.api_token:
        return False
    return secrets.compare_digest(password, config.api_token)
