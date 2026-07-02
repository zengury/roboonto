# roboonto

[![CI](https://github.com/zengury/roboonto/actions/workflows/ci.yml/badge.svg)](https://github.com/zengury/roboonto/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)

**English** · [中文](README.zh.md)

A toolchain that turns robot vendor materials (URDF, SDK, manuals) into a queryable, agent-ready ontology — and ships first-party ontologies for specific robots.

**Docs:** [Quickstart](docs/QUICKSTART.md) · [Specification](docs/SPEC.md) · [MCP integration](docs/MCP.md) · [Agent-Readiness Levels](docs/ARL.md) · [Capability layer](docs/CAPABILITY_LAYER.md) · [Data sources](SOURCES.md) · [中文文档](docs/zh/)

```
vendor materials ──► [ roboonto importers ] ──► YAML ontology ──► [ api ] ──► your agent / runtime
                                                       ▲                ▲
                                                       │                │
                                                  log/mcap ──► [ ingestor ] ──► [ diagnostics ]
```

## What you get

- **A tool** (this repo): importers, an ontology API, a log ingestor, and reference diagnostics.
- **Packs** (under `robots/`): per-robot ontologies. AgiBot X2 ships v0.3.0.

## Status

| | |
|---|---|
| Version | v0.3.0 capability layer |
| Robots covered | AgiBot X2 · Unitree G1 EDU · HalfCheetah (sim) |
| Pack grades | X2 **customer-ready 100/100** · G1 **customer-ready 100/100** ([ARL-3](docs/ARL.md)) |
| X2 pack contents | 256 objects · 22 actions · 403 links · 11 capabilities |
| X2 3D atlas | `robots/agibot_x2/roboonto_pack_3d.html` |
| Tests | 107 |
| Python | 3.10+ |

## Install

```sh
pip install roboonto
```

Robot packs (G1, X2, …) live in this repo — clone for full ontologies and examples:

```sh
git clone https://github.com/zengury/roboonto
cd roboonto
pip install -e .
```

Optional, for log ingestion:
```sh
pip install pyyaml mcap mcap-ros2-support
```

## Use

### Query an ontology

```python
from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query

ontology = OntologyLoader("robots/agibot_x2").load()
q = Query(ontology)

# What joints are in the left arm?
for j in q.objects_of_type("Joint"):
    if j["id"].startswith("agibot_x2.kin.joint.left_arm"):
        print(j["id"], j["properties"]["effort_limit"])

# What actions are allowed in LOCOMOTION_DEFAULT?
for a in q.actions_allowed_in_mode("LOCOMOTION_DEFAULT"):
    print(a["type_id"], a.get("safety_class"))

# What can the robot do, and how should an agent call it?
for affordance in q.agent_affordance_menu(capability_kind="navigation"):
    print(affordance["name"], [a["id"] for a in affordance["actions"]])
```

### Capability-first agent queries

```sh
python3 -m roboonto.cli query robots/agibot_x2 agent-affordances navigation
python3 -m roboonto.cli query robots/agibot_x2 service-fit agibot_x2.req.safe_base_motion
python3 -m roboonto.cli infer-capabilities robots/agibot_x2 --yaml
```

The capability layer separates `what the robot can do` from `how to call it`:

```
SoftwareComponent / Sensor
  -> provides_capability -> Capability
  -> exposed_via -> Topic / Service / Action
  -> satisfies_requirement -> ServiceRequirement
```

See [`docs/CAPABILITY_LAYER.md`](docs/CAPABILITY_LAYER.md).

### Standards alignment

RoboOnto keeps its engineering YAML format, but the v0.3 capability layer includes explicit mappings to robotics ontology standards:

- **IEEE 1872.2 / AuR**: anchors robot autonomy concepts such as autonomous capability, task, autonomous system, and environment.
- **IEEE 1872.1 / CORA**: anchors core robotics terms for robot, actuator, sensor, and related physical entities.
- **RoSO**: anchors service-oriented concepts such as component, function, sensing, actuation, and parameters.

These mappings live in each pack's `standard_mappings.yaml` and in object-level `standard_mappings` fields where useful. They are used as vocabulary anchors for agents and tools, while RoboOnto remains the operational schema for loading, querying, validation, CLI, MCP, and 3D visualization.

### 3D ontology atlas

Open `robots/agibot_x2/roboonto_pack_3d.html` in a browser to inspect the X2 ontology interactively. The atlas version is synced with the package version (`v0.3.0`) and supports:

- `Graph` mode for the whole relation network.
- `Layered` mode for hardware / compute / interface / action / capability / requirement paths.
- Node search, node explanations, incoming/outgoing relation inspection, and one-hop navigation.

### Validate an action call

```python
from roboonto.api.action_validator import ActionValidator

v = ActionValidator(ontology)
report = v.check(
    "set_forward_velocity",
    params={"forward_velocity": 0.05, "source": "test"},
    state={"mc_action": "LOCOMOTION_DEFAULT", "is_moving": False,
           "registered_input_sources": ["test"]},
)
# report.failures explains why precondition fails
```

### Ingest a session log

```sh
python3 -m roboonto.tools.log_ingestor \
    /path/to/session_dir \
    --robot agibot_x2 \
    --output ./output \
    -v
```

Reads `bag/`, `info/`, `log/` subdirs. Handles `.mcap`, `.atop`, `.log`, `.yaml`, `.json`. Produces `session.summary.json` + `coverage.report.md` + `stats.json`.

## Layout

```
roboonto/
├── roboonto/              tool code
│   ├── core/              meta-schema (defines what an ontology is)
│   ├── api/               loader · query · action validator
│   ├── importers/         URDF · SDK docs · ...
│   └── tools/             log ingestor + readers (mcap, atop)
├── robots/                ontology packs
│   └── agibot_x2/         hardware · kinematics · capabilities · interfaces · behaviors · events · actions · derived_links
├── skills/                operational knowledge (universal · humanoid · instance)
├── docs/                  spec · quickstart · MCP · ARL · quality methodology
├── examples/              quickstart scripts
└── tests/
```

## Design

The repo separates two things deliberately:

- **archive** (under `robots/`): YAML files describing what a robot *is*. Per-robot. Versioned independently.
- **engine** (under `roboonto/`): Python code that loads, queries, validates, ingests. Robot-agnostic.

Source provenance is mandatory. Every ontology object carries a `source` field: `document` (with locator), `urdf_import`, `log_observation` (with confidence + diff_status), or `aimrt_introspect`. Mixed-source claims are explicit, not hidden.

For a deeper dive: [`docs/SPEC.md`](docs/SPEC.md), [`docs/ONTOLOGY_QUALITY_METHODOLOGY.md`](docs/ONTOLOGY_QUALITY_METHODOLOGY.md).

## Roadmap

- v0.4 — ACL (Agent Compliance Level) conformance harness · sim readiness profile · diagnostics engine MVP
- v0.5 — pack registry · third robot pack
- v1.0 — web dashboard · CLI completeness

## License

Code and schema: [Apache-2.0](LICENSE). Robot packs contain factual
specifications extracted from publicly available vendor materials — see
[SOURCES.md](SOURCES.md) for per-pack provenance and the correction policy.
