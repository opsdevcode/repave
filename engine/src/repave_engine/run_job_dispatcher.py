"""Dispatch per-run Kubernetes Jobs (service decomposition Phase 4)."""

from __future__ import annotations

import json
import logging
import os
import re
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from repave_engine.worker_mode import WorkerMode

logger = logging.getLogger(__name__)

_RUN_ID_LABEL_MAX = 63
_JOB_NAME_PREFIX = "repave-run-"


class RunJobDispatcher(Protocol):
    def dispatch(
        self,
        run_id: str,
        *,
        live_plan_secret_name: str | None = None,
    ) -> None: ...


@dataclass(frozen=True)
class RunJobConfig:
    namespace: str
    image: str
    image_pull_policy: str
    service_account_name: str
    config_map_name: str
    runs_mount_path: str
    github_secret_name: str | None
    database_url: str | None
    artifact_store_uri: str | None
    corpus_init_image: str | None
    github_org: str
    modules_root: str
    ttl_seconds_after_finished: int
    active_deadline_seconds: int


def job_name_for_run(run_id: str) -> str:
    suffix = re.sub(r"[^a-z0-9]", "", run_id.lower())[:16]
    name = f"{_JOB_NAME_PREFIX}{suffix}"
    return name[:_RUN_ID_LABEL_MAX].rstrip("-.")


def load_run_job_config(_repo_root: Path) -> RunJobConfig | None:
    if os.environ.get("REPAVE_RUN_JOBS", "").strip().lower() not in ("1", "true", "yes"):
        return None
    namespace = os.environ.get("REPAVE_RUN_JOB_NAMESPACE", "").strip()
    image = os.environ.get("REPAVE_RUN_JOB_IMAGE", "").strip()
    config_map = os.environ.get("REPAVE_RUN_JOB_CONFIGMAP", "").strip()
    if not namespace or not image or not config_map:
        logger.warning(
            "REPAVE_RUN_JOBS=1 but namespace/image/configmap env vars are incomplete; "
            "skipping Job dispatch"
        )
        return None
    service_account = os.environ.get(
        "REPAVE_RUN_JOB_SERVICE_ACCOUNT",
        os.environ.get("REPAVE_RUN_JOB_SERVICE_ACCOUNT_NAME", "default"),
    ).strip()
    github_secret = os.environ.get("REPAVE_RUN_JOB_GITHUB_SECRET", "").strip() or None
    database_url = os.environ.get("REPAVE_DATABASE_URL", "").strip() or None
    artifact_store_uri = os.environ.get("REPAVE_ARTIFACT_STORE_URI", "").strip() or None
    corpus_init_image = os.environ.get("REPAVE_RUN_JOB_CORPUS_IMAGE", "").strip() or None
    github_org = os.environ.get("REPAVE_GITHUB_ORG", "").strip()
    modules_root = os.environ.get("REPAVE_MODULES_ROOT", "/data/modules").strip()
    ttl_raw = os.environ.get("REPAVE_RUN_JOB_TTL_SECONDS", "3600").strip()
    deadline_raw = os.environ.get("REPAVE_RUN_JOB_ACTIVE_DEADLINE_SECONDS", "7200").strip()
    return RunJobConfig(
        namespace=namespace,
        image=image,
        image_pull_policy=os.environ.get("REPAVE_RUN_JOB_IMAGE_PULL_POLICY", "IfNotPresent"),
        service_account_name=service_account or "default",
        config_map_name=config_map,
        runs_mount_path=os.environ.get("REPAVE_RUNS_DB", "/data/runs/runs.sqlite").rsplit("/", 1)[0]
        or "/data/runs",
        github_secret_name=github_secret,
        database_url=database_url,
        artifact_store_uri=artifact_store_uri,
        corpus_init_image=corpus_init_image,
        github_org=github_org,
        modules_root=modules_root,
        ttl_seconds_after_finished=int(ttl_raw),
        active_deadline_seconds=int(deadline_raw),
    )


def build_run_job_dispatcher(
    repo_root: Path,
    *,
    worker_mode: WorkerMode,
) -> RunJobDispatcher | None:
    if worker_mode != WorkerMode.JOB:
        return None
    config = load_run_job_config(repo_root)
    if config is None:
        return _LoggingRunJobDispatcher()
    return KubernetesRunJobDispatcher(config)


class _LoggingRunJobDispatcher:
    """Fallback when job mode is configured but in-cluster Job env is missing."""

    def dispatch(
        self,
        run_id: str,
        *,
        live_plan_secret_name: str | None = None,
    ) -> None:
        del live_plan_secret_name
        logger.warning(
            "worker_mode=job but Run Job config is incomplete; run %s remains queued "
            "(set REPAVE_RUN_JOBS and Job env vars or run repave run-worker manually)",
            run_id,
        )


def _github_auth_env(secret_name: str) -> list[dict[str, Any]]:
    specs = (
        ("GITHUB_TOKEN", "github-token"),
        ("GITHUB_APP_ID", "github-app-id"),
        ("GITHUB_APP_INSTALLATION_ID", "github-app-installation-id"),
        ("GITHUB_APP_PRIVATE_KEY", "github-app-private-key"),
        ("INFRACOST_API_KEY", "infracost-api-key"),
    )
    env: list[dict[str, Any]] = []
    for env_name, secret_key in specs:
        env.append(
            {
                "name": env_name,
                "valueFrom": {
                    "secretKeyRef": {
                        "name": secret_name,
                        "key": secret_key,
                        "optional": True,
                    }
                },
            }
        )
    return env


class KubernetesRunJobDispatcher:
    def __init__(self, config: RunJobConfig) -> None:
        self._config = config

    def dispatch(
        self,
        run_id: str,
        *,
        live_plan_secret_name: str | None = None,
    ) -> None:
        body = _build_job_body(
            run_id,
            self._config,
            live_plan_secret_name=live_plan_secret_name,
        )
        _create_namespaced_job(self._config.namespace, body)


def _build_job_body(
    run_id: str,
    config: RunJobConfig,
    *,
    live_plan_secret_name: str | None = None,
) -> dict[str, Any]:
    name = job_name_for_run(run_id)
    env: list[dict[str, Any]] = [
        {"name": "REPAVE_IMAGE_GATE_TOOLCHAIN", "value": "1"},
        {"name": "REPAVE_ASYNC_GENERATION", "value": "1"},
        {"name": "REPAVE_EXTERNAL_WORKERS", "value": "1"},
        {"name": "REPAVE_RUNS_DB", "value": f"{config.runs_mount_path.rstrip('/')}/runs.sqlite"},
        {"name": "REPAVE_GITHUB_ORG", "value": config.github_org},
        {"name": "REPAVE_MODULES_ROOT", "value": config.modules_root},
    ]
    if config.database_url:
        env.append({"name": "REPAVE_DATABASE_URL", "value": config.database_url})
    if config.artifact_store_uri:
        env.append({"name": "REPAVE_ARTIFACT_STORE_URI", "value": config.artifact_store_uri})
    if config.github_secret_name:
        env.extend(_github_auth_env(config.github_secret_name))

    volume_mounts: list[dict[str, Any]] = [
        {
            "name": "config",
            "mountPath": "/app/repave.config.yaml",
            "subPath": "repave.config.yaml",
        },
        {"name": "runs", "mountPath": config.runs_mount_path},
    ]
    volumes: list[dict[str, Any]] = [
        {"name": "config", "configMap": {"name": config.config_map_name}},
        {"name": "runs", "emptyDir": {}},
    ]

    init_containers: list[dict[str, Any]] = []
    if config.corpus_init_image:
        init_containers.append(
            {
                "name": "corpus-init",
                "image": config.corpus_init_image,
                "command": ["/bin/sh", "-c", "cp -a /app/. /corpus-data/"],
                "volumeMounts": [{"name": "corpus-data", "mountPath": "/corpus-data"}],
            }
        )
        volumes.append({"name": "corpus-data", "emptyDir": {}})
        for sub_path, mount_path in (
            ("schemas", "/app/schemas"),
            ("blueprints", "/app/blueprints"),
            ("standards", "/app/standards"),
            ("policy", "/app/policy"),
            ("ansible", "/app/ansible"),
            ("observability", "/app/observability"),
        ):
            volume_mounts.append(
                {
                    "name": "corpus-data",
                    "mountPath": mount_path,
                    "subPath": sub_path,
                }
            )

    container: dict[str, Any] = {
        "name": "run-worker",
        "image": config.image,
        "imagePullPolicy": config.image_pull_policy,
        "command": [
            "repave",
            "run-worker",
            "--repo-root",
            "/app",
            "--run-id",
            run_id,
            "--once",
        ],
        "env": env,
        "volumeMounts": volume_mounts,
    }
    secret_name = (live_plan_secret_name or "").strip()
    if secret_name:
        # Per-environment cloud/backend credentials for ADR 003 live_plan Jobs.
        container["envFrom"] = [{"secretRef": {"name": secret_name}}]

    pod_spec: dict[str, Any] = {
        "restartPolicy": "Never",
        "serviceAccountName": config.service_account_name,
        "containers": [container],
        "volumes": volumes,
    }
    if init_containers:
        pod_spec["initContainers"] = init_containers

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": name,
            "labels": {
                "app.kubernetes.io/name": "repave",
                "app.kubernetes.io/component": "run-job",
                "repave.dev/run-id": run_id,
            },
        },
        "spec": {
            "ttlSecondsAfterFinished": config.ttl_seconds_after_finished,
            "activeDeadlineSeconds": config.active_deadline_seconds,
            "backoffLimit": 0,
            "template": {
                "metadata": {
                    "labels": {
                        "app.kubernetes.io/name": "repave",
                        "app.kubernetes.io/component": "run-job",
                        "repave.dev/run-id": run_id,
                    }
                },
                "spec": pod_spec,
            },
        },
    }


def _in_cluster_api_base() -> tuple[str, str]:
    host = os.environ.get("KUBERNETES_SERVICE_HOST", "").strip()
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443").strip()
    token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
    if not host or not token_path.is_file():
        raise RuntimeError("Kubernetes in-cluster credentials are not available")
    token = token_path.read_text(encoding="utf-8").strip()
    base = f"https://{host}:{port}"
    return base, token


def _create_namespaced_job(namespace: str, body: dict[str, Any]) -> None:
    base, token = _in_cluster_api_base()
    url = f"{base}/apis/batch/v1/namespaces/{namespace}/jobs"
    payload = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(  # nosec B310
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    context = ssl.create_default_context()
    ca_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
    if ca_path.is_file():
        context.load_verify_locations(cafile=str(ca_path))
    try:
        with urllib.request.urlopen(request, context=context, timeout=30) as response:  # nosec B310
            if response.status not in (200, 201):
                raise RuntimeError(f"unexpected Job create status: {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 409:
            logger.info("run Job already exists for create request: %s", detail[:200])
            return
        raise RuntimeError(f"Kubernetes Job create failed ({exc.code}): {detail}") from exc
