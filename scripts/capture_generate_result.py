#!/usr/bin/env python3
"""Capture generate result PNGs for docs/images/portal/."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("REPAVE_PORTAL_URL", "http://127.0.0.1:8088").rstrip("/")

ENGINE_SRC = ROOT / "engine" / "src"
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from playwright.sync_api import sync_playwright  # noqa: E402
from repave_engine.api import create_app  # noqa: E402
from repave_engine.settings import load_output_config  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402


def _capture(html: str, out: Path) -> None:
    if "lineage-heading" not in html and "Lineage" not in html:
        raise RuntimeError("Generate response missing lineage block")
    if "<base " not in html:
        html = html.replace("<head>", f'<head><base href="{BASE}/">', 1)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.set_content(html, wait_until="networkidle")
        out.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out), full_page=True)
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture portal generate result PNGs")
    parser.add_argument(
        "--variant",
        choices=("default", "backstage", "all"),
        default="all",
        help="Which screenshot to capture (default: all)",
    )
    args = parser.parse_args()

    output = load_output_config(repo_root=ROOT)
    client = TestClient(create_app(repo_root=ROOT, output_config=output))

    variants: list[tuple[str, Path, dict[str, str]]] = []
    if args.variant in ("default", "all"):
        variants.append(
            (
                "default",
                ROOT / "docs/images/portal/generate-result.png",
                {
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
        )
    if args.variant in ("backstage", "all"):
        variants.append(
            (
                "backstage",
                ROOT / "docs/images/portal/generate-result-backstage.png",
                {
                    "blueprint_name": "terraform-module-generic",
                    "dry_run": "true",
                    "module_name": "readme-demo",
                    "description": "README screenshot module",
                    "cloud_provider": "aws",
                    "provider_services": "ec2,s3",
                    "policy_pack_source": "repave-default",
                    "policy_profile": "estate-default",
                    "include_backstage_catalog": "true",
                    "owner": "group:platform",
                    "catalog_lifecycle": "experimental",
                },
            )
        )

    for _name, out_path, form in variants:
        response = client.post("/generate", data=form)
        if response.status_code != 200:
            print(response.text[:2000], file=sys.stderr)
            return 1
        _capture(response.text, out_path)
        print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
