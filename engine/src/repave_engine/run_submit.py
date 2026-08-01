"""Shared async run submission helpers (blueprint, bundle, or live_plan)."""

from __future__ import annotations

from typing import Any

from repave_engine.live_plan import LIVE_PLAN_BLUEPRINT_SENTINEL
from repave_engine.live_plan_pr import parse_pull_request_ref
from repave_engine.run_queue import RunQueue
from repave_engine.run_store import RunRecord
from repave_engine.settings import load_live_plan_config


def parse_run_target(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    blueprint_name = str(payload.get("blueprint", "")).strip()
    bundle_name = str(payload.get("bundle", "")).strip()
    if blueprint_name and bundle_name:
        raise ValueError("provide only one of blueprint or bundle")
    if not blueprint_name and not bundle_name:
        raise ValueError("blueprint or bundle is required")
    return blueprint_name or None, bundle_name or None


def submit_async_run(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None = None,
    repo_root: Any | None = None,
) -> RunRecord:
    kind = str(payload.get("kind", "")).strip()
    if kind == "live_plan":
        return _submit_live_plan(
            queue,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id,
            repo_root=repo_root,
        )
    blueprint_name, bundle_name = parse_run_target(payload)
    inputs_raw = payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise ValueError("inputs must be an object")
    dry_run = bool(payload.get("dry_run", True))
    return queue.submit(
        blueprint_name=blueprint_name,
        bundle_name=bundle_name,
        inputs=inputs_raw,
        dry_run=dry_run,
        acting_user=acting_user,
        client_request_id=client_request_id,
    )


def _submit_live_plan(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None,
    repo_root: Any | None,
) -> RunRecord:
    from pathlib import Path

    entity_id = str(payload.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("entity_id is required for kind=live_plan")
    root = Path(repo_root) if repo_root is not None else queue.repo_root
    config = load_live_plan_config(root)
    if config is None or not config.enabled:
        raise ValueError(
            "live_plan is not enabled; set live_plan.enabled in repave.config.yaml "
            "or REPAVE_LIVE_PLAN=1"
        )
    env = config.environment_for(entity_id)
    target = str(payload.get("target", "")).strip()
    if not target:
        if env is None or not env.target:
            raise ValueError(
                f"no live_plan.environments entry for {entity_id!r} and no target override"
            )
        target = env.target
    job_secret_ref: str | None = None
    policies_dir = config.policies_dir
    use_backend = True
    if env is not None:
        job_secret_ref = env.secret_name.strip() or None
        policies_dir = env.policies_dir or policies_dir
        use_backend = env.use_backend
    secret_override = str(payload.get("secret_name", "")).strip()
    if secret_override:
        job_secret_ref = secret_override
    pull_request = parse_pull_request_ref(payload)
    return queue.submit(
        blueprint_name=LIVE_PLAN_BLUEPRINT_SENTINEL,
        inputs={
            "entity_id": entity_id,
            "target": target,
            "policies_dir": policies_dir,
            "use_backend": use_backend,
        },
        dry_run=True,
        acting_user=acting_user,
        client_request_id=client_request_id,
        kind="live_plan",
        live_plan_secret_name=job_secret_ref,
        pull_request=pull_request.to_dict() if pull_request is not None else None,
    )


def is_bundle_run(record: RunRecord) -> bool:
    return bool(record.payload.get("bundle"))


def is_live_plan_run(record: RunRecord) -> bool:
    return str(record.payload.get("kind", "")).strip() == "live_plan"
