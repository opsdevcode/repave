from __future__ import annotations

import pytest

from repave_engine.fleet_operator_actions import (
    RecordingKubectlRunner,
    patch_upgrade_campaign_paused,
)


def test_patch_upgrade_campaign_paused_merge_patch() -> None:
    runner = RecordingKubectlRunner()
    patch_upgrade_campaign_paused(
        "platform-rollout",
        "repave-system",
        paused=True,
        runner=runner,
    )
    assert len(runner.commands) == 1
    cmd = runner.commands[0]
    assert cmd[:6] == [
        "kubectl",
        "patch",
        "upgradecampaign",
        "platform-rollout",
        "-n",
        "repave-system",
    ]
    assert "--type=merge" in cmd
    assert '{"spec": {"paused": true}}' in cmd


def test_patch_upgrade_campaign_paused_requires_name() -> None:
    with pytest.raises(ValueError, match="campaign name"):
        patch_upgrade_campaign_paused("", "default", paused=False)


def test_patch_upgrade_campaign_paused_surfaces_kubectl_error() -> None:
    runner = RecordingKubectlRunner(returncode=1, stderr="Forbidden")
    with pytest.raises(RuntimeError, match="Forbidden"):
        patch_upgrade_campaign_paused("demo", "default", paused=True, runner=runner)
