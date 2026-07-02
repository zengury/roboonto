# URDF Import Changelog — v0.1 → v0.2

## Overview

本次更新引入了 URDF(`x2_ultra.urdf`,v1.3.0)作为第二信息源,完成
**URDF 权威优先 + AimDK 文档业务语义保留**的合并。Ontology 从 v0.1 的
"纯文档派生"升级为"多源 grounded",并**修复了方法论层面暴露的孤岛问题**。

| 指标 | v0.1 | v0.2 | Δ |
|---|---|---|---|
| Objects | 182 | 223 | +41 (全是 Link) |
| Object types | 16 | 17 | +1 (Link) |
| Links (图关系) | 62 | **318** | **+256** (×5.1) |
| Isolated nodes in 3D | 124 (61%) | **6 (2.4%)** | -95% |
| Unit tests | 12/12 | 12/12 | ✓ |

---

## 1. URDF importer 产出

### 新文件

| 文件 | 内容 | 作用 |
|---|---|---|
| `roboonto/importers/urdf.py` | URDF 解析器 + joint patcher + mount patcher + diff reporter | 可复用于任何 URDF-based 机器人 |
| `robots/agibot_x2/kinematics.yaml` | 41 个 Link object + 40 个 parent_of 关系 + 5 个 sensor mount | 补全机器人树结构 |
| `robots/agibot_x2/joints_patch.yaml` | URDF 权威的 31 个 Joint 对象 | 可审阅的 patch |
| `robots/agibot_x2/DIFF_REPORT.md` | 53 条 joint 冲突 + 3 条传感器建议 | 人工 review 交付物 |
| `robots/agibot_x2/derived_links.yaml` | 197 条 "从属性派生的显式关系" | 修复孤岛问题 |

### Joint 字段变化(URDF 权威)

每个 Joint 现在的字段包括:

```yaml
- type: Joint
  id: agibot_x2.hw.left_arm.elbow
  properties:
    urdf_name: left_elbow_joint        # 新
    joint_kind: revolute
    parent_link: agibot_x2.hw.link.left_shoulder_yaw_link   # URDF 权威
    child_link:  agibot_x2.hw.link.left_elbow_link
    origin_xyz: [0, 0, -0.273]          # 新,URDF 权威
    origin_rpy: [0, 0, 0]               # 新
    axis_xyz:   [0, 1, 0]               # 新,URDF 权威
    dof_axis: pitch                     # 已保留,但现在可被 URDF 校验
    position_limit: { min: -2.3556, max: 0.0, unit: rad }   # URDF 权威
    velocity_limit: { value: 15.077,      unit: rad/s }      # 新,URDF 权威
    effort_limit:   { value: 24.0,        unit: Nm }         # 新,URDF 权威(替代假的 120 一刀切)
    name_human: 左Elbow                  # 保留,来自 AimDK
    j_label: J4                          # 保留,来自 AimDK
  source:
    type: urdf+document
    locator: x2_ultra.urdf#joint[left_elbow_joint]
    business_semantics_from: aimdk.docx#§1.7
```

---

## 2. 重大 finding — AimDK 文档的系统性错误

Diff 报告揭示了 **31 个 joint 全部** 有某种冲突,其中最严重的:

### 2a. 扭矩一刀切错误(22/31 受影响)

AimDK 文档的 headline spec "关节峰值扭矩 120 Nm" 被我错误理解为"所有关节都是
120 Nm",实际 URDF 给出真实的 7 档分布:

| Effort (Nm) | Joint 数 | Joint 类型 |
|---|---|---|
| 120 | 9 | 腿主关节 (hip×3, knee) |
| 48 | 2 | waist pitch/roll |
| 36 | 6 | shoulder pitch/roll + ankle pitch |
| 24 | 8 | shoulder yaw + elbow + wrist yaw + ankle roll |
| 4.8 | 4 | wrist pitch/roll |
| 2.6 | 1 | head yaw |
| 0.6 | 1 | head pitch |

**安全影响**:v0.1 的 ontology 告诉 agent 所有关节都能承受 120 Nm。
如果 agent 按此规划 head_pitch 的动作,会过驱 200 倍,直接损毁电机。
这是 ontology 从文档抽取时**必须和 URDF 交叉验证**的教训 —— 本次修复之前,
v0.1 实际上是有安全隐患的。

### 2b. 关节位置极性错误(6/31 受影响)

| Joint | AimDK 文档 | URDF(权威) | 含义 |
|---|---|---|---|
| `left_shoulder_pitch` | [-116.5°, +176.5°] | [-176.5°, +116.5°] | 方向完全反了 |
| `right_shoulder_roll` | [-3.5°, +174.5°] | [-171.5°, +3.5°] | 镜像关节未处理 |
| `left_ankle_pitch` | [-26°, +46°] | [-46°, +26°] | 方向反了 |
| `right_hip_roll` | [-13.5°, +166.5°] | [-166.5°, +13.5°] | 镜像关节未处理 |
| `right_wrist_roll` | [-86.5°, +41.5°] | [-41.5°, +86.5°] | 方向反了 |

这些是 AimDK 只提供单侧数据、我导入时手工镜像导致的。URDF 的 `axis="-1 0 0"`
已经在字段层面处理了方向,应该信任 URDF。

### 2c. 文档缺失或过时(2/31 受影响)

- `head_pitch_joint`:AimDK 说 "0~0°"(实际被标为"未启用")。URDF 给 [-22°, +22°]。
  **机器人实际能点头**,文档未更新。
- `waist_yaw`:AimDK 说 [-196.5°, +126.5°],URDF 说 [-196.5°, +136.5°]。差 10°,
  可能是固件升级后变了。

### 2d. 传感器隐藏

URDF 里有 **9 个 fixed joint**,其中 3 个在 ontology 里没对应的 Sensor 对象:
- `imu_in_torso_link` — 文档里只提到 `imu_torso` 和 `imu_head`,URDF 说还有这一个
- `imu_in_head_link` — ontology 里没登记
- `stereo_head_front` — URDF 把双目当一个 link,ontology 分左右。需要对齐

这 3 个已经在 `DIFF_REPORT.md` 里列为 suggestions,人工确认后补进 ontology。

---

## 3. 方法论缺口修复 — "隐含关系显式化"

### 问题

v0.1 的 3D 图里有 **124 个孤岛节点**(全 245 中的 61%)。你的反馈
"这个空洞不应该出现那么多,可能是你的方法问题" 指出了 ontology 设计的真实缺陷:

**很多关系其实被隐含在对象属性里,但没有显式化为 link。图谱只能看到显式的关系。**

### 识别出的隐含模式

| 隐含位置 | 明确化为什么关系 |
|---|---|
| `StatusBit.carrier_field = "pmu_bool_status"` | `carried_by` Topic(pmu_state)|
| `Joint.parent_link`/`child_link` (字符串)| `has_parent_link` / `has_child_link` Link |
| `PresetMotion.motion_value` 存在 | `invocable_via` Action(set_preset_motion) |
| `Action.priority_integration = "tts_priority"` | `used_by` PriorityLevel |
| `Topic.compute_unit = "pc2"` | `hosts` ComputeUnit |

### 修复产出

`robots/agibot_x2/derived_links.yaml` 共 **197 条派生 link**,分 8 类关系:

- **31 × carried_by** — PMU/BMS StatusBit → pmu_state topic
- **16 × indicates** — StatusBit → 对应硬件(补全之前只有 8 个)
- **7 × carried_by** — TouchEvent → touch topic
- **13 × carried_by** — 手部/关节 FaultCode → 对应 state topic
- **31 × invocable_via** — PresetMotion → set_preset_motion action
- **7 × requires_mode** — PresetMotion → 所需模式
- **60 × has_parent_link / has_child_link** — Joint → Link 运动学链
- **10 × used_by** — PriorityLevel → TTS actions
- **11 × grants** — InputSource → Action 授权
- **11 × allows 扩展** — Mode → Action
- **6 × hosts** — ComputeUnit → Topic

### 结果

孤岛分布:

| Category | v0.1 孤岛 | v0.2 孤岛 |
|---|---|---|
| action | — | 0 (0%) |
| behavior | 31 | **0** |
| event | 41 | **0** |
| hardware | 36 | 1 (1%) |
| interface | 9 | 5 (13%) |
| meta | 7 | **0** |
| **总计** | **124 (61%)** | **6 (2.4%)** |

剩下 6 个孤岛全部是 interface 类的未使用 MsgSchema —— 这是真实空白
(没有 object 引用它们),不是设计缺陷。

### 新的枢纽节点

度数前 5 的节点,直观反映了机器人的"语义重心":

1. **`set_preset_motion`**(degree 39)— 31 个预设动作的统一入口
2. **`/aima/hal/pmu/state`**(degree 33)— 所有电源诊断信息的单一通道
3. **`power`**(degree 22,从 9 升)— 电源子系统是故障推理的中心
4. **`stand_default`**(degree 12)— 大多数动作需要的基础模式
5. **`torso_link`**(degree 11)— 机身 link 是挂载多个关节和传感器的中心

这些"高中心性节点"正是 agent 做诊断/规划推理时应该优先加载上下文的点。

---

## 4. 方法论成果

本次迭代沉淀出三条可 reuse 的 ontology 设计原则:

### 原则 1:多源交叉校验 > 单源完整抽取

单一信息源(哪怕是官方 SDK 文档)可能有系统性错误。
**URDF / SDK 文档 / runtime introspection 应该互为校验**,冲突是 finding。

### 原则 2:任何属性提到的其他对象都必须有显式 link

如果对象 A 的某个属性引用了对象 B,这个引用**必须**同时作为一个 link 显式存在于
`links:` 里。这不是冗余,这是图谱可遍历的前提。

这给 roboonto schema 提出了一个新要求:**v0.2 的 loader 应该 warn 所有"字符串里
写了另一个 object_id 但没对应 link"的情况**。这个检查我会加到 v0.2 的 loader。

### 原则 3:Vendor 给的 headline spec 不能直接做 ontology 属性

文档说"关节峰值扭矩 120 Nm" 是**产品宣传**,不是每个关节的真实 effort_limit。
ontology 层面必须查 URDF 的 `<limit effort="...">` 得到每个关节的真实值。
**宣传语是 marketing 的语义层,ontology 是工程语义层**,不能混。

---

## 5. Next steps

### v0.2 loader 强化(未来 sprint)

- 加一个 validator:扫描所有对象的属性字符串,如果值是已知的 object_id 但没
  对应的 link,就 warn("implicit_reference without explicit link")
- 这会把"隐含关系显式化"从人工维护变成半自动校验

### URDF importer 扩展

当前 `urdf.py` 只处理 `<link>` / `<joint>`。还能扩展:

- `<transmission>` — 虽然我之前说不映射,但实际 transmission 定义了
  motor ratio,agent 做 PID 调参时需要
- 各个 link 的 COM / inertia tensor — 用于动力学规划
- Mujoco 扩展字段(`<mujoco>` block,armature / damping / friction)—
  如果未来接入仿真,是必需的

### 第二台机器人(宇树 G1)

这是下一个最重要的验证。G1 的 URDF 和 X2 差异会暴露当前 schema 的局限。
先做对比 scan(不用完整导入),看结构冲突。
