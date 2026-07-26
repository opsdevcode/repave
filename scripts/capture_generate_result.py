#!/usr/bin/env python3
"""Capture docs/images/portal/generate-result.png (portal must be on :8088)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/images/portal/generate-result.png"
BASE = os.environ.get("REPAVE_PORTAL_URL", "http://127.0.0.1:8088").rstrip("/")

# Run from repo with engine on PYTHONPATH via `cd engine && uv run ...`
ENGINE_SRC = ROOT / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from playwright.sync_api import sync_playwright  # noqa: E402
from repave_engine.api import create_app  # noqa: E402
from repave_engine.settings import load_output_config  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


def main() -> int:
    output = load_output_config(repo_root=ROOT)
    client = TestClient(create_app(repo_root=ROOT, output_config=output))
    response = client.post(
        "/generate",
        data={
            "blueprint_name": "terraform-module-generic",
            "dry_run": "true",
            "module_name": "readme-demo",
            "description": "README screenshot module",
            "cloud_provider": "aws",
            "provider_services": "ec2,s3",
            "policy_pack_source": "repave-default",
            "policy_profile": "estate-default",
            "include_backstage_catalog": "false",
        },
    )
    if response.status_code != 200:
        print(response.text[:2000], file=sys.stderr)
        return 1
    html = response.text
    if "lineage-heading" not in html and "Lineage" not in html:
        print("Generate response missing lineage block", file=sys.stderr)
        return 1
    if "<base " not in html:
        html = html.replace("<head>", f'<head><base href="{BASE}/">', 1)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(html, wait_until="networkidle")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT), full_page=True)
        browser.close()
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
