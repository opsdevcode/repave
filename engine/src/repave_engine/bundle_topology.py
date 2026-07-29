"""Bundle member topology for portal graphs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repave_engine.bundle import Bundle
from repave_engine.bundle_portal import BundleMemberPreview


@dataclass(frozen=True)
class TopologyNode:
    node_id: str
    label: str
    subtitle: str
    role: str

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.node_id,
            "label": self.label,
            "subtitle": self.subtitle,
            "role": self.role,
        }


@dataclass(frozen=True)
class TopologyEdge:
    source: str
    target: str
    label: str

    def to_public_dict(self) -> dict[str, str]:
        return {"source": self.source, "target": self.target, "label": self.label}


def build_bundle_topology(
    bundle: Bundle,
    previews: tuple[BundleMemberPreview, ...],
) -> tuple[tuple[TopologyNode, ...], tuple[TopologyEdge, ...]]:
    preview_by_id = {item.member_id: item for item in previews}
    nodes: list[TopologyNode] = []
    for member in bundle.members:
        preview = preview_by_id.get(member.member_id)
        label = preview.repo_name if preview else member.member_id
        subtitle = preview.blueprint_name if preview else member.blueprint_name
        nodes.append(
            TopologyNode(
                node_id=member.member_id,
                label=label,
                subtitle=subtitle,
                role=member.member_id,
            )
        )
    edges = _default_edges(bundle.name, [member.member_id for member in bundle.members])
    return tuple(nodes), edges


def _default_edges(bundle_name: str, member_ids: list[str]) -> tuple[TopologyEdge, ...]:
    edges: list[TopologyEdge] = []
    if "app" in member_ids and "helm" in member_ids:
        edges.append(TopologyEdge("app", "helm", "chart packages app"))
    if "helm" in member_ids and "dashboards" in member_ids:
        edges.append(TopologyEdge("helm", "dashboards", "observability"))
    if len(member_ids) > 1:
        edges.insert(0, TopologyEdge(bundle_name, member_ids[0], "bundle"))
    return tuple(edges)


def topology_public(
    nodes: tuple[TopologyNode, ...],
    edges: tuple[TopologyEdge, ...],
) -> dict[str, Any]:
    return {
        "nodes": [node.to_public_dict() for node in nodes],
        "edges": [edge.to_public_dict() for edge in edges],
    }
