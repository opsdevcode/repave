from __future__ import annotations

from unittest.mock import patch

from repave_engine.live_plan import LivePlanSummary
from repave_engine.live_plan_pr import (
    LivePlanPrAttachmentResult,
    PullRequestRef,
    attach_live_plan_to_pull_request,
    merge_live_plan_section,
    parse_pull_request_ref,
    parse_pull_request_url,
    render_live_plan_section,
)


def _sample_summary() -> LivePlanSummary:
    return LivePlanSummary(
        entity_id="acme-tf-app",
        target="/tmp/mod",
        plan_ok=True,
        opa_passed=True,
        opa_skipped=False,
        opa_detail="ok",
        resource_add=2,
        resource_change=1,
        resource_destroy=0,
        detail="terraform plan succeeded",
    )


def test_parse_pull_request_url() -> None:
    ref = parse_pull_request_url("https://github.com/acme/tf-app/pull/42")
    assert ref == PullRequestRef(owner="acme", repo="tf-app", number=42)


def test_parse_pull_request_ref_from_block() -> None:
    ref = parse_pull_request_ref(
        {
            "kind": "live_plan",
            "entity_id": "svc",
            "pull_request": {"owner": "acme", "repo": "tf-app", "number": 7},
        }
    )
    assert ref == PullRequestRef(owner="acme", repo="tf-app", number=7)


def test_parse_pull_request_ref_from_url_field() -> None:
    ref = parse_pull_request_ref(
        {
            "kind": "live_plan",
            "entity_id": "svc",
            "pull_request_url": "https://github.com/acme/tf-app/pull/99/",
        }
    )
    assert ref == PullRequestRef(owner="acme", repo="tf-app", number=99)


def test_render_live_plan_section_omits_raw_json() -> None:
    body = render_live_plan_section(_sample_summary(), run_id="run-abc")
    assert "## Live plan against state" in body
    assert "+2 ~1 -0" in body
    assert "run-abc" in body
    assert "Plan JSON is not included" in body
    assert "resource_changes" not in body


def test_merge_live_plan_section_appends_then_replaces() -> None:
    section = render_live_plan_section(_sample_summary())
    first = merge_live_plan_section("Intro\n", section)
    assert "<!-- repave-live-plan -->" in first
    assert first.count("## Live plan against state") == 1

    updated = merge_live_plan_section(
        first,
        render_live_plan_section(
            LivePlanSummary(
                entity_id="acme-tf-app",
                target="/tmp/mod",
                plan_ok=False,
                opa_passed=False,
                opa_skipped=False,
                opa_detail="deny",
                resource_add=0,
                resource_change=0,
                resource_destroy=1,
                detail="plan failed",
            )
        ),
    )
    assert updated.count("## Live plan against state") == 1
    assert "failed" in updated
    assert updated.startswith("Intro\n")


def test_attach_live_plan_to_pull_request_without_token() -> None:
    ref = PullRequestRef(owner="acme", repo="tf-app", number=1)
    result = attach_live_plan_to_pull_request(
        ref,
        _sample_summary(),
        run_id="run-1",
        github_token=None,
    )
    assert result == LivePlanPrAttachmentResult(
        attached=False,
        pull_request_url="https://github.com/acme/tf-app/pull/1",
        detail="GITHUB_TOKEN is not configured; set it to attach live-plan results",
    )


def test_attach_live_plan_to_pull_request_updates_body() -> None:
    ref = PullRequestRef(owner="acme", repo="tf-app", number=1)
    with (
        patch(
            "repave_engine.live_plan_pr.get_pull_request",
            return_value={"body": "Existing PR text\n"},
        ) as get_pr,
        patch("repave_engine.live_plan_pr.update_pull_request_body") as update_pr,
    ):
        result = attach_live_plan_to_pull_request(
            ref,
            _sample_summary(),
            run_id="run-1",
            github_token="ghp_test",
        )
    assert result.attached is True
    get_pr.assert_called_once_with("acme", "tf-app", 1, "ghp_test")
    update_pr.assert_called_once()
    args = update_pr.call_args[0]
    assert args[0:3] == ("acme", "tf-app", 1)
    assert "<!-- repave-live-plan -->" in args[3]
    assert "Plan JSON is not included" in args[3]


def test_attach_live_plan_to_pull_request_surfaces_github_errors() -> None:
    ref = PullRequestRef(owner="acme", repo="tf-app", number=1)
    with patch(
        "repave_engine.live_plan_pr.get_pull_request",
        side_effect=RuntimeError("404 Not Found"),
    ):
        result = attach_live_plan_to_pull_request(
            ref,
            _sample_summary(),
            run_id="run-1",
            github_token="ghp_test",
        )
    assert result.attached is False
    assert "404" in result.detail
