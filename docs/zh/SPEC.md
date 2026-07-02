# RoboOnto 规范

> 版本 0.3 · 规范性来源:[`roboonto/core/meta-schema.yaml`](../../roboonto/core/meta-schema.yaml)(YAML 为准,本文是解释)
> English version: [../SPEC.md](../SPEC.md)

RoboOnto 是机器人的机器可读规格语言。一个 **pack**(`robots/<robot>/`)描述一台机器人:由什么构成、怎么与它通信、能做什么、以及每个动作在什么条件下合法。Pack 是静态、可版本化、可审计的——它描述**应然**(限位、约束、关系),从不承载**实然**(实时状态)。

```
meta-schema.yaml          语法书 — 什么算合法的 pack
core-object-types.yaml    词汇表 — 跨机器人共享的对象类型
robots/<X>/*.yaml         百科全书 — 用这门语言写出的一台机器人
```

---

## 1. ObjectType — 名词

ObjectType 声明世界上存在某种东西,以及它有哪些属性。

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` | ✔ | 全局 PascalCase 标识(`Joint`、`Topic`、`Capability`) |
| `category` | ✔ | `hardware` · `software` · `interface` · `behavior` · `event` · `frame` · `capability` · `meta` |
| `description` | ✔ | 人类可读简述 |
| `extends` | | 继承另一个 ObjectType |
| `properties` | | 属性定义(见 §2) |
| `identifying_property` | | 哪个属性作实例 id(默认 `id`) |
| `constraints` | | 实例必须满足的不变量 |
| `sources_hint` | | 典型数据源(URDF / SDK 文档 / 内省) |

`core-object-types.yaml` 自带的核心类型:

- **hardware** — `Link`、`Joint`、`Sensor`、`ComputeUnit`、`PowerSubsystem`、`EndEffector`
- **software** — `SoftwareComponent`、`Process`、`App`、`OTAPackage`
- **interface** — `Topic`、`Service`、`MsgSchema`、`SrvSchema`
- **behavior** — `Mode`、`PresetMotion`、`ControlLoop`
- **event** — `StatusBit`、`FaultCode`、`TouchEvent`
- **capability** — `Capability`、`CapabilityParameter`、`ServiceRequirement`(§6)
- **frame** — `CoordinateFrame`
- **meta** — `InputSource`、`PriorityLevel`、`SafetyClass`

## 2. Properties — 类型系统

原始类型:`string`、`int`、`float`、`bool`、`enum`(配 `values`)、`range`(`{min, max, unit}`)、`vector3`、`quaternion`。
引用类型:`ref`(配 `target: <ObjectType>`)、`ref_list`。
任意属性的元数据:`unit`(SI 优先)、`required`、`unique`、`default`、`source`(§5)。

物理量必须带单位。校验器强制同名属性在一个 pack 内单位一致。

## 3. LinkType — 关系

对象实例之间的有向、有类型、有基数检查的关系:

```yaml
- id: provides_capability     # snake_case
  source: SoftwareComponent   # 源端 ObjectType
  target: Capability
  cardinality: many_to_many   # one_to_one | one_to_many | many_to_many
  inverse_id: provided_by     # 可选
```

## 4. ActionType — 动词(kinetic 层)

Action 是 RoboOnto 区别于只读知识图谱的关键:它声明 agent 可以**做**什么,以及调用在什么条件下合法。

| 字段 | 必填 | 含义 |
|---|---|---|
| `id` / `type_id` | ✔ | snake_case 动作名 |
| `description` | ✔ | |
| `invoker` | ✔ | 调用方式:`ros2_topic` · `ros2_service` · `dds_service` · `dds_topic` · `cli` · `compound` |
| `parameters` | ✔ | 参数 schema(name、type、unit、constraints) |
| `affects` | ✔ | 动作触及哪些硬件/软件(`ref_list`) |
| `preconditions` | | 执行前必须全部成立的表达式 |
| `param_constraints` | | 范围 / 枚举 / 跨参数约束 |
| `postconditions` | | 预期效果(供因果推理) |
| `side_effects` | | 可能触发的事件 |
| `rollback` | | 对应的补偿动作(如有) |
| `safety_class` | | `INFO` · `CONFIG` · `MOTION` · `POWER` · `IRREVERSIBLE` |
| `idempotent` | | bool |

**纪律:** precondition 是「对本体的查询 + 注入的运行时状态」——pack 本身从不存储实时状态。运行时 `ActionValidator` 接收当前状态、求值每条 precondition,返回通过/失败及失败表达式与错误信息:

```python
from roboonto.api.action_validator import ActionValidator
report = v.check("set_velocity",
                 params={"velocity": [0.5, 0, 0], "duration": 2.0},
                 state={"fsm_mode": "WALKRUN"})
```

Precondition DSL 谓词:`eq ne lt gt le ge`、`in / not_in`、`exists / not_exists`、`has_link / has_object`、`@state.X`(运行时状态)、`@ontology.X`(本体查询)。

## 5. Source — 溯源

每个对象和每个属性值都可以带 `source` 块。这让每条断言可审计、可 diff、可更正。

```yaml
source:
  type: sdk_code            # document | urdf | ros2_introspect | sdk_code | manual | derived | inferred
  locator: "unitree_sdk2/include/unitree/robot/g1/loco/g1_loco_api.hpp"
  extractor: "sdk_code@0.1" # 可选:导入器 + 版本
  extracted_at: "2026-05-16T00:00:00Z"
  confidence: 0.95          # 可选,LLM 抽取时有意义
```

校验器报告来源覆盖率;`customer_v1` 发布 profile 要求 ≥60%(审计级 ≥90%)。

## 6. 能力层

API 解释**怎么调用**机器人;能力解释机器人**能做什么**。

```
SoftwareComponent / Sensor
  ── provides_capability ──▶ Capability
                               ── exposed_via ──▶ Topic / Service / Action
                               ── has_parameter ──▶ CapabilityParameter
                               ── satisfies ──▶ ServiceRequirement
```

- **`Capability`** — 语义能力(`capability_kind`:sensing、actuation、perception、localization、mapping、planning、navigation、manipulation、diagnosis、communication、interaction),带 `produces` / `consumes` / `detects`、`environment_requirements`、`boundaries` 和 `standard_mappings`。
- **`ServiceRequirement`** — 任务侧需求,可与能力匹配(`Query.explain_service_fit`)。
- **`standard_mappings.yaml`** — 每个 pack 的注册表,把 RoboOnto 术语锚定到 IEEE 1872.1(CORA)、IEEE 1872.2(AuR)与 RoSO 词表。这是**参考性**对齐,非合规声明。

为已有 pack 起草能力层:`roboonto infer-capabilities <dir> --yaml`,然后人工审校提供方、边界与映射。

## 7. 命名与标识

| 类别 | 约定 | 示例 |
|---|---|---|
| ObjectType id | PascalCase | `Joint`、`Capability` |
| 实例 id | `<robot>.<category>.<dotted_path>` | `unitree_g1_edu.hw.joint.left_knee` |
| LinkType / ActionType id | snake_case | `provides_capability`、`set_velocity` |
| 单位 | SI 优先 | `m/s`、`rad`、`Nm`、`Hz` |

## 8. Pack 布局

```yaml
# robots/<robot>/ontology.yaml — 入口
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
  - capability_boundary.yaml   # 诚实的盲区声明
```

每个分片文件的顶层键为以下四种的组合:`object_types`、`objects`、`links`、`actions`。

## 9. 校验

`roboonto validate <dir>` 强制:

- 所有 `ref` 可解析;同 category 下 id 不重复
- 约束表达式可解析
- 同名属性单位一致
- 来源覆盖率报告;跨来源冲突报告(绝不自动合并)

`roboonto readiness <dir> --profile customer_v1` 按 must/should/may 发布清单给 pack 评级(`fail → alpha → beta → customer-ready`)——评级如何映射到 Agent 就绪度等级见 [ARL.md](ARL.md)。
