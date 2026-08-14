#!/usr/bin/env python3
"""Capture the hosted public landing page (service mode, no session)."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
ENGINE_SRC = ROOT / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from playwright.sync_api import Route, sync_playwright  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from repave_engine.api import create_app  # noqa: E402
from repave_engine.settings import load_output_config  # noqa: E402


def _screenshot(html: str, out: Path, client: TestClient) -> None:
    if "<base " not in html:
        html = html.replace("<head>", '<head><base href="http://repave.test/">', 1)

    def handle_route(route: Route) -> None:
        parsed = urlparse(route.request.url)
        host = (parsed.hostname or "").lower()
        if host and host not in {"repave.test", "127.0.0.1", "localhost"}:
            route.continue_()
            return
        response = client.get(parsed.path or "/")
        headers = {}
        content_type = response.headers.get("content-type")
        if content_type:
            headers["content-type"] = content_type
        route.fulfill(status=response.status_code, body=response.content, headers=headers)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.route("**/*", handle_route)
        page.set_content(html, wait_until="networkidle")
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), full_page=True)
        browser.close()


def _capture_catalog(client: TestClient) -> None:
    response = client.get("/")
    if response.status_code != 200:
        raise RuntimeError(f"catalog GET / returned {response.status_code}")
    html = response.text
    if "home-hero__gold" not in html or "Create account" in html:
        raise RuntimeError("catalog HTML missing hero or unexpectedly shows signup")
    out = ROOT / "docs/images/portal/home-catalog.png"
    _screenshot(html, out, client)
    print(f"wrote {out}")


def _capture_landing() -> None:
    os.environ["REPAVE_SERVICE_MODE"] = "1"
    os.environ.setdefault("REPAVE_SESSION_SECRET", "screenshot-session-secret")
    db_path = Path(tempfile.gettempdir()) / "repave-capture-landing.sqlite"
    os.environ.setdefault("REPAVE_DATABASE_URL", f"sqlite:///{db_path}")
    os.environ.setdefault("REPAVE_OIDC_ISSUER", "https://idp.example.com/")
    os.environ.setdefault("REPAVE_OIDC_CLIENT_ID", "screenshot")
    os.environ.setdefault("REPAVE_OIDC_CLIENT_SECRET", "screenshot")
    os.environ.setdefault("REPAVE_OIDC_REDIRECT_URI", "https://repave.example.com/auth/callback")
    output = load_output_config(repo_root=ROOT)
    client = TestClient(create_app(repo_root=ROOT, output_config=output))
    response = client.get("/")
    if response.status_code != 200:
        raise RuntimeError(f"landing GET / returned {response.status_code}")
    html = response.text
    if "Create account" not in html or "home-hero__gold" not in html:
        raise RuntimeError("landing HTML missing expected brand/account copy")
    out = ROOT / "docs/images/portal/landing.png"
    _screenshot(html, out, client)
    print(f"wrote {out}")


def main() -> int:
    # Avoid REPAVE_ENV=local so the host-toolchain banner stays out of README shots.
    os.environ.pop("REPAVE_ENV", None)
    os.environ.setdefault("REPAVE_GITHUB_ORG", "opsdevcode")
    modules_root = Path(
        os.environ.setdefault("REPAVE_MODULES_ROOT", str(Path.home() / "repave-modules"))
    )
    modules_root.mkdir(parents=True, exist_ok=True)
    output = load_output_config(repo_root=ROOT)
    _capture_catalog(TestClient(create_app(repo_root=ROOT, output_config=output)))
    _capture_landing()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
