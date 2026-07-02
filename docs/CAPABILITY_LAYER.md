# Capability Layer

RoboOnto now models robot affordances as a first-class layer:

```text
SoftwareComponent / Sensor
  -> provides_capability -> Capability
  -> exposed_via -> Topic / Service / Action
  -> satisfies_requirement -> ServiceRequirement
```

This follows the practical lesson from IEEE/RoSO-style robotics ontologies:
APIs explain how to call a robot; capabilities explain what the robot can do.

## What Changed

- `Capability`: semantic ability such as locomotion velocity control, power diagnostics, visual/depth sensing.
- `SoftwareComponent`: provider boundary for capabilities.
- `CapabilityParameter`: semantic parameters like velocity axes, thresholds, confidence, ranges.
- `ServiceRequirement`: task or service need that can be matched against capabilities.
- `standard_mappings.yaml`: registry for IEEE 1872.2/AuR, CORA, and RoSO terms.

## Agent Effect

Before this layer, an agent had to scan actions and infer intent:

```text
list_actions -> inspect 22 actions -> guess which ones form "safe base motion"
```

Now it can ask for an affordance menu:

```sh
python3 -m roboonto.cli query robots/agibot_x2 agent-affordances navigation
```

The result is already grouped:

- capability: `agibot_x2.cap.locomotion_velocity_control`
- provider: `agibot_x2.sw.motion_controller`
- actions: `set_forward_velocity`, `set_lateral_velocity`, `set_angular_velocity`
- interface: `/aima/mc/locomotion/velocity`
- constraints: mode, input source, static-start thresholds
- safety: all action safety classes and preconditions

This reduces tool-selection work from action enumeration to capability selection.

## Efficiency Gains

- Fewer tool calls: one `agent_affordances` call replaces several `list_actions`, `get_action`, and `query_objects` calls.
- Less prompt reasoning: safety boundaries and providers are returned in structured fields.
- Better recall: ServiceRequirement matching reveals all capabilities needed for a task, including observation dependencies.
- Lower hallucination risk: standard mappings and source fields anchor claims to ontology evidence.

## Completeness Gates

`customer_v1` now checks:

- at least one Capability exists;
- every Capability has a `provides_capability` provider;
- every Capability has `exposed_via` Topic/Service/Action;
- all high-risk actions are reachable from a Capability;
- standard mappings include at least two external vocabularies.

X2 now grades `customer-ready` with these checks enabled.

## Migration

For an existing robot pack:

```sh
python3 -m roboonto.cli infer-capabilities robots/<robot> --yaml
```

Use the draft as a starting point, then add providers, boundaries, standard mappings, and ServiceRequirement links by hand.
