"""HTML-friendly errors for browser portal form posts (not JSON APIs)."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse

PORTAL_FORM_POST_PATHS = frozenset(
    {
        "/generate",
        "/update",
        "/verify",
        "/import",
        "/fleet/register",
        "/fleet/unregister",
    }
)


def wants_portal_html_response(request: Request) -> bool:
    """True when the client expects a portal HTML page instead of JSON."""
    path = request.url.path
    if path.startswith("/api/"):
        return False

    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return False

    content_type = request.headers.get("content-type", "")
    if request.method == "POST" and (
        "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type
    ):
        return True

    if "text/html" in accept:
        return True

    if request.method in ("GET", "HEAD"):
        return True
    return request.method == "POST" and path in PORTAL_FORM_POST_PATHS


def portal_back_href(request: Request) -> str:
    referer = request.headers.get("referer", "").strip()
    if referer.startswith(("http://", "https://")):
        return referer
    return "/"


def format_portal_error_message(*, status_code: int, detail: Any) -> str:
    text = _detail_text(detail)
    if status_code == 401:
        return "Sign in required. Refresh the page and sign in again."
    if status_code == 403 and "insufficient role" in text.lower():
        return (
            "You need generator access to run this action. "
            "Ask a platform admin to add you to the generators group (repave-generators)."
        )
    if status_code == 429:
        return text or "Too many requests. Wait a moment and try again."
    if status_code == 503:
        return text or "Service temporarily unavailable. Try again shortly."
    return text or f"Request failed ({status_code})."


def _detail_text(detail: Any) -> str:
    if isinstance(detail, list):
        parts: list[str] = []
        for item in detail:
            if isinstance(item, dict) and item.get("msg"):
                parts.append(str(item["msg"]))
            else:
                parts.append(str(item))
        return "; ".join(part for part in parts if part)
    if detail is None:
        return ""
    return str(detail).strip()


def portal_login_redirect(request: Request) -> RedirectResponse:
    next_path = portal_back_href(request)
    if not next_path.startswith("/"):
        next_path = "/"
    return RedirectResponse(f"/auth/login?next={quote(next_path, safe='')}", status_code=302)
