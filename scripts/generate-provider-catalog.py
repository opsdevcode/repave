#!/usr/bin/env python3
"""Generate provider-catalog.json from HashiCorp Terraform provider source trees.

Each provider service includes Terraform resource options plus a basic capability
subset for users who do not want to pick individual resources.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

PROVIDER_PATHS = {
    "aws": ("hashicorp/terraform-provider-aws", "internal/service"),
    "azure": ("hashicorp/terraform-provider-azurerm", "internal/services"),
    "gcp": ("hashicorp/terraform-provider-google", "google/services"),
}

BASIC_RESOURCE_PRIORITY = (
    "bucket",
    "bucket_policy",
    "object",
    "cluster",
    "node_group",
    "addon",
    "function",
    "alias",
    "instance",
    "volume",
    "vpc",
    "subnet",
    "account",
    "container",
    "table",
    "topic",
    "queue",
    "role",
    "policy",
    "network",
    "load_balancer",
    "database",
    "secret",
    "key",
)

DEFAULT_OUTPUT = (
    Path(__file__).resolve().parents[1]
    / "blueprints"
    / "terraform-module-generic"
    / "provider-catalog.json"
)


def github_request(url: str) -> dict[str, object]:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=120) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected GitHub response for {url}: {payload!r}")
    return payload


def fetch_repo_tree(repo: str) -> list[str]:
    payload = github_request(f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1")
    tree = payload.get("tree", [])
    if not isinstance(tree, list):
        raise RuntimeError(f"Unexpected tree payload for {repo}")
    return [str(item.get("path", "")) for item in tree if item.get("type") == "blob"]


def aws_resources(paths: list[str], service_root: str) -> list[str]:
    skip_names = {
        "consts",
        "exports",
        "service_package_gen",
        "generate",
        "framework",
        "wait",
        "tags",
        "enum",
        "flex",
        "sweep",
        "validators",
        "identity",
    }
    prefix = f"{service_root}/"
    resources: set[str] = set()
    for path in paths:
        if not path.startswith(prefix) or not path.endswith(".go") or "_test" in path:
            continue
        base = Path(path).stem
        if base in skip_names:
            continue
        if any(token in base for token in ("_data_source", "_list", "arn")):
            continue
        resources.add(base)
    return sorted(resources)


def azure_resources(paths: list[str], service_root: str) -> list[str]:
    prefix = f"{service_root}/"
    resources: set[str] = set()
    for path in paths:
        if path.startswith(prefix) and path.endswith("_resource.go"):
            resources.add(Path(path).name[: -len("_resource.go")])
    return sorted(resources)


def gcp_resources(paths: list[str], service_root: str, service: str) -> list[str]:
    prefix = f"{service_root}/resource_{service}_"
    resources: set[str] = set()
    for path in paths:
        if not path.startswith(prefix) or not path.endswith(".go"):
            continue
        if "_test" in path or "_sweeper" in path:
            continue
        resources.add(Path(path).stem[len(f"resource_{service}_") :])
    return sorted(resources)


def pick_basic_resources(resources: list[str], *, limit: int = 5) -> list[str]:
    basic: list[str] = []
    resource_set = set(resources)
    for candidate in BASIC_RESOURCE_PRIORITY:
        if candidate in resource_set and candidate not in basic:
            basic.append(candidate)
        if len(basic) >= limit:
            return basic

    short_names = sorted(
        (resource for resource in resources if resource.count("_") <= 2),
        key=lambda item: (item.count("_"), len(item), item),
    )
    for candidate in short_names:
        if candidate not in basic:
            basic.append(candidate)
        if len(basic) >= limit:
            break

    if not basic:
        basic = resources[: min(limit, len(resources))]
    return basic


def build_catalog() -> dict[str, dict[str, dict[str, list[str]]]]:
    catalog: dict[str, dict[str, dict[str, list[str]]]] = {}
    for provider, (repo, service_root) in PROVIDER_PATHS.items():
        paths = fetch_repo_tree(repo)
        service_paths = defaultdict(list)
        root_prefix = f"{service_root}/"
        for path in paths:
            if not path.startswith(root_prefix):
                continue
            remainder = path[len(root_prefix) :]
            service = remainder.split("/", 1)[0]
            if service:
                service_paths[service].append(path)

        provider_catalog: dict[str, dict[str, list[str]]] = {}
        for service in sorted(service_paths):
            service_list = service_paths[service]
            if provider == "aws":
                resources = aws_resources(service_list, f"{service_root}/{service}")
            elif provider == "azure":
                resources = azure_resources(service_list, f"{service_root}/{service}")
            else:
                resources = gcp_resources(service_list, f"{service_root}/{service}", service)
            provider_catalog[service] = {
                "resources": resources,
                "basic": pick_basic_resources(resources),
            }
        catalog[provider] = provider_catalog
        print(f"{provider}: {len(provider_catalog)} services")
    return catalog


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    try:
        catalog = build_catalog()
    except urllib.error.URLError as exc:
        print(f"Failed to fetch provider service lists: {exc}", file=sys.stderr)
        return 1

    output.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
