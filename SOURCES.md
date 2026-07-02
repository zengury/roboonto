# Data Sources & Provenance

The robot packs under `robots/` contain **factual engineering specifications**
(joint limits, torque ratings, topic names, API ids, fault codes) extracted
from publicly available vendor materials. Copyright in the original documents
and SDKs remains with their respective vendors. Every extracted assertion
carries a `source` field (type + locator) pointing back to its origin — see
`roboonto/core/meta-schema.yaml` §5 for the grounding schema.

The RoboOnto code and schema are licensed under Apache-2.0 (see `LICENSE`).
The standard-vocabulary mappings in `standard_mappings.yaml` files are an
**informative alignment** with IEEE 1872.1 (CORA), IEEE 1872.2 (AuR), and
RoSO terminology — not a conformance or certification claim.

## Per-pack sources

### robots/agibot_x2 — AgiBot X2

| Source | Type | Notes |
|---|---|---|
| AimDK documentation (`aimdk.docx` locators) | vendor docs, publicly released | actions, interfaces, PMU/power, fault codes |
| X2 URDF | vendor release | kinematics, joint/link parameters |
| On-robot verification | first-party measurements | capability boundaries, probe results |

### robots/unitree_g1_edu — Unitree G1 EDU

| Source | Type | Notes |
|---|---|---|
| [`unitree_sdk2`](https://github.com/unitreerobotics/unitree_sdk2) | public GitHub, BSD-3-Clause | loco/arm/audio APIs, DDS IDL (LowState/IMUState/BmsState) |
| [`unitree_ros`](https://github.com/unitreerobotics/unitree_ros) G1 description | public GitHub | URDF, joint limits, STL meshes (23-DOF rev_1_0) |
| Unitree public documentation | vendor docs | mode machine, FSM ids |

### robots/halfcheetah — MuJoCo HalfCheetah

| Source | Type | Notes |
|---|---|---|
| [Gymnasium / MuJoCo](https://github.com/Farama-Foundation/Gymnasium) HalfCheetah model | open source | simulated robot; no physical hardware |

## Takedown / corrections

If you are a rights holder and believe any extracted data exceeds fair use of
factual specifications, or you spot an incorrect assertion, please open an
issue — every assertion is traceable to its locator, so corrections are
surgical and auditable.
