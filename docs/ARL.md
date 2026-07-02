# ARL — Agent-Readiness Levels

*How ready is this robot to be driven by an AI agent?*

ARL is a four-level index computed from a pack's reproducible readiness
checks. The scoring rules are open (`roboonto/framework/profiles/`), the
tooling is open (`roboonto readiness`), and anyone can recompute a level
locally — a level is a claim you can verify, not a badge you have to trust.

| Level | Name | Meaning | Verifiable gate (customer_v1) |
|---|---|---|---|
| **ARL-0** | Observable | The robot is described; read-only queries work. | pack loads; `robot` meta present |
| **ARL-1** | Checkable | Agents can *dry-run* calls: actions carry preconditions and safety classes. | grade ≥ `alpha` (all `must` rules: zero loader errors, every action has `safety_class` + standard invoker, ≥1 Mode, compute + power modeled) |
| **ARL-2** | Safely drivable | Agents can plan against *capabilities*, and every dangerous action is reachable through one. | grade ≥ `beta` **and** all capability rules pass: each Capability has a provider and an exposed interface; every MOTION/POWER/IRREVERSIBLE action maps to a Capability; ≥2 external standard vocabularies anchored |
| **ARL-3** | Operable | Audit-grade grounding; fault semantics modeled; ready for unattended agent operation under a runtime gate. | grade = `customer-ready` (100% `should`), ≥90% source coverage, FaultCode/StatusBit depth, dense relation graph |

Current shipped packs (recompute with
`roboonto readiness robots/<r> --profile customer_v1`):

| Pack | Grade | Score | ARL |
|---|---|---|---|
| `agibot_x2` | customer-ready | 100.0 | **ARL-3** |
| `unitree_g1_edu` | customer-ready | 100.0 | **ARL-3** |
| `halfcheetah` (simulated) | — | — | evaluated against a sim profile, not customer_v1 |

## What ARL is not

- **Not a safety certification.** ARL measures the *description* of the
  robot — whether an agent has the facts and constraints it needs. It says
  nothing about the correctness of firmware or the safety of a deployment.
- **Not a conformance claim** to IEEE 1872.x / RoSO. Packs anchor their terms
  to those vocabularies (`standard_mappings.yaml`) as an informative
  alignment.
- **Not about the agent.** ARL grades the robot side. Whether an *agent*
  behaves well against a robot (validates before acting, respects rejections,
  escalates instead of retrying blindly) is a separate, behavioral
  measurement that requires a runtime harness — planned as a companion
  index (ACL, Agent Compliance Level).

## Versioning

Rulers evolve: a pack graded 100 under one profile version may lose points
under a stricter successor (this happened to our own G1 pack when the
capability rules landed). Therefore any published level must pin
**(profile version, pack version)** — e.g. `ARL-3 @ customer_v1 / g1-pack 0.3.0`.
Profiles are versioned files in-repo; old versions remain retrievable
forever via git.
