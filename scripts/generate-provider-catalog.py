#!/usr/bin/env python3
"""Generate provider-catalog.json from HashiCorp Terraform provider source trees.

Service names match the provider's internal service packages (for example
hashicorp/terraform-provider-aws/internal/service/<name>).
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

PROVIDER_PATHS = {
    "aws": ("hashicorp/terraform-provider-aws", "internal/service"),
    "azure": ("hashicorp/terraform-provider-azurerm", "internal/services"),
    "gcp": ("hashicorp/terraform-provider-google", "google/services"),
}

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "terraform-module-generic"
    / "provider-catalog.json"
)


def fetch_service_dirs(repo: str, path: str) -> list[str]:
    items: list[dict[str, object]] = []
    url = f"https://api.github.com/repos/{repo}/contents/{path}?per_page=100"
    while url:
        request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.load(response)
        if not isinstance(payload, list):
            raise RuntimeError(f"Unexpected GitHub response for {repo}/{path}: {payload!r}")
        items.extend(payload)
        url = None
        link = response.headers.get("Link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip("<> ")
    return sorted(item["name"] for item in items if item.get("type") == "dir")


def build_catalog() -> dict[str, list[str]]:
    catalog: dict[str, list[str]] = {}
    for provider, (repo, path) in PROVIDER_PATHS.items():
        catalog[provider] = fetch_service_dirs(repo, path)
    return catalog


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    try:
        catalog = build_catalog()
    except urllib.error.URLError as exc:
        print(f"Failed to fetch provider service lists: {exc}", file=sys.stderr)
        return 1

    output.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    for provider, services in catalog.items():
        print(f"{provider}: {len(services)} services")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
