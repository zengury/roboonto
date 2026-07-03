"""GraphData — schema for the 3D ontology-atlas visualization data contract.

Emits the GRAPH_DATA object consumed by the layered 3D atlas template
(roboonto/tools/templates/ontology_atlas_3d.html):

    {
      "robot":  {"id": ..., "meta": {...}},
      "nodes":  [{"id","type","layer","label","props","degree"}, ...],
      "links":  [{"source","target","type"}, ...],
      "stats":  {"total_nodes","total_links","by_type": {...}}
    }

Nodes are grouped into 9 visual layers (see TYPE_LAYER). `props` carries the
object's scalar properties, list properties collapsed to `<key>_count` /
`<key>_sample`, and a `source` provenance string.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

# Object type -> atlas layer. Mirrors the 9-layer stack in the template.
TYPE_LAYER: dict[str, str] = {
    # compute
    "ComputeUnit": "compute",
    "SoftwareComponent": "compute",
    "Process": "compute",
    "ROSNode": "compute",
    # hardware (physical, non-link)
    "PowerSubsystem": "hardware",
    "Sensor": "hardware",
    "RobotBody": "hardware",
    "ProtectionThreshold": "hardware",
    "EndEffector": "hardware",
    "Joint": "hardware",
    "VirtualEndpoint": "hardware",
    # kinematics
    "Link": "kinematics",
    "CoordinateFrame": "kinematics",
    # events
    "StatusBit": "events",
    "FaultCode": "events",
    "TouchEvent": "events",
    # behaviors
    "Mode": "behaviors",
    "PresetMotion": "behaviors",
    "ControlLoop": "behaviors",
    "InputSource": "behaviors",
    "PriorityLevel": "behaviors",
    # interfaces
    "Topic": "interfaces",
    "Service": "interfaces",
    "MsgSchema": "interfaces",
    "SrvSchema": "interfaces",
    # actions
    "Action": "actions",
    # capabilities
    "Capability": "capabilities",
    "CapabilityParameter": "capabilities",
    # requirements
    "ServiceRequirement": "requirements",
}

_SAMPLE_TRUNC = 72
_LABEL_TRUNC = 50


def layer_for(otype: str) -> str:
    return TYPE_LAYER.get(otype, "hardware")


def _build_props(properties: dict[str, Any], source_str: str) -> dict[str, Any]:
    """Scalars kept; lists collapsed to _count/_sample; source appended."""
    out: dict[str, Any] = {}
    for k, v in properties.items():
        if isinstance(v, bool) or isinstance(v, (str, int, float)):
            out[k] = v
        elif isinstance(v, list):
            out[f"{k}_count"] = len(v)
            if v and isinstance(v[0], (str, int, float)) and not isinstance(v[0], bool):
                out[f"{k}_sample"] = str(v[0])[:_SAMPLE_TRUNC]
        # dicts / nested structures are omitted from the flat prop view
    if source_str:
        out["source"] = source_str
    return out


@dataclass
class GraphNode:
    id: str
    type: str
    layer: str
    label: str
    props: dict[str, Any] = field(default_factory=dict)
    degree: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "layer": self.layer,
            "label": self.label, "props": self.props, "degree": self.degree,
        }


@dataclass
class GraphLink:
    source: str
    target: str
    type: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "type": self.type}


@dataclass
class GraphData:
    robot_id: str
    robot_meta: dict[str, Any]
    nodes: list[GraphNode]
    links: list[GraphLink]
    stats: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Schema checks. Returns list of issues (empty = valid)."""
        issues = []
        node_ids = {n.id for n in self.nodes}
        if not self.robot_id:
            issues.append("robot_id is empty")
        for n in self.nodes:
            if not n.layer:
                issues.append(f"node {n.id}: empty layer")
        # Link endpoints (allow wildcard refs like robot.hw.left_leg.*)
        for l in self.links:
            for endpoint in (l.source, l.target):
                if "*" in endpoint:
                    continue
                if endpoint not in node_ids:
                    issues.append(
                        f"WARNING: link {l.type}: endpoint '{endpoint}' not found (will render as dangling)")
        return issues

    def to_json(self) -> str:
        import json
        return json.dumps({
            "robot": {"id": self.robot_id, "meta": self.robot_meta},
            "nodes": [n.to_dict() for n in self.nodes],
            "links": [l.to_dict() for l in self.links],
            "stats": self.stats,
        }, ensure_ascii=False)

    @staticmethod
    def build(ontology_dir: str) -> "GraphData":
        """Build GraphData from an ontology directory."""
        from roboonto.api.loader import OntologyLoader

        loader = OntologyLoader(ontology_dir)
        ontology = loader.load()
        robot = ontology.robot_meta

        nodes: list[GraphNode] = []

        for obj in ontology.objects_by_id.values():
            otype = obj.get("type", "")
            props = obj.get("properties", {})
            label = str(
                props.get("name_human") or props.get("name")
                or props.get("urdf_name") or props.get("name_urdf")
                or obj["id"].split(".")[-1]
            )[:_LABEL_TRUNC]
            src = obj.get("source", {})
            source_str = src.get("locator") or src.get("type", "")
            nodes.append(GraphNode(
                id=obj["id"], type=otype, layer=layer_for(otype), label=label,
                props=_build_props(props, source_str),
            ))

        for a in ontology.actions_by_id.values():
            aid = a["type_id"]
            src = a.get("source", {})
            source_str = src.get("locator") or src.get("type", "")
            aprops: dict[str, Any] = {"safety_class": a.get("safety_class", "")}
            inv = a.get("invoker", {})
            if isinstance(inv, dict) and inv.get("type"):
                aprops["invoker"] = inv["type"]
            if source_str:
                aprops["source"] = source_str
            nodes.append(GraphNode(
                id=aid, type="Action", layer="actions", label=aid[:_LABEL_TRUNC],
                props=aprops,
            ))

        links: list[GraphLink] = []
        for link in ontology.links:
            s, t, lt = link.get("source", ""), link.get("target", ""), link.get("type", "")
            if s and t:
                links.append(GraphLink(source=s, target=t, type=lt))
        for a in ontology.actions_by_id.values():
            for aff in a.get("affects", []):
                links.append(GraphLink(source=a["type_id"], target=aff, type="affects"))

        # Degrees
        degree: dict[str, int] = {}
        for l in links:
            degree[l.source] = degree.get(l.source, 0) + 1
            degree[l.target] = degree.get(l.target, 0) + 1
        for n in nodes:
            n.degree = degree.get(n.id, 0)

        by_type: dict[str, int] = {}
        for n in nodes:
            by_type[n.type] = by_type.get(n.type, 0) + 1
        stats = {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "by_type": dict(sorted(by_type.items())),
        }

        return GraphData(
            robot_id=robot.get("id", ""), robot_meta=robot,
            nodes=nodes, links=links, stats=stats,
        )
