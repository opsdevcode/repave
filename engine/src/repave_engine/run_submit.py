"""Shared async run submission helpers (blueprint, bundle, live_plan, environment_vend)."""

from __future__ import annotations

from typing import Any

from repave_engine.environment_vend import (
    ENVIRONMENT_VEND_BLUEPRINT_SENTINEL,
    resolve_vend_request_fields,
)
from repave_engine.live_plan import LIVE_PLAN_BLUEPRINT_SENTINEL
from repave_engine.live_plan_pr import parse_pull_request_ref
from repave_engine.platform_runs import (
    ENVIRONMENT_RECLAIM_SENTINEL,
    FLEET_DRIFT_CONFIRM_SENTINEL,
    load_environment_reclaim_config,
)
from repave_engine.run_queue import RunQueue
from repave_engine.run_store import RunRecord
from repave_engine.settings import (
    load_environment_vending_config,
    load_live_plan_config,
)


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
    if kind == "environment_vend":
        return _submit_environment_vend(
            queue,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id,
            repo_root=repo_root,
        )
    if kind == "environment_reclaim":
        return _submit_environment_reclaim(
            queue,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id,
            repo_root=repo_root,
        )
    if kind == "fleet_drift_confirm":
        return _submit_fleet_drift_confirm(
            queue,
            payload=payload,
            acting_user=acting_user,
            client_request_id=client_request_id,
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


def _submit_environment_vend(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None,
    repo_root: Any | None,
) -> RunRecord:
    from pathlib import Path

    root = Path(repo_root) if repo_root is not None else queue.repo_root
    config = load_environment_vending_config(root)
    if config is None or not config.enabled:
        raise ValueError(
            "environment_vending is not enabled; set environment_vending.enabled in "
            "repave.config.yaml or REPAVE_ENVIRONMENT_VENDING=1"
        )
    (
        blueprint,
        gitops_repo,
        gitops_path,
        owner,
        env_class,
        base_branch,
        dry_run,
    ) = resolve_vend_request_fields(payload, config)
    inputs_raw = payload.get("inputs", {})
    if not isinstance(inputs_raw, dict):
        raise ValueError("inputs must be an object")
    git_branch = str(payload.get("git_branch", "")).strip()
    entity_id = str(payload.get("entity_id", "")).strip()
    vend_meta: dict[str, str] = {
        "blueprint": blueprint,
        "gitops_repo": gitops_repo,
        "gitops_path": gitops_path,
        "owner": owner,
        "class": env_class,
        "base_branch": base_branch,
        "git_branch": git_branch,
    }
    if entity_id:
        vend_meta["entity_id"] = entity_id
    return queue.submit(
        blueprint_name=ENVIRONMENT_VEND_BLUEPRINT_SENTINEL,
        inputs=dict(inputs_raw),
        dry_run=dry_run,
        acting_user=acting_user,
        client_request_id=client_request_id,
        kind="environment_vend",
        environment_vend=vend_meta,
    )


def is_bundle_run(record: RunRecord) -> bool:
    return bool(record.payload.get("bundle"))


def is_live_plan_run(record: RunRecord) -> bool:
    return str(record.payload.get("kind", "")).strip() == "live_plan"


def is_environment_vend_run(record: RunRecord) -> bool:
    return str(record.payload.get("kind", "")).strip() == "environment_vend"


def is_environment_reclaim_run(record: RunRecord) -> bool:
    return str(record.payload.get("kind", "")).strip() == "environment_reclaim"


def is_fleet_drift_confirm_run(record: RunRecord) -> bool:
    return str(record.payload.get("kind", "")).strip() == "fleet_drift_confirm"


def _submit_environment_reclaim(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None,
    repo_root: Any | None,
) -> RunRecord:
    from pathlib import Path

    root = Path(repo_root) if repo_root is not None else queue.repo_root
    load_environment_reclaim_config(root)
    dry_run = bool(payload.get("dry_run", True))
    stack_name = str(payload.get("stack_name", "")).strip()
    inputs: dict[str, Any] = {}
    if stack_name:
        inputs["stack_name"] = stack_name
    return queue.submit(
        blueprint_name=ENVIRONMENT_RECLAIM_SENTINEL,
        inputs=inputs,
        dry_run=dry_run,
        acting_user=acting_user,
        client_request_id=client_request_id,
        kind="environment_reclaim",
    )


def _submit_fleet_drift_confirm(
    queue: RunQueue,
    *,
    payload: dict[str, Any],
    acting_user: str,
    client_request_id: str | None,
) -> RunRecord:
    repo_urls_raw = payload.get("repo_urls", [])
    if not isinstance(repo_urls_raw, list) or not repo_urls_raw:
        raise ValueError("repo_urls must be a non-empty list")
    repo_urls = [str(item).strip() for item in repo_urls_raw if str(item).strip()]
    if not repo_urls:
        raise ValueError("repo_urls must include at least one repository URL")
    return queue.submit(
        blueprint_name=FLEET_DRIFT_CONFIRM_SENTINEL,
        inputs={"repo_urls": repo_urls},
        dry_run=True,
        acting_user=acting_user,
        client_request_id=client_request_id,
        kind="fleet_drift_confirm",
    )
