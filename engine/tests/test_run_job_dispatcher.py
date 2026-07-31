from __future__ import annotations

import json
from unittest.mock import patch

from repave_engine.run_job_dispatcher import (
    KubernetesRunJobDispatcher,
    RunJobConfig,
    _build_job_body,
    build_run_job_dispatcher,
    job_name_for_run,
)
from repave_engine.worker_mode import WorkerMode


def test_job_name_for_run_is_dns_safe() -> None:
    run_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    name = job_name_for_run(run_id)
    assert name.startswith("repave-run-")
    assert len(name) <= 63
    assert name == job_name_for_run(run_id)


def test_build_job_body_includes_run_id_command() -> None:
    config = RunJobConfig(
        namespace="repave",
        image="ghcr.io/opsdevcode/repave-engine:1.0.0",
        image_pull_policy="IfNotPresent",
        service_account_name="repave",
        config_map_name="repave",
        runs_mount_path="/data/runs",
        github_secret_name="repave",
        database_url="postgresql://repave:secret@postgres/repave",
        artifact_store_uri=None,
        corpus_init_image="ghcr.io/opsdevcode/repave-corpus:1.0.0",
        github_org="example-org",
        modules_root="/data/modules",
        ttl_seconds_after_finished=3600,
        active_deadline_seconds=7200,
    )
    body = _build_job_body("run-123", config)
    container = body["spec"]["template"]["spec"]["containers"][0]
    assert container["command"][-2] == "run-123"
    assert body["metadata"]["labels"]["repave.dev/run-id"] == "run-123"
    assert body["spec"]["template"]["spec"]["initContainers"][0]["name"] == "corpus-init"
    env_names = {item["name"] for item in container["env"]}
    assert "GITHUB_TOKEN" in env_names
    assert "GITHUB_APP_ID" in env_names


def test_kubernetes_dispatcher_posts_job() -> None:
    config = RunJobConfig(
        namespace="repave",
        image="worker:tag",
        image_pull_policy="IfNotPresent",
        service_account_name="repave",
        config_map_name="repave",
        runs_mount_path="/data/runs",
        github_secret_name=None,
        database_url=None,
        artifact_store_uri=None,
        corpus_init_image=None,
        github_org="example-org",
        modules_root="/data/modules",
        ttl_seconds_after_finished=3600,
        active_deadline_seconds=7200,
    )
    dispatcher = KubernetesRunJobDispatcher(config)
    captured: dict[str, object] = {}

    def fake_create(namespace: str, body: dict[str, object]) -> None:
        captured["namespace"] = namespace
        captured["body"] = body

    with patch("repave_engine.run_job_dispatcher._create_namespaced_job", side_effect=fake_create):
        dispatcher.dispatch("abc-def")
    assert captured["namespace"] == "repave"
    body = captured["body"]
    assert isinstance(body, dict)
    assert json.dumps(body)


def test_build_run_job_dispatcher_job_mode_only() -> None:
    assert (
        build_run_job_dispatcher(__import__("pathlib").Path("."), worker_mode=WorkerMode.INLINE)
        is None
    )
    with patch.dict(
        "os.environ",
        {
            "REPAVE_RUN_JOBS": "1",
            "REPAVE_RUN_JOB_NAMESPACE": "repave",
            "REPAVE_RUN_JOB_IMAGE": "worker:1",
            "REPAVE_RUN_JOB_CONFIGMAP": "repave",
        },
        clear=False,
    ):
        dispatcher = build_run_job_dispatcher(
            __import__("pathlib").Path("."),
            worker_mode=WorkerMode.JOB,
        )
    assert isinstance(dispatcher, KubernetesRunJobDispatcher)
