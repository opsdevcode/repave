"""Render GoldenPathRepo manifests from the fleet registry.

The operator reconciles `GoldenPathRepo` custom resources; the registry knows which
repositories repave governs. Rather than teach the operator to read the registry — which
would couple it to engine storage and require an in-cluster engine service — the engine
emits manifests that `kubectl apply` or a GitOps controller consumes. Output is
deterministic so re-running produces no diff when the registry has not changed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from repave_engine.fleet import FleetEntry, FleetError

API_VERSION = "repave.dev/v1alpha1"
KIND = "GoldenPathRepo"
DEFAULT_NAMESPACE = "default"

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
# Kubernetes object names: RFC 1123 label, 253 chars max. Leave room for a suffix.
_MAX_NAME = 200


class _QuotingDumper(yaml.SafeDumper):
    """Quote strings that would otherwise round-trip as a non-string scalar.

    CRD pin fields are typed `string`, so a two-component version like `1.0` must not be
    emitted bare — YAML would parse it back as a float and strict decoding would reject it.
    """


def _represent_str(dumper: yaml.SafeDumper, data: str) -> yaml.ScalarNode:
    resolved = dumper.resolve(yaml.ScalarNode, data, (True, False))
    style = "'" if resolved != "tag:yaml.org,2002:str" else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_QuotingDumper.add_representer(str, _represent_str)


@dataclass(frozen=True)
class RenderedManifest:
    """One manifest and the path it was written to."""

    entry: FleetEntry
    name: str
    path: Path


def resource_name(repo_url: str) -> str:
    """Derive a stable RFC 1123 name from a repo URL.

    Uses owner-and-repo rather than the repo alone so `acme/vpc` and `other/vpc` do not
    collide in one namespace.
    """
    stripped = re.sub(r"^[a-z]+://", "", repo_url.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"^[^/@]+@", "", stripped)  # scp-style git@host:org/repo
    stripped = stripped.replace(":", "/").rstrip("/")
    # Registry entries are normalized, but manifests may be rendered from raw URLs too.
    if stripped.lower().endswith(".git"):
        stripped = stripped[: -len(".git")]
    parts = [part for part in stripped.split("/") if part]
    tail = parts[-2:] if len(parts) >= 3 else parts[-1:]
    slug = _NON_ALNUM.sub("-", "-".join(tail).lower()).strip("-")
    if not slug:
        raise FleetError(f"cannot derive a resource name from {repo_url!r}")
    return slug[:_MAX_NAME].rstrip("-")


def manifest_for(entry: FleetEntry, *, namespace: str = DEFAULT_NAMESPACE) -> dict[str, object]:
    """Build the GoldenPathRepo body for one registry entry."""
    missing = [
        field
        for field in ("blueprint_name", "blueprint_version", "standard_source", "standard_version")
        if not getattr(entry, field)
    ]
    if missing:
        raise FleetError(
            f"{entry.repo_url} cannot become a GoldenPathRepo: desiredPins requires "
            f"{', '.join(sorted(missing))}. Re-register with --path so pins come from repave.yaml."
        )

    metadata: dict[str, object] = {
        "name": resource_name(entry.repo_url),
        "namespace": namespace,
        "labels": {"repave.dev/managed-by": "repave-fleet"},
    }
    if entry.owner:
        metadata["annotations"] = {"repave.dev/owner": entry.owner}

    return {
        "apiVersion": API_VERSION,
        "kind": KIND,
        "metadata": metadata,
        "spec": {
            "repoURL": entry.repo_url,
            "desiredPins": {
                "blueprintName": entry.blueprint_name,
                "blueprintVersion": entry.blueprint_version,
                "standardSource": entry.standard_source,
                "standardVersion": entry.standard_version,
            },
        },
    }


def render_manifests(
    entries: tuple[FleetEntry, ...] | list[FleetEntry],
    output_dir: Path,
    *,
    namespace: str = DEFAULT_NAMESPACE,
) -> tuple[RenderedManifest, ...]:
    """Write one manifest per entry into output_dir, one file per repository."""
    names: dict[str, str] = {}
    bodies: list[tuple[FleetEntry, str, dict[str, object]]] = []
    for entry in entries:
        body = manifest_for(entry, namespace=namespace)
        metadata = body["metadata"]
        assert isinstance(metadata, dict)
        name = str(metadata["name"])
        if name in names and names[name] != entry.repo_url:
            raise FleetError(
                f"{entry.repo_url} and {names[name]} both map to resource name {name!r}; "
                "rename one repository or split them across namespaces"
            )
        names[name] = entry.repo_url
        bodies.append((entry, name, body))

    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: list[RenderedManifest] = []
    for entry, name, body in bodies:
        path = output_dir / f"{name}.yaml"
        text = yaml.dump(body, Dumper=_QuotingDumper, sort_keys=False, default_flow_style=False)
        path.write_text(text, encoding="utf-8")
        rendered.append(RenderedManifest(entry=entry, name=name, path=path))
    return tuple(rendered)
