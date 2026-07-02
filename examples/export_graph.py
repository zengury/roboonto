#!/usr/bin/env python3
"""Export ontology as a graph JSON for 3D visualization."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from roboonto.api.loader import OntologyLoader


# Category → color (手选的高饱和配色,深色背景下好看)
CATEGORY_COLOR = {
    "hardware":  "#ff6b6b",   # 红
    "software":  "#a78bfa",   # 紫
    "interface": "#4dd0e1",   # 青
    "behavior":  "#ffd54f",   # 黄
    "event":     "#ff9800",   # 橙
    "frame":     "#81c784",   # 绿
    "meta":      "#90a4ae",   # 灰蓝
    "action":    "#ec407a",   # 粉红
}

TYPE_TO_CATEGORY = {
    # hardware
    "ComputeUnit": "hardware", "Joint": "hardware", "Link": "hardware",
    "Sensor": "hardware", "PowerSubsystem": "hardware", "RobotBody": "hardware",
    "EndEffector": "hardware",
    # software
    "ROSNode": "software", "Process": "software", "App": "software", "OTAPackage": "software",
    # interface
    "Topic": "interface", "Service": "interface",
    "MsgSchema": "interface", "SrvSchema": "interface",
    # behavior
    "Mode": "behavior", "PresetMotion": "behavior", "ControlLoop": "behavior",
    # event
    "StatusBit": "event", "FaultCode": "event", "TouchEvent": "event",
    # frame
    "CoordinateFrame": "frame",
    # meta
    "InputSource": "meta", "PriorityLevel": "meta", "SafetyClass": "meta",
}


def main():
    loader = OntologyLoader(Path("robots/agibot_x2"))
    ontology = loader.load()

    nodes = []
    # Objects
    for obj in ontology.objects_by_id.values():
        t = obj.get("type", "Unknown")
        cat = TYPE_TO_CATEGORY.get(t, "meta")
        p = obj.get("properties") or {}
        label = p.get("name_human") or p.get("name") or p.get("display_name") or obj["id"].split(".")[-1]
        nodes.append({
            "id": obj["id"],
            "label": label,
            "type": t,
            "category": cat,
            "color": CATEGORY_COLOR[cat],
            "properties": p,
            "source_doc": (obj.get("source") or {}).get("locator", ""),
        })

    # Actions (作为特殊节点)
    for aid, act in ontology.actions_by_id.items():
        nodes.append({
            "id": aid,
            "label": aid,
            "type": "Action",
            "category": "action",
            "color": CATEGORY_COLOR["action"],
            "properties": {
                "description": act.get("description", ""),
                "safety_class": act.get("safety_class"),
                "invoker_type": (act.get("invoker") or {}).get("type"),
                "invoker_name": (act.get("invoker") or {}).get("name"),
                "preconditions_count": len(act.get("preconditions") or []),
                "parameters": [p["name"] for p in act.get("parameters") or []],
            },
            "source_doc": (act.get("source") or {}).get("locator", ""),
        })

    # Links
    links = []
    known_ids = {n["id"] for n in nodes}
    for link in ontology.links:
        src, tgt = link.get("source"), link.get("target")
        # 跳过 wildcard 和 dangling refs(visualization 容不下 * )
        if src not in known_ids or tgt not in known_ids:
            continue
        links.append({
            "source": src,
            "target": tgt,
            "type": link.get("type", ""),
        })

    # 给每个节点算 degree
    degree = {n["id"]: 0 for n in nodes}
    for l in links:
        degree[l["source"]] = degree.get(l["source"], 0) + 1
        degree[l["target"]] = degree.get(l["target"], 0) + 1
    for n in nodes:
        n["degree"] = degree.get(n["id"], 0)

    # 类别计数,用于 legend
    cat_counts = {}
    for n in nodes:
        cat_counts[n["category"]] = cat_counts.get(n["category"], 0) + 1

    graph = {
        "robot": {
            "id": ontology.robot_id,
            "meta": ontology.robot_meta,
        },
        "stats": {
            "total_nodes": len(nodes),
            "total_links": len(links),
            "categories": cat_counts,
            "object_types": {t: len(v) for t, v in ontology.objects_by_type.items()},
        },
        "category_colors": CATEGORY_COLOR,
        "nodes": nodes,
        "links": links,
    }

    out = Path("examples/graph.json")
    out.write_text(json.dumps(graph, ensure_ascii=False, indent=2))
    print(f"Exported {len(nodes)} nodes + {len(links)} links → {out}")
    print(f"Category breakdown: {cat_counts}")


if __name__ == "__main__":
    main()
