# RoboOnto MCP — AI Agent Integration

Run RoboOnto as an [MCP](https://modelcontextprotocol.io) (Model Context
Protocol) server and any MCP-capable agent — Claude Code, Cursor, Continue,
your own SDK agent — gets zero-hallucination access to robot facts: hardware,
actions, constraints, capabilities. Every answer is backed by the ontology
and traceable to a `source` locator.

> 中文版见 [zh/MCP.md](zh/MCP.md)

## Setup

```sh
pip install -e .          # from a repo checkout
```

```jsonc
// ~/.claude/mcp.json  (Claude Code — other clients are analogous)
{
  "mcpServers": {
    "roboonto": {
      "command": "roboonto",
      "args": ["serve", "--mcp"]                    // bundled robots/
      // "args": ["serve", "--mcp", "--dir", "/path/to/robots"]
    }
  }
}
```

The server speaks JSON-RPC 2.0 over stdio (MCP 2024-11-05). Robot directory
resolution: `--dir` > `ROBOONTO_ROBOTS_DIR` env > packaged `robots/`.

## Tools

| Tool | What it answers |
|---|---|
| `roboonto.list_robots` | Which robots are available? (with object/action counts, validation status) |
| `roboonto.query_objects` | What objects of type X exist? (Joint, Sensor, Mode, Topic, StatusBit, …) |
| `roboonto.explain` | What is this entity? (properties, relations, provenance) |
| `roboonto.list_actions` | What can an agent call? (ids, safety classes, parameters) |
| `roboonto.get_action` | Full spec of one action: constraints, preconditions, affects, invoker |
| `roboonto.check_action` | **Would this call be legal right now?** Verdict + reasons, before hardware |
| `roboonto.list_capabilities` | What can the robot *do*? Filter by kind / detects / provider / requirement |
| `roboonto.agent_affordances` | Capability-first planning menu: ability → provider → actions → interfaces → boundaries, pre-grouped |
| `roboonto.explain_service_fit` | Which capabilities satisfy this service requirement, and how? |
| `roboonto.infer_capabilities` | Draft a `capabilities.yaml` from existing actions (review required) |
| `roboonto.readiness` | Grade a pack against the release checklist (fail/alpha/beta/customer-ready) |

## The intended agent loop

```
1. agent_affordances("navigation")      → what can I use for this task?
2. get_action("set_velocity")           → how exactly do I call it?
3. check_action(params, state)          → is it legal right now?  ← the gate
4. (execute through your runtime)       → RoboOnto never executes; it judges
5. explain("unitree_g1_edu.event.…")    → interpret what came back
```

RoboOnto is deliberately **read-and-judge only**: it tells an agent what
exists, what is allowed, and why — execution belongs to your runtime. That
separation is what makes the pack safe to open, version, and audit.

## Example

```
Agent: Can I make the G1 walk forward at 3 m/s right now?

→ check_action("set_velocity", params={velocity:[3,0,0]}, state={fsm_mode:"PASSIVE"})
← ok: false
   - precondition failed: fsm_mode == WALKRUN  (robot is PASSIVE — joints relaxed)
   - safety_class MOTION: affects pelvis and both legs
→ the agent switches mode first (set_loco_fsm_mode), re-checks, then acts.
```

No guessing, no training-data folklore about "typical humanoid limits" — the
answer comes from `unitree_sdk2` via the pack's source locators.
