"""
roboonto MCP server — expose ontology as tools for AI agents (Claude Code, Cursor, etc.)

协议: JSON-RPC 2.0 over stdio (Model Context Protocol 2024-11-05)

Claude Code 配置 (~/.claude/mcp.json):
{
  "mcpServers": {
    "roboonto": {
      "command": "roboonto",
      "args": ["serve", "--mcp", "--dir", "/path/to/robots"]
    }
  }
}

或使用安装时自带的 robots:
{
  "mcpServers": {
    "roboonto": {
      "command": "roboonto",
      "args": ["serve", "--mcp"]
    }
  }
}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="[roboonto-mcp] %(levelname)s %(message)s")
log = logging.getLogger("roboonto_mcp")

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INTERNAL_ERROR = -32603


def _find_robots_dir() -> Path:
    """Find the robots directory: explicit --dir > env var > package-relative."""
    # Check env var
    env_dir = os.environ.get("ROBOONTO_ROBOTS_DIR")
    if env_dir:
        return Path(env_dir)
    # Check relative to this file (installed package)
    pkg_dir = Path(__file__).resolve().parent.parent / "robots"
    if pkg_dir.exists():
        return pkg_dir
    # Fallback
    return Path("robots")


def _list_robot_dirs(robots_dir: Path) -> list[str]:
    """List available robot ontology dirs."""
    if not robots_dir.exists():
        return []
    return sorted([
        d.name for d in robots_dir.iterdir()
        if d.is_dir() and not d.name.startswith("_") and not d.name.startswith(".")
        and (d / "ontology.yaml").exists()
    ])


# ── Tool implementations ──

def _load_ontology(robot_id: str, robots_dir: Path) -> Any:
    """Load an ontology, return (ontology, loader) or error."""
    from roboonto.api.loader import OntologyLoader
    robot_dir = robots_dir / robot_id
    if not (robot_dir / "ontology.yaml").exists():
        return {"error": f"robot '{robot_id}' not found in {robots_dir}"}
    loader = OntologyLoader(robot_dir)
    ontology = loader.load()
    issues = loader.validate()
    errors = [str(i) for i in issues if i.severity == "error"]
    return {"ontology": ontology, "loader": loader, "errors": errors}


def handle_list_robots(args: dict, robots_dir: Path) -> dict:
    """List available robot ontology packs with basic stats."""
    robot_ids = _list_robot_dirs(robots_dir)
    result = {}
    for rid in robot_ids:
        loaded = _load_ontology(rid, robots_dir)
        if "error" in loaded:
            result[rid] = {"error": loaded["error"]}
            continue
        ont = loaded["ontology"]
        result[rid] = {
            "objects": len(ont.objects_by_id),
            "actions": len(ont.actions_by_id),
            "validation_errors": len(loaded.get("errors", [])),
        }
    return {"robots": result}


def handle_list_actions(args: dict, robots_dir: Path) -> dict:
    """List all agent-callable actions for a robot."""
    robot_id = args.get("robot", "agibot_x2")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    ont = loaded["ontology"]
    actions = []
    for a in ont.actions_by_id.values():
        actions.append({
            "id": a["type_id"],
            "description": a.get("description", ""),
            "safety_class": a.get("safety_class", "UNKNOWN"),
            "idempotent": a.get("idempotent", False),
            "parameters": [
                {"name": p["name"], "type": p.get("type", "any"), "constraints": p.get("constraints", [])}
                for p in a.get("parameters", [])
            ],
        })
    return {"robot": robot_id, "actions": actions}


def handle_get_action(args: dict, robots_dir: Path) -> dict:
    """Get full spec for a specific action."""
    robot_id = args.get("robot", "agibot_x2")
    action_id = args.get("action", "")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    ont = loaded["ontology"]
    a = ont.actions_by_id.get(action_id)
    if not a:
        return {"error": f"action '{action_id}' not found in {robot_id}"}
    from roboonto.api.query import action_for_llm
    return action_for_llm(a)


def handle_check_action(args: dict, robots_dir: Path) -> dict:
    """Validate whether an action can be called with given params/state."""
    robot_id = args.get("robot", "agibot_x2")
    action_id = args.get("action", "")
    params = args.get("params", {})
    state = args.get("state", {})
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    ont = loaded["ontology"]
    from roboonto.api.action_validator import ActionValidator
    v = ActionValidator(ont)
    report = v.check(action_id, params=params, state=state)
    return {
        "ok": report.ok,
        "summary": report.summary(),
        "details": report.to_dict() if hasattr(report, "to_dict") else str(report),
    }


def handle_query_objects(args: dict, robots_dir: Path) -> dict:
    """Query ontology objects by type."""
    robot_id = args.get("robot", "agibot_x2")
    obj_type = args.get("type", "")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    ont = loaded["ontology"]
    from roboonto.api.query import Query
    q = Query(ont)
    if obj_type:
        objects = q.objects_of_type(obj_type)
    else:
        objects = [{"id": oid, "type": o.get("type", ""), "name": o.get("properties", {}).get("name", oid)}
                   for oid, o in ont.objects_by_id.items()]
    return {"robot": robot_id, "type": obj_type or "all", "count": len(objects), "objects": objects}


def handle_list_capabilities(args: dict, robots_dir: Path) -> dict:
    """List robot capabilities, optionally filtered by semantic fields."""
    robot_id = args.get("robot", "agibot_x2")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    from roboonto.api.query import Query
    q = Query(loaded["ontology"])
    caps = q.find_capabilities(
        capability_kind=args.get("capability_kind") or None,
        detects=args.get("detects") or None,
        provider=args.get("provider") or None,
        exposed_via=args.get("exposed_via") or None,
        requirement=args.get("requirement") or None,
    )
    return {"robot": robot_id, "count": len(caps), "capabilities": caps}


def handle_agent_affordances(args: dict, robots_dir: Path) -> dict:
    """Return a capability-first menu for agent planners."""
    robot_id = args.get("robot", "agibot_x2")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    from roboonto.api.query import Query
    q = Query(loaded["ontology"])
    menu = q.agent_affordance_menu(
        capability_kind=args.get("capability_kind") or None,
        include_readonly=bool(args.get("include_readonly", True)),
    )
    return {
        "robot": robot_id,
        "standard_mappings": q.standard_mappings(),
        "count": len(menu),
        "affordances": menu,
    }


def handle_infer_capabilities(args: dict, robots_dir: Path) -> dict:
    """Infer a reviewable capabilities.yaml draft from actions/interfaces."""
    robot_id = args.get("robot", "agibot_x2")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    from roboonto.api.capability_infer import infer_capability_drafts
    return {"robot": robot_id, "draft": infer_capability_drafts(loaded["ontology"])}


def handle_explain_service_fit(args: dict, robots_dir: Path) -> dict:
    """Explain which capabilities satisfy a service requirement."""
    robot_id = args.get("robot", "agibot_x2")
    requirement = args.get("requirement", "")
    if not requirement:
        return {"error": "requirement is required"}
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    from roboonto.api.query import Query
    q = Query(loaded["ontology"])
    return {"robot": robot_id, **q.explain_service_fit(requirement)}


def handle_explain(args: dict, robots_dir: Path) -> dict:
    """Explain a specific ontology entity."""
    robot_id = args.get("robot", "agibot_x2")
    entity_id = args.get("id", "")
    loaded = _load_ontology(robot_id, robots_dir)
    if "error" in loaded:
        return loaded
    ont = loaded["ontology"]
    if entity_id in ont.objects_by_id:
        obj = ont.objects_by_id[entity_id]
        return {
            "id": entity_id,
            "type": obj.get("type", ""),
            "properties": obj.get("properties", {}),
            "description": obj.get("description", ""),
            "source": obj.get("source"),
        }
    if entity_id in ont.actions_by_id:
        a = ont.actions_by_id[entity_id]
        return {
            "id": entity_id,
            "type": "action",
            "description": a.get("description", ""),
            "safety_class": a.get("safety_class"),
            "parameters": a.get("parameters", []),
            "preconditions": a.get("preconditions", []),
            "affects": a.get("affects", []),
        }
    # Try related entities
    from roboonto.api.query import Query
    q = Query(ont)
    related = q.actions_affecting(entity_id)
    if related:
        return {"id": entity_id, "related_actions": related}
    return {"error": f"entity '{entity_id}' not found"}


def handle_readiness(args: dict, robots_dir: Path) -> dict:
    """Grade an ontology against the customer profile."""
    robot_id = args.get("robot", "agibot_x2")
    from roboonto.framework.readiness import Readiness
    profile = args.get("profile", "customer_v1")
    r = Readiness(robots_dir / robot_id, profile=profile)
    report = r.run()
    return report.to_dict()


# ── Tool definitions ──

TOOLS = [
    {
        "name": "roboonto.list_robots",
        "description": "List all available robot ontology packs with stats (object count, action count, validation status).",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "roboonto.list_actions",
        "description": "List all agent-callable actions for a robot. Returns action IDs, descriptions, safety classes, and parameters.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID (e.g. agibot_x2, halfcheetah). Default: agibot_x2"}
            },
            "required": [],
        },
    },
    {
        "name": "roboonto.get_action",
        "description": "Get the full specification for a specific action: parameters with constraints, preconditions, affects, safety class, and invoker details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "action": {"type": "string", "description": "Action ID (e.g. set_forward_velocity)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "roboonto.check_action",
        "description": "Validate whether an action can be called with given parameters and robot state. Returns ok/not-ok with reasons.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "action": {"type": "string", "description": "Action ID"},
                "params": {"type": "object", "description": "Action parameters"},
                "state": {"type": "object", "description": "Robot state (mode, battery, etc.)"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "roboonto.query_objects",
        "description": "Query ontology objects by type (e.g. Joint, Sensor, Mode, Topic, StatusBit). Returns all if no type specified.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "type": {"type": "string", "description": "Object type to filter (Joint, Sensor, Mode, Topic, etc.)"},
            },
            "required": [],
        },
    },
    {
        "name": "roboonto.list_capabilities",
        "description": "List robot capabilities and filter by kind, detected semantic target, provider, exposed interface/action, or service requirement.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "capability_kind": {"type": "string", "description": "Capability kind (perception, actuation, navigation, diagnosis, etc.)"},
                "detects": {"type": "string", "description": "Detected semantic target, e.g. person or obstacle"},
                "provider": {"type": "string", "description": "Provider entity id"},
                "exposed_via": {"type": "string", "description": "Topic/Service/Action id exposing the capability"},
                "requirement": {"type": "string", "description": "ServiceRequirement id"},
            },
            "required": [],
        },
    },
    {
        "name": "roboonto.agent_affordances",
        "description": "Return a capability-first affordance menu for agent planners: what the robot can do, provider, actions, interfaces, parameters, and boundaries.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "capability_kind": {"type": "string", "description": "Optional capability kind filter"},
                "include_readonly": {"type": "boolean", "description": "Include INFO/read-only actions. Default: true"},
            },
            "required": [],
        },
    },
    {
        "name": "roboonto.infer_capabilities",
        "description": "Infer a reviewable capabilities.yaml draft from existing actions and invokes_via interface links.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
            },
            "required": [],
        },
    },
    {
        "name": "roboonto.explain_service_fit",
        "description": "Explain which capabilities satisfy a ServiceRequirement, including providers, parameters, and exposed interfaces/actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "requirement": {"type": "string", "description": "ServiceRequirement id"},
            },
            "required": ["requirement"],
        },
    },
    {
        "name": "roboonto.explain",
        "description": "Explain an ontology entity: hardware, sensor, joint, event, fault code, or action. Returns properties, relations, source.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "id": {"type": "string", "description": "Entity ID (e.g. agibot_x2.hw.left_leg.hip_pitch, agibot_x2.event.pmu.bus48v_overcurrent)"},
            },
            "required": ["id"],
        },
    },
    {
        "name": "roboonto.readiness",
        "description": "Grade an ontology against the customer profile (must/should/may rules). Returns grade (fail/alpha/beta/customer-ready), score, and per-rule results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "robot": {"type": "string", "description": "Robot ID"},
                "profile": {"type": "string", "description": "Profile name (default: customer_v1)"},
            },
            "required": [],
        },
    },
]

TOOL_HANDLERS = {
    "roboonto.list_robots": handle_list_robots,
    "roboonto.list_actions": handle_list_actions,
    "roboonto.get_action": handle_get_action,
    "roboonto.check_action": handle_check_action,
    "roboonto.query_objects": handle_query_objects,
    "roboonto.list_capabilities": handle_list_capabilities,
    "roboonto.agent_affordances": handle_agent_affordances,
    "roboonto.infer_capabilities": handle_infer_capabilities,
    "roboonto.explain_service_fit": handle_explain_service_fit,
    "roboonto.explain": handle_explain,
    "roboonto.readiness": handle_readiness,
}


# ── MCP protocol (stdlib, zero dependencies beyond Python) ──

def _read_message() -> dict | None:
    try:
        line = sys.stdin.readline()
        if not line:
            return None
        return json.loads(line)
    except json.JSONDecodeError as e:
        _write_message({"jsonrpc": "2.0", "id": None,
                        "error": {"code": PARSE_ERROR, "message": f"Parse error: {e}"}})
        return None


def _write_message(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _send_result(msg_id: Any, result: Any) -> None:
    _write_message({"jsonrpc": "2.0", "id": msg_id, "result": result})


def _send_error(msg_id: Any, code: int, message: str) -> None:
    _write_message({"jsonrpc": "2.0", "id": msg_id,
                    "error": {"code": code, "message": message}})


def serve_mcp(robots_dir: Path):
    log.info("roboonto MCP starting (robots: %s)", robots_dir)

    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")

        try:
            if method == "initialize":
                _send_result(msg_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "roboonto", "version": "0.3.0"},
                })
            elif method == "tools/list":
                _send_result(msg_id, {"tools": TOOLS})
            elif method == "tools/call":
                tool_name = msg.get("params", {}).get("name", "")
                tool_args = msg.get("params", {}).get("arguments", {})
                if tool_name in TOOL_HANDLERS:
                    result = TOOL_HANDLERS[tool_name](tool_args, robots_dir)
                    _send_result(msg_id, {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, default=str)}]
                    })
                else:
                    _send_error(msg_id, METHOD_NOT_FOUND, f"Unknown tool: {tool_name}")
            elif method in ("notifications/initialized", "notifications/cancelled"):
                pass
            else:
                _send_error(msg_id, METHOD_NOT_FOUND, f"Method not found: {method}")
        except Exception as e:
            log.exception("Error in %s", method)
            if msg_id is not None:
                _send_error(msg_id, INTERNAL_ERROR, str(e))

    log.info("roboonto MCP stopped")


if __name__ == "__main__":
    robots_dir = _find_robots_dir()
    serve_mcp(robots_dir)
