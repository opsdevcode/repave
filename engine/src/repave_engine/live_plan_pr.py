"""Attach live-plan summaries to GitHub pull request bodies (ADR 003 Phase 2)."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from repave_engine.github import get_pull_request, update_pull_request_body
from repave_engine.live_plan import LivePlanSummary

logger = logging.getLogger(__name__)

_LIVE_PLAN_SECTION_START = "<!-- repave-live-plan -->"
_LIVE_PLAN_SECTION_END = "<!-- /repave-live-plan -->"
_LIVE_PLAN_SECTION_RE = re.compile(
    re.escape(_LIVE_PLAN_SECTION_START) + r".*?" + re.escape(_LIVE_PLAN_SECTION_END) + r"\n?",
    re.DOTALL,
)
_PULL_REQUEST_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)/?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PullRequestRef:
    owner: str
    repo: str
    number: int

    @property
    def html_url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}/pull/{self.number}"

    def to_dict(self) -> dict[str, Any]:
        return {"owner": self.owner, "repo": self.repo, "number": self.number}

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PullRequestRef | None:
        owner = str(raw.get("owner", "")).strip()
        repo = str(raw.get("repo", "")).strip()
        number_raw = raw.get("number")
        if number_raw is None:
            return None
        try:
            number = int(number_raw)
        except (TypeError, ValueError):
            return None
        if not owner or not repo or number <= 0:
            return None
        return cls(owner=owner, repo=repo, number=number)


@dataclass(frozen=True)
class LivePlanPrAttachmentResult:
    attached: bool
    pull_request_url: str
    detail: str

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "attached": self.attached,
            "pull_request_url": self.pull_request_url,
            "detail": self.detail,
        }


def parse_pull_request_ref(payload: Mapping[str, Any]) -> PullRequestRef | None:
    """Parse optional PR coordinates from a live_plan submit payload."""
    block = payload.get("pull_request")
    if isinstance(block, dict):
        ref = PullRequestRef.from_dict(block)
        if ref is not None:
            return ref
    url = str(payload.get("pull_request_url", "")).strip()
    if url:
        return parse_pull_request_url(url)
    return None


def parse_pull_request_url(url: str) -> PullRequestRef | None:
    normalized = url.strip()
    if not normalized:
        return None
    match = _PULL_REQUEST_URL_RE.match(normalized)
    if match is not None:
        return PullRequestRef(
            owner=match.group("owner"),
            repo=match.group("repo"),
            number=int(match.group("number")),
        )
    parsed = urlparse(normalized)
    if parsed.netloc.lower() != "github.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 4 or parts[2] != "pull":
        return None
    try:
        number = int(parts[3])
    except ValueError:
        return None
    owner, repo = parts[0], parts[1]
    if not owner or not repo or number <= 0:
        return None
    return PullRequestRef(owner=owner, repo=repo, number=number)


def render_live_plan_section(
    summary: LivePlanSummary | Mapping[str, Any],
    *,
    run_id: str = "",
) -> str:
    data = summary.to_public_dict() if isinstance(summary, LivePlanSummary) else dict(summary)
    entity_id = str(data.get("entity_id", "")).strip() or "unknown"
    target = str(data.get("target", "")).strip() or "unknown"
    plan_ok = bool(data.get("plan_ok"))
    opa_passed = bool(data.get("opa_passed"))
    opa_skipped = bool(data.get("opa_skipped"))
    opa_detail = str(data.get("opa_detail", "")).strip()
    detail = str(data.get("detail", "")).strip()
    resource_add = int(data.get("resource_add", 0))
    resource_change = int(data.get("resource_change", 0))
    resource_destroy = int(data.get("resource_destroy", 0))

    lines = [
        "## Live plan against state",
        "",
        f"- **Entity:** `{entity_id}`",
        f"- **Target:** `{target}`",
        f"- **Plan:** {'ok' if plan_ok else 'failed'}",
        (f"- **Resources:** +{resource_add} ~{resource_change} -{resource_destroy}"),
    ]
    if run_id.strip():
        lines.append(f"- **Run:** `{run_id.strip()}`")
    if opa_skipped:
        lines.append("- **Policy (OPA):** skipped")
    elif opa_passed:
        lines.append("- **Policy (OPA):** passed")
    else:
        suffix = f" — {opa_detail}" if opa_detail else ""
        lines.append(f"- **Policy (OPA):** failed{suffix}")
    if detail:
        lines.append(f"- **Detail:** {detail}")
    lines.extend(
        [
            "",
            "_Plan JSON is not included; see the repave run console for the audit trail._",
        ]
    )
    return "\n".join(lines)


def merge_live_plan_section(body: str, section: str) -> str:
    wrapped = f"{_LIVE_PLAN_SECTION_START}\n{section.rstrip()}\n{_LIVE_PLAN_SECTION_END}\n"
    if _LIVE_PLAN_SECTION_RE.search(body):
        return _LIVE_PLAN_SECTION_RE.sub(wrapped, body)
    trimmed = body.rstrip()
    if trimmed:
        return trimmed + "\n\n" + wrapped
    return wrapped


def attach_live_plan_to_pull_request(
    pull_request: PullRequestRef,
    summary: LivePlanSummary | Mapping[str, Any],
    *,
    run_id: str,
    github_token: str | None,
) -> LivePlanPrAttachmentResult:
    """Best-effort PR body update; never raises for expected GitHub failures."""
    url = pull_request.html_url
    if not github_token:
        return LivePlanPrAttachmentResult(
            attached=False,
            pull_request_url=url,
            detail="GITHUB_TOKEN is not configured; set it to attach live-plan results",
        )
    try:
        current = get_pull_request(
            pull_request.owner,
            pull_request.repo,
            pull_request.number,
            github_token,
        )
        body = str(current.get("body") or "")
        section = render_live_plan_section(summary, run_id=run_id)
        merged = merge_live_plan_section(body, section)
        update_pull_request_body(
            pull_request.owner,
            pull_request.repo,
            pull_request.number,
            merged,
            github_token,
        )
    except Exception as exc:
        logger.warning(
            "live_plan PR attachment failed for %s run %s: %s",
            url,
            run_id,
            exc,
        )
        return LivePlanPrAttachmentResult(
            attached=False,
            pull_request_url=url,
            detail=str(exc),
        )
    return LivePlanPrAttachmentResult(
        attached=True,
        pull_request_url=url,
        detail="live plan summary appended to pull request body",
    )
