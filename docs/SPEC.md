# RoboOnto Specification

> Version 0.3 · Normative source: [`roboonto/core/meta-schema.yaml`](../roboonto/core/meta-schema.yaml)
> (the YAML is authoritative; this document explains it)
> 中文版: [zh/SPEC.md](zh/SPEC.md)

RoboOnto is a machine-readable specification language for robots. A **pack**
(`robots/<robot>/`) describes one robot: what it is made of, how to talk to
it, what it can do, and under which conditions an action is legal. Packs are
static, versionable, and auditable — they describe *what should be*
(limits, constraints, relations), never *what currently is* (live state).

```
meta-schema.yaml          the grammar  — what counts as a valid pack
core-object-types.yaml    the lexicon  — shared object types across robots
robots/<X>/*.yaml         the encyclopedia — one robot, written in that language
```

---

## 1. ObjectType — nouns

An ObjectType declares that a kind of thing exists and what properties it has.

| Field | Req | Meaning |
|---|---|---|
| `id` | ✔ | Global PascalCase identifier (`Joint`, `Topic`, `Capability`) |
| `category` | ✔ | `hardware` · `software` · `interface` · `behavior` · `event` · `frame` · `capability` · `meta` |
| `description` | ✔ | Human-readable summary |
| `extends` | | Inherit from another ObjectType |
| `properties` | | Property definitions (see §2) |
| `identifying_property` | | Which property is the instance id (default `id`) |
| `constraints` | | Invariants instances must satisfy |
| `sources_hint` | | Typical data sources (URDF / SDK docs / introspection) |

Core types shipped in `core-object-types.yaml`:

- **hardware** — `Link`, `Joint`, `Sensor`, `ComputeUnit`, `PowerSubsystem`, `EndEffector`
- **software** — `SoftwareComponent`, `Process`, `App`, `OTAPackage`
- **interface** — `Topic`, `Service`, `MsgSchema`, `SrvSchema`
- **behavior** — `Mode`, `PresetMotion`, `ControlLoop`
- **event** — `StatusBit`, `FaultCode`, `TouchEvent`
- **capability** — `Capability`, `CapabilityParameter`, `ServiceRequirement` (§6)
- **frame** — `CoordinateFrame`
- **meta** — `InputSource`, `PriorityLevel`, `SafetyClass`

## 2. Properties — the type system

Primitive types: `string`, `int`, `float`, `bool`, `enum` (+`values`),
`range` (`{min, max, unit}`), `vector3`, `quaternion`.
Reference types: `ref` (+`target: <ObjectType>`), `ref_list`.
Metadata on any property: `unit` (SI preferred), `required`, `unique`,
`default`, `source` (§5).

Physical quantities always carry units. The validator enforces that a
property with the same name uses a consistent unit across a pack.

## 3. LinkType — relations

Directed, typed, cardinality-checked relations between object instances.

```yaml
- id: provides_capability     # snake_case
  source: SoftwareComponent   # source ObjectType
  target: Capability
  cardinality: many_to_many   # one_to_one | one_to_many | many_to_many
  inverse_id: provided_by     # optional
```

## 4. ActionType — verbs (the kinetic layer)

Actions are what distinguish RoboOnto from a read-only knowledge graph: they
declare what an agent may *do*, and under which conditions the call is legal.

| Field | Req | Meaning |
|---|---|---|
| `id` / `type_id` | ✔ | snake_case action name |
| `description` | ✔ | |
| `invoker` | ✔ | How to call it: `ros2_topic` · `ros2_service` · `dds_service` · `dds_topic` · `cli` · `compound` |
| `parameters` | ✔ | Parameter schema (name, type, unit, constraints) |
| `affects` | ✔ | Which hardware/software the action touches (`ref_list`) |
| `preconditions` | | Expressions that must all hold before execution |
| `param_constraints` | | Range / enum / cross-parameter constraints |
| `postconditions` | | Expected effects (for causal reasoning) |
| `side_effects` | | Events the action may trigger |
| `rollback` | | The compensating action, if any |
| `safety_class` | | `INFO` · `CONFIG` · `MOTION` · `POWER` · `IRREVERSIBLE` |
| `idempotent` | | bool |

**Discipline:** preconditions are *queries against the ontology plus injected
runtime state* — the pack never stores live state itself. At runtime the
`ActionValidator` receives the current state, evaluates every precondition,
and returns pass/fail with the failing expression and its error message:

```python
from roboonto.api.action_validator import ActionValidator
report = v.check("set_velocity",
                 params={"velocity": [0.5, 0, 0], "duration": 2.0},
                 state={"fsm_mode": "WALKRUN"})
```

Precondition DSL predicates: `eq ne lt gt le ge`, `in / not_in`,
`exists / not_exists`, `has_link / has_object`, `@state.X` (runtime state),
`@ontology.X` (ontology query).

## 5. Source — grounding

Every object and every property value may carry a `source` block. This makes
each assertion auditable, diffable, and correctable.

```yaml
source:
  type: sdk_code            # document | urdf | ros2_introspect | sdk_code | manual | derived | inferred
  locator: "unitree_sdk2/include/unitree/robot/g1/loco/g1_loco_api.hpp"
  extractor: "sdk_code@0.1" # optional: importer + version
  extracted_at: "2026-05-16T00:00:00Z"
  confidence: 0.95          # optional, meaningful for LLM extraction
```

The validator reports source coverage; the `customer_v1` release profile
requires ≥60% (audit grade: ≥90%).

## 6. Capability layer

APIs explain *how to call* a robot; capabilities explain *what it can do*.

```
SoftwareComponent / Sensor
  ── provides_capability ──▶ Capability
                               ── exposed_via ──▶ Topic / Service / Action
                               ── has_parameter ──▶ CapabilityParameter
                               ── satisfies ──▶ ServiceRequirement
```

- **`Capability`** — a semantic ability (`capability_kind`: sensing, actuation,
  perception, localization, mapping, planning, navigation, manipulation,
  diagnosis, communication, interaction) with `produces` / `consumes` /
  `detects`, `environment_requirements`, `boundaries`, and
  `standard_mappings`.
- **`ServiceRequirement`** — a task-side need that can be matched against
  capabilities (`Query.explain_service_fit`).
- **`standard_mappings.yaml`** — per-pack registry anchoring RoboOnto terms to
  IEEE 1872.1 (CORA), IEEE 1872.2 (AuR), and RoSO vocabulary. This is an
  *informative* alignment, not a conformance claim.

Bootstrap a draft for an existing pack with
`roboonto infer-capabilities <dir> --yaml`, then hand-review providers,
boundaries, and mappings.

## 7. Naming & identity

| Kind | Convention | Example |
|---|---|---|
| ObjectType ids | PascalCase | `Joint`, `Capability` |
| Instance ids | `<robot>.<category>.<dotted_path>` | `unitree_g1_edu.hw.joint.left_knee` |
| LinkType / ActionType ids | snake_case | `provides_capability`, `set_velocity` |
| Units | SI preferred | `m/s`, `rad`, `Nm`, `Hz` |

## 8. Pack layout

```yaml
# robots/<robot>/ontology.yaml — the entry point
robot:
  id: unitree_g1_edu
  vendor: Unitree Robotics
  model: G1 EDU (23-DOF)
  roboonto_version: "0.1"
includes:
  - standard_mappings.yaml
  - hardware.yaml
  - kinematics.yaml
  - behaviors.yaml
  - events.yaml
  - interfaces.yaml
  - actions.yaml
  - capabilities.yaml
  - derived_links.yaml
  - capability_boundary.yaml   # honest blind-spot declarations
```

Each shard file contains any of four top-level keys: `object_types`,
`objects`, `links`, `actions`.

## 9. Validation

`roboonto validate <dir>` enforces:

- all `ref`s resolve; no duplicate ids per category
- constraint expressions parse
- unit consistency for same-named properties
- source-coverage report; cross-source conflicts reported (never auto-merged)

`roboonto readiness <dir> --profile customer_v1` grades a pack
(`fail → alpha → beta → customer-ready`) against a release checklist of
must/should/may rules — see [`ARL.md`](ARL.md) for how grades map to
Agent-Readiness Levels.
