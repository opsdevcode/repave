"""In-cluster operator mutations from the platform console (kubectl)."""

from __future__ import annotations

import json
import subprocess

from repave_engine.fleet_operator_status import KubectlRunner, SubprocessKubectlRunner

_default_kubectl_runner = SubprocessKubectlRunner()


def patch_upgrade_campaign_paused(
    name: str,
    namespace: str,
    *,
    paused: bool,
    runner: KubectlRunner | None = None,
) -> None:
    resource_name = name.strip()
    resource_ns = namespace.strip() or "default"
    if not resource_name:
        raise ValueError("campaign name is required")
    payload = json.dumps({"spec": {"paused": paused}})
    cmd = [
        "kubectl",
        "patch",
        "upgradecampaign",
        resource_name,
        "-n",
        resource_ns,
        "--type=merge",
        "-p",
        payload,
    ]
    kubectl = runner if runner is not None else _default_kubectl_runner
    result = kubectl.run(cmd, timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "kubectl patch failed").strip()
        raise RuntimeError(
            f"kubectl patch upgradecampaign/{resource_name} failed: {detail}; "
            "install kubectl, select a cluster context, and ensure RBAC can patch "
            "repave.dev/upgradecampaigns"
        )


class RecordingKubectlRunner:
    """Test double that records patch commands."""

    def __init__(self, *, returncode: int = 0, stderr: str = "") -> None:
        self.commands: list[list[str]] = []
        self.returncode = returncode
        self.stderr = stderr

    def run(self, cmd: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
        self.commands.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=self.returncode,
            stdout="",
            stderr=self.stderr,
        )
