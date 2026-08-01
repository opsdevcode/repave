"""Read-only GitOps deployment status for portal catalog entities (ADR 003 Phase 1)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SyncStatus = Literal["synced", "out_of_sync", "unknown"]
HealthStatus = Literal["healthy", "degraded", "progressing", "unknown"]
DeploymentReader = Literal["url", "argocd", "flux"]


class DeploymentEntity(Protocol):
    @property
    def display_name(self) -> str: ...

    @property
    def entity_id(self) -> str: ...

    @property
    def owner(self) -> str: ...


@dataclass(frozen=True)
class DeploymentStatus:
    sync_status: SyncStatus
    health: HealthStatus
    revision: str
    last_synced: str
    detail: str
    deep_link: str
    source: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "sync_status": self.sync_status,
            "health": self.health,
            "revision": self.revision,
            "last_synced": self.last_synced,
            "detail": self.detail,
            "deep_link": self.deep_link,
            "source": self.source,
        }


def unknown_deployment_status(
    *,
    source: str,
    deep_link: str = "",
    detail: str = "Deployment status unavailable",
) -> DeploymentStatus:
    return DeploymentStatus(
        sync_status="unknown",
        health="unknown",
        revision="",
        last_synced="",
        detail=detail,
        deep_link=deep_link,
        source=source,
    )


def format_deployment_template(template: str, entity: DeploymentEntity) -> str | None:
    raw = template.strip()
    if not raw:
        return None
    try:
        return raw.format(
            name=entity.display_name,
            service=entity.display_name,
            entity_id=entity.entity_id,
            owner=entity.owner or "",
        )
    except KeyError:
        return raw.format(name=entity.display_name)


def _normalize_sync(raw: str) -> SyncStatus:
    lowered = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if lowered in ("synced", "sync", "in_sync"):
        return "synced"
    if lowered in ("out_of_sync", "outofsync", "drifted", "not_synced"):
        return "out_of_sync"
    return "unknown"


def _normalize_health(raw: str) -> HealthStatus:
    lowered = raw.strip().lower().replace(" ", "_").replace("-", "_")
    if lowered in ("healthy", "ok", "pass", "green", "ready"):
        return "healthy"
    if lowered in ("degraded", "unhealthy", "fail", "failed", "error", "red"):
        return "degraded"
    if lowered in ("progressing", "pending", "suspending", "reconciling"):
        return "progressing"
    return "unknown"


def parse_deployment_payload(
    payload: Any,
    *,
    source: str,
    deep_link: str = "",
) -> DeploymentStatus | None:
    """Parse the generic JSON contract used by the url reader."""
    if not isinstance(payload, dict):
        return None
    sync = _normalize_sync(str(payload.get("sync_status", payload.get("sync", "unknown"))))
    health = _normalize_health(str(payload.get("health", payload.get("health_status", "unknown"))))
    revision = str(payload.get("revision", payload.get("deployed_revision", ""))).strip()
    last_synced = str(
        payload.get("last_synced", payload.get("reconciled_at", payload.get("as_of", "")))
    ).strip()
    detail = str(payload.get("detail", payload.get("message", ""))).strip()
    link = str(payload.get("deep_link", payload.get("url", deep_link))).strip() or deep_link
    if not detail:
        detail = f"Sync {sync}; health {health}"
    return DeploymentStatus(
        sync_status=sync,
        health=health,
        revision=revision,
        last_synced=last_synced,
        detail=detail,
        deep_link=link,
        source=source,
    )


def resolve_deployment_reader(
    *,
    deployment_reader: str,
    deployment_status_url: str,
) -> DeploymentReader | None:
    explicit = deployment_reader.strip().lower()
    if explicit in ("url", "argocd", "flux"):
        return explicit  # type: ignore[return-value]
    if deployment_status_url.strip():
        return "url"
    return None


def deployment_reader_configured(
    *,
    deployment_reader: str,
    deployment_status_url: str,
) -> bool:
    return (
        resolve_deployment_reader(
            deployment_reader=deployment_reader,
            deployment_status_url=deployment_status_url,
        )
        is not None
    )


def fetch_deployment_status_url(
    template: str,
    entity: DeploymentEntity,
    *,
    timeout: float = 4.0,
) -> DeploymentStatus:
    url = format_deployment_template(template, entity)
    if not url:
        return unknown_deployment_status(
            source="url",
            detail="deployment_status_url template is empty or invalid",
        )
    try:
        response = httpx.get(url, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("deployment status url fetch failed for %s: %s", entity.entity_id, exc)
        return unknown_deployment_status(
            source="url",
            deep_link=url,
            detail="Deployment status endpoint unreachable",
        )
    parsed = parse_deployment_payload(payload, source="url", deep_link=url)
    if parsed is None:
        return unknown_deployment_status(
            source="url",
            deep_link=url,
            detail="Deployment status response was not a valid object",
        )
    return parsed


def _parse_argocd_application(payload: Any, *, deep_link: str) -> DeploymentStatus | None:
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if not isinstance(status, dict):
        return None
    sync_raw = status.get("sync")
    health_raw = status.get("health")
    sync_block: dict[str, Any] = sync_raw if isinstance(sync_raw, dict) else {}
    health_block: dict[str, Any] = health_raw if isinstance(health_raw, dict) else {}
    sync = _normalize_sync(str(sync_block.get("status", "unknown")))
    health = _normalize_health(str(health_block.get("status", "unknown")))
    revision = str(sync_block.get("revision", "")).strip()
    last_synced = str(status.get("reconciledAt", "")).strip()
    if not last_synced:
        operation = status.get("operationState")
        if isinstance(operation, dict):
            last_synced = str(operation.get("finishedAt", "")).strip()
    detail = f"Argo CD sync {sync}; health {health}"
    return DeploymentStatus(
        sync_status=sync,
        health=health,
        revision=revision,
        last_synced=last_synced,
        detail=detail,
        deep_link=deep_link,
        source="argocd",
    )


def fetch_deployment_status_argocd(
    *,
    base_url: str,
    application_template: str,
    entity: DeploymentEntity,
    token: str | None = None,
    timeout: float = 4.0,
) -> DeploymentStatus:
    base = base_url.strip().rstrip("/")
    app_name = format_deployment_template(application_template or "{name}", entity)
    if not base or not app_name:
        return unknown_deployment_status(
            source="argocd",
            detail="portal.deployment_argocd.base_url and application are required",
        )
    deep_link = f"{base}/applications/{quote(app_name, safe='')}"
    api_url = f"{base}/api/v1/applications/{quote(app_name, safe='')}"
    headers: dict[str, str] = {}
    auth = (token if token is not None else os.environ.get("REPAVE_ARGOCD_TOKEN", "")).strip()
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    try:
        response = httpx.get(api_url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("argocd deployment status failed for %s: %s", entity.entity_id, exc)
        return unknown_deployment_status(
            source="argocd",
            deep_link=deep_link,
            detail="Argo CD API unreachable",
        )
    parsed = _parse_argocd_application(payload, deep_link=deep_link)
    if parsed is None:
        return unknown_deployment_status(
            source="argocd",
            deep_link=deep_link,
            detail="Argo CD application response missing status",
        )
    return parsed


def _flux_ready_condition(status: dict[str, Any]) -> tuple[HealthStatus, str]:
    conditions = status.get("conditions")
    if not isinstance(conditions, list):
        return "unknown", ""
    for item in conditions:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).strip() != "Ready":
            continue
        ready = str(item.get("status", "")).strip().lower()
        message = str(item.get("message", "")).strip()
        last = str(item.get("lastTransitionTime", "")).strip()
        if ready == "true":
            return "healthy", last
        if ready == "false":
            return "degraded", last
        return "progressing", last or message
    return "unknown", ""


def _parse_flux_resource(payload: Any, *, deep_link: str, kind: str) -> DeploymentStatus | None:
    if not isinstance(payload, dict):
        return None
    status = payload.get("status")
    if not isinstance(status, dict):
        return None
    health, last_from_condition = _flux_ready_condition(status)
    revision = str(
        status.get("lastAppliedRevision", status.get("lastAttemptedRevision", ""))
    ).strip()
    last_synced = last_from_condition or str(status.get("lastHandledReconcileAt", "")).strip()
    sync: SyncStatus = "synced" if health == "healthy" and revision else "unknown"
    if health == "degraded":
        sync = "out_of_sync"
    detail = f"Flux {kind} health {health}"
    return DeploymentStatus(
        sync_status=sync,
        health=health,
        revision=revision,
        last_synced=last_synced,
        detail=detail,
        deep_link=deep_link,
        source="flux",
    )


def fetch_deployment_status_flux(
    *,
    api_server: str,
    namespace_template: str,
    name_template: str,
    kind: str,
    entity: DeploymentEntity,
    token: str | None = None,
    timeout: float = 4.0,
) -> DeploymentStatus:
    server = api_server.strip().rstrip("/")
    namespace = format_deployment_template(namespace_template or "default", entity)
    name = format_deployment_template(name_template or "{name}", entity)
    resource_kind = kind.strip().lower() or "kustomization"
    if not server or not namespace or not name:
        return unknown_deployment_status(
            source="flux",
            detail="portal.deployment_flux.api_server, namespace, and name are required",
        )
    if resource_kind == "helmrelease":
        api_path = (
            f"/apis/helm.toolkit.fluxcd.io/v2/namespaces/{quote(namespace, safe='')}"
            f"/helmreleases/{quote(name, safe='')}"
        )
    else:
        api_path = (
            f"/apis/kustomize.toolkit.fluxcd.io/v1/namespaces/{quote(namespace, safe='')}"
            f"/kustomizations/{quote(name, safe='')}"
        )
    api_url = f"{server}{api_path}"
    headers: dict[str, str] = {"Accept": "application/json"}
    auth = (token if token is not None else os.environ.get("REPAVE_FLUX_TOKEN", "")).strip()
    if not auth:
        auth = os.environ.get("REPAVE_KUBE_TOKEN", "").strip()
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    try:
        response = httpx.get(api_url, headers=headers, timeout=timeout, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("flux deployment status failed for %s: %s", entity.entity_id, exc)
        return unknown_deployment_status(
            source="flux",
            deep_link=api_url,
            detail="Flux Kubernetes API unreachable",
        )
    parsed = _parse_flux_resource(payload, deep_link=api_url, kind=resource_kind)
    if parsed is None:
        return unknown_deployment_status(
            source="flux",
            deep_link=api_url,
            detail="Flux resource response missing status",
        )
    return parsed


def fetch_entity_deployment_status_for_portal(
    portal_config: object,
    entity: DeploymentEntity,
) -> DeploymentStatus | None:
    """Dispatch to url, Argo CD, or Flux reader. None when not configured."""
    from repave_engine.settings import PortalConfig

    if not isinstance(portal_config, PortalConfig):
        return None
    reader = resolve_deployment_reader(
        deployment_reader=portal_config.deployment_reader,
        deployment_status_url=portal_config.deployment_status_url,
    )
    if reader is None:
        return None
    if reader == "url":
        return fetch_deployment_status_url(portal_config.deployment_status_url, entity)
    if reader == "argocd":
        return fetch_deployment_status_argocd(
            base_url=portal_config.deployment_argocd.base_url,
            application_template=portal_config.deployment_argocd.application,
            entity=entity,
        )
    return fetch_deployment_status_flux(
        api_server=portal_config.deployment_flux.api_server,
        namespace_template=portal_config.deployment_flux.namespace,
        name_template=portal_config.deployment_flux.name,
        kind=portal_config.deployment_flux.kind,
        entity=entity,
    )
