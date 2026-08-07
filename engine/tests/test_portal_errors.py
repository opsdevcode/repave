from __future__ import annotations

from starlette.requests import Request

from repave_engine.portal_errors import (
    format_portal_error_message,
    wants_portal_html_response,
)


def _request(
    *,
    method: str = "GET",
    path: str = "/",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers or [],
        "query_string": b"",
    }
    return Request(scope)


def test_wants_portal_html_response_for_multipart_generate_post() -> None:
    request = _request(
        method="POST",
        path="/generate",
        headers=[
            (b"content-type", b"multipart/form-data; boundary=abc"),
            (b"accept", b"text/html,application/json;q=0.9"),
        ],
    )
    assert wants_portal_html_response(request) is True


def test_wants_portal_html_response_honors_json_only_accept() -> None:
    request = _request(
        method="POST",
        path="/generate",
        headers=[
            (b"content-type", b"multipart/form-data; boundary=abc"),
            (b"accept", b"application/json"),
        ],
    )
    assert wants_portal_html_response(request) is False


def test_format_portal_error_message_maps_insufficient_role() -> None:
    message = format_portal_error_message(status_code=403, detail="Insufficient role")
    assert "generator access" in message
