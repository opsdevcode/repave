"""SQL-backed session middleware for multi-replica portal (cookie holds signed session id)."""

from __future__ import annotations

from typing import Any

from itsdangerous import BadSignature, URLSafeSerializer
from starlette.datastructures import MutableHeaders
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from repave_engine.session_store import SessionStore


class SqlSessionMiddleware:
    """Load and persist request.session in SQL; cookie stores a signed session id only."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret_key: str,
        session_store: SessionStore,
        session_cookie: str = "session",
        max_age: int = 14 * 24 * 60 * 60,
        same_site: str = "lax",
        https_only: bool = False,
        path: str = "/",
    ) -> None:
        self.app = app
        self.signer = URLSafeSerializer(secret_key, salt="repave-sql-session")
        self.session_store = session_store
        self.session_cookie = session_cookie
        self.max_age = max_age
        self.security_flags = f"httponly; samesite={same_site}"
        if https_only:
            self.security_flags += "; secure"
        self.path = path

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        session_id: str | None = None
        initial_session: dict[str, Any] = {}

        cookie = connection.cookies.get(self.session_cookie)
        if cookie:
            try:
                loaded_id = self.signer.loads(cookie)
                if isinstance(loaded_id, str) and loaded_id.strip():
                    session_id = loaded_id.strip()
                    loaded = self.session_store.load(session_id)
                    if loaded is not None:
                        initial_session = loaded
                    else:
                        session_id = None
            except BadSignature:
                session_id = None

        scope["session"] = initial_session.copy()
        scope["_sql_session_id"] = session_id

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session = scope.get("session")
                sid = scope.get("_sql_session_id")
                headers = MutableHeaders(scope=message)
                if session:
                    if not isinstance(session, dict):
                        session = dict(session)
                    if sid is None:
                        sid = self.session_store.create_id()
                        scope["_sql_session_id"] = sid
                    self.session_store.save(sid, dict(session))
                    cookie_value = self.signer.dumps(sid)
                    header_value = (
                        f"{self.session_cookie}={cookie_value}; path={self.path}; "
                        f"Max-Age={self.max_age}; {self.security_flags}"
                    )
                    headers.append("Set-Cookie", header_value)
                elif sid is not None:
                    self.session_store.delete(sid)
                    header_value = (
                        f"{self.session_cookie}=; path={self.path}; Max-Age=0; "
                        f"{self.security_flags}"
                    )
                    headers.append("Set-Cookie", header_value)
                elif self.session_cookie in connection.cookies:
                    header_value = (
                        f"{self.session_cookie}=; path={self.path}; Max-Age=0; "
                        f"{self.security_flags}"
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
