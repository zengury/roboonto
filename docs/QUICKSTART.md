# Quickstart

Get from zero to an agent-queryable robot ontology in five minutes.

## Install

```sh
git clone https://github.com/zengury/roboonto
cd roboonto
pip install -e .
pip install pyyaml            # only runtime dependency
pytest tests/ -q              # 107 passed
```

## 1 · Validate a shipped pack

Two real robots ship with the repo, both graded `customer-ready`:

```sh
roboonto validate robots/unitree_g1_edu
roboonto readiness robots/unitree_g1_edu --profile customer_v1
#   Grade:     customer-ready
#   Score:     100.0 / 100
```

## 2 · Query it

```python
from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query

q = Query(OntologyLoader("robots/unitree_g1_edu").load())

# What can this robot do?  (capability layer)
for cap in q.list_capabilities():
    print(cap["id"], "—", cap["properties"]["description"])

# Everything an agent needs for navigation, in one call:
menu = q.agent_affordance_menu(capability_kind="navigation")
# → capability + provider + actions (with preconditions & safety class)
#   + interfaces + boundaries, pre-grouped

# Which actions are dangerous?
for a in q.actions_by_safety_class("MOTION"):
    print(a["type_id"], a.get("preconditions"))
```

## 3 · Validate an action before executing it

The pack knows which calls are legal *right now*. Inject the runtime state
and get a verdict with reasons — before anything touches hardware:

```python
from roboonto.api.action_validator import ActionValidator

v = ActionValidator(q.o)
report = v.check("set_velocity",
                 params={"velocity": [0.5, 0.0, 0.0], "duration": 2.0},
                 state={"fsm_mode": "PASSIVE"})
print(report.ok)          # False
print(report.failures)    # fsm_mode == WALKRUN — robot must be walking first
```

## 4 · Serve it to AI agents (MCP)

```jsonc
// ~/.claude/mcp.json
{
  "mcpServers": {
    "roboonto": { "command": "roboonto", "args": ["serve", "--mcp"] }
  }
}
```

Any MCP client (Claude Code, Cursor, …) now gets `list_actions`,
`check_action`, `agent_affordances`, `explain_service_fit`, `readiness`, and
friends — zero-hallucination robot facts, every answer traceable to a
`source` locator. See [MCP.md](MCP.md).

## 5 · Build a pack for your own robot

```sh
cp -r robots/_template robots/my_robot

# Import what can be imported
roboonto import urdf my_robot.urdf -o robots/my_robot
roboonto import sdk-code path/to/sdk -o robots/my_robot

# Draft the capability layer, then hand-review it
roboonto infer-capabilities robots/my_robot --yaml > robots/my_robot/capabilities.yaml

# Work under an audit log (every step recorded to .build/log.jsonl)
roboonto build init robots/my_robot --operator you
roboonto build run robots/my_robot validate -- roboonto validate robots/my_robot

# Grade it
roboonto readiness robots/my_robot --profile customer_v1
```

The readiness report tells you exactly what is missing and how to fix each
gap (`hint` per rule). Aim for `customer-ready` before you let an agent
drive the robot — see [ARL.md](ARL.md) for what each level means.

## Read next

- [SPEC.md](SPEC.md) — the specification (types, actions, grounding, capability layer)
- [ARL.md](ARL.md) — Agent-Readiness Levels
- [CAPABILITY_LAYER.md](CAPABILITY_LAYER.md) — why capabilities, not just APIs
- [ONTOLOGY_QUALITY_METHODOLOGY.md](ONTOLOGY_QUALITY_METHODOLOGY.md) — how packs are built (中文)
