"""GraphData — formal schema for 3D visualization data contract.

Single definition used by generator and consumed by HTML template.
Validation here prevents template/data mismatch bugs.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphNode:
    id: str
    type: str
    category: str
    label: str
    color: str
    source_doc: str = ""
    degree: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "type": self.type, "category": self.category,
            "label": self.label, "color": self.color,
            "source_doc": self.source_doc, "degree": self.degree,
            "properties": self.properties
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
    category_colors: dict[str, str] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> list[str]:
        """Run schema validation. Returns list of issues (empty = valid)."""
        issues = []
        node_ids = {n.id for n in self.nodes}
        # Check required top-level keys
        if not self.robot_id:
            issues.append("robot_id is empty")
        if not self.category_colors:
            issues.append("category_colors is empty")
        # Check stats structure
        if "categories" not in self.stats:
            issues.append("stats missing 'categories' key")
        if "total_nodes" not in self.stats:
            issues.append("stats missing 'total_nodes'")
        # Check node fields
        for n in self.nodes:
            if not n.category:
                issues.append(f"node {n.id}: empty category")
            if n.category not in self.category_colors:
                issues.append(f"node {n.id}: category '{n.category}' not in category_colors")
        # Check link endpoints (allow wildcard refs like agibot_x2.hw.left_leg.*)
        for l in self.links:
            for endpoint in [l.source, l.target]:
                if "*" in endpoint:
                    continue
                if endpoint not in node_ids:
                    issues.append(f"WARNING: link {l.type}: endpoint '{endpoint}' not found (will render as dangling)")
        return issues

    def to_json(self) -> str:
        import json
        return json.dumps({
            "robot": {"id": self.robot_id, "meta": self.robot_meta},
            "stats": self.stats,
            "category_colors": self.category_colors,
            "nodes": [n.to_dict() for n in self.nodes],
            "links": [l.to_dict() for l in self.links],
        }, ensure_ascii=False)

    @staticmethod
    def build(ontology_dir: str) -> "GraphData":
        """Build GraphData from an ontology directory."""
        from roboonto.api.loader import OntologyLoader
        from roboonto.core.type_registry import TYPE_CATEGORY, CATEGORY_COLORS

        loader = OntologyLoader(ontology_dir)
        ontology = loader.load()
        robot = ontology.robot_meta

        nodes = []
        for obj in ontology.objects_by_id.values():
            otype = obj.get("type", "")
            cat, color = TYPE_CATEGORY.get(otype, ("hardware", "#888"))
            props = obj.get("properties", {})
            label = str(props.get("name") or props.get("urdf_name") or obj["id"].split(".")[-1])[:50]
            src = obj.get("source", {})
            source_doc = f'{src.get("type","")}: {src.get("locator","")}' if src.get("locator") else src.get("type","")
            nodes.append(GraphNode(
                id=obj["id"], type=otype, category=cat, label=label,
                color=color, source_doc=source_doc,
                properties={k: v for k, v in props.items() if isinstance(v, (str, int, float, bool))}
            ))

        for a in ontology.actions_by_id.values():
            aid = a["type_id"]
            src = a.get("source", {})
            nodes.append(GraphNode(
                id=aid, type="Action", category="action", label=aid,
                color=CATEGORY_COLORS["action"],
                source_doc=f'{src.get("type","")}: {src.get("locator","")}' if src.get("locator") else "",
                properties={"safety_class": a.get("safety_class", "")}
            ))

        links = []
        for link in ontology.links:
            s, t, lt = link.get("source", ""), link.get("target", ""), link.get("type", "")
            if s and t:
                links.append(GraphLink(source=s, target=t, type=lt))
        for a in ontology.actions_by_id.values():
            for aff in a.get("affects", []):
                links.append(GraphLink(source=a["type_id"], target=aff, type="affects"))

        # Compute degrees
        degree = {}
        for l in links:
            degree[l.source] = degree.get(l.source, 0) + 1
            degree[l.target] = degree.get(l.target, 0) + 1
        for n in nodes:
            n.degree = degree.get(n.id, 0)

        # Stats
        cat_counts, type_counts = {}, {}
        for n in nodes:
            cat_counts[n.category] = cat_counts.get(n.category, 0) + 1
            type_counts[n.type] = type_counts.get(n.type, 0) + 1

        stats = {
            "total_nodes": len(nodes), "total_links": len(links),
            "categories": cat_counts, "object_types": type_counts
        }

        return GraphData(
            robot_id=robot.get("id", ""), robot_meta=robot,
            nodes=nodes, links=links,
            category_colors=CATEGORY_COLORS, stats=stats
        )
