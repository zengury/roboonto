# Ontology 构建质量方法论 v1.0

> 每接入一台新机器人，按此流程执行。程序验证 + LLM 审查双轨并行。
> 版本: 1.0 | 维护: roboonto team

---

## 0. 核心原则

**数据源决定质量上限。找不到源头 = 质量不可接受。**

```
SDK 深度             Ontology 质量
─────────────────    ────────────
只读 API 名称          < 30 objects, 无法安全操作
读 API + 参数           ~50 objects, 基本操作
读 API + IDL 字段       ~120 objects, 可诊断
读 API + IDL + Error   ~180 objects, 可安全操作+诊断
读上述 + 硬件规格       ~230 objects, 生产级
读上述 + 真机验证       ~250+ objects, X2 级别
```

---

## 1. 数据源检查清单

每次接入新机器人，必须逐一检查以下源头。**任何一项标记为"未找到"需要记录原因**。

### 1.1 运动学 (Kinematics)

| # | 检查项 | 数据源 | 工具 | 产出 |
|---|--------|--------|------|------|
| 1 | URDF/MJCF 文件 | 厂商 GitHub / SDK 包 | `roboonto import urdf` | kinematics.yaml + joints_patch.yaml |
| 2 | 关节名映射 | SDK 头文件 (JointIndex enum) | 手工对照 URDF | 关节名规范 |
| 3 | 关节限位 (position_limit) | URDF | 自动导入 | 带单位的 min/max |
| 4 | 关节力矩限位 (effort_limit) | URDF | 自动导入 | 带单位的 value |
| 5 | 关节速度限位 (velocity_limit) | URDF | 自动导入 | 带单位的 value |

**LLM 审查点 1**: URDF 导入后，检查关节数是否符合该型号公布规格。

### 1.2 通信接口 (Interfaces)

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | Topic 列表 | SDK IDL 头文件 / ROS2 topic list | Topic 对象 |
| 2 | Service 列表 | SDK API 头文件 (*_api.hpp) | Service 对象 |
| 3 | MsgSchema | .msg/.srv 文件 (ROS2) 或 IDL (DDS) | MsgSchema 对象 |
| 4 | 通信协议 | SDK 构建文件 (CMakeLists.txt) | 标注 ROS2/DDS/CAN |

**LLM 审查点 2**: 确认通信协议类型，检查 invoker 类型是否正确映射。

### 1.3 动作 (Actions)

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | API 函数列表 | SDK *_api.hpp (所有 API ID) | Action type_id |
| 2 | 参数定义 | SDK 头文件 (函数签名 / Jsonize 类) | parameters + constraints |
| 3 | 前置条件 | SDK 注释 / example 代码 | preconditions |
| 4 | 安全等级 | API 函数性质 (只读/配置/运动) | safety_class: INFO/CONFIG/MOTION |

**LLM 审查点 3**: 检查每个 Action 的 safety_class 是否合理。不能把所有运动类标成 INFO。

### 1.4 状态位 (StatusBits) — 最容易遗漏！

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | 电机状态 | IDL MotorState_ (每个字段) | mode/temperature/motorstate × 关节数 |
| 2 | 电池状态 | IDL BmsState_ (每个字段) | soc/soh/temperature/current/voltage... |
| 3 | IMU 状态 | IDL IMUState_ (每个字段) | quaternion/gyroscope/accelerometer/rpy |
| 4 | 运动模式状态 | IDL SportModeState_ | fsm_id/fsm_mode/task_id |
| 5 | 主板状态 | IDL MainBoardState_ | fan/temperature/state |
| 6 | 手部状态 | IDL HandState_ (如果有) | motor_state/press_sensor |
| 7 | 无线遥控 | IDL LowState_ wireless_remote | remote state |

**这是 X2 vs G1 质量差距最大的地方。X2 读了 11 个 PMU bit 和 21 个 BMS bit；G1 初版只写了 3 个 StatusBit。IDL 头文件的每个字段都是潜在的 StatusBit。**

**LLM 审查点 4**: 逐一检查 IDL 头文件的所有字段，确认每个有诊断价值的字段都已录入。

### 1.5 故障码 (FaultCodes)

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | 运动故障 | SDK *_error.hpp (loco/arm/...) | FaultCode + 错误码 |
| 2 | 通信故障 | SDK error headers | FaultCode |
| 3 | 硬件故障 | 产品手册 / 维修文档 | FaultCode (标注来源) |

**LLM 审查点 5**: 检查是否遗漏任何 *_error.hpp 文件。

### 1.6 硬件 (Hardware)

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | 计算单元 | 产品规格 / SDK board 定义 | ComputeUnit (含二开板) |
| 2 | 传感器 | URDF + 产品规格 | Sensor 列表 |
| 3 | 电源 | 产品规格 / BMS IDL | PowerSubsystem |

**LLM 审查点 6**: G1 EDU 的 Orin NX 是最容易遗漏的——它是该型号的核心差异化特征。

### 1.7 行为 (Behaviors)

| # | 检查项 | 数据源 | 产出 |
|---|--------|--------|------|
| 1 | 运动模式 | SDK mode 枚举 | Mode 对象 |
| 2 | 预设动作 | SDK example 代码 (函数调用) | PresetMotion 对象 |
| 3 | 模式转换 | SDK example 代码 (模式切换逻辑) | transitions_to links |

**LLM 审查点 7**: 通读所有 example 代码，提取每个函数调用作为潜在 PresetMotion。

---

## 2. 构建流水线

### Step 1: 骨架创建
```bash
cp -r robots/_template robots/{robot_id}
roboonto build init robots/{robot_id} --operator $USER
```
**验证**: ontology.yaml 有正确的 robot.id/vendor/model

### Step 2: URDF 导入
```bash
roboonto import urdf {robot}.urdf -o robots/{robot_id}
roboonto validate robots/{robot_id}
```
**验证**: 0 errors, joints 数与公布规格一致
**LLM 审查**: 关节数是否符合预期

### Step 3: SDK 数据提取 (手工 + 程序辅助)
按 §1.3-§1.7 逐一提取。每完成一个 shard 立即 `roboonto validate`。
```
Actions     → actions.yaml
StatusBits  → events.yaml  ← 最容易遗漏！必须逐字段读 IDL
FaultCodes  → events.yaml
Interfaces  → interfaces.yaml
Behaviors   → behaviors.yaml
Hardware    → kinematics.yaml (append objects)
Compute     → kinematics.yaml (append ComputeUnit)
```

### Step 4: 关系网
```bash
roboonto validate robots/{robot_id}
```
**验证**: 0 errors, 0 warnings
**LLM 审查**: 检查 StatusBit→Sensor、Fault→Component、Action→Service 的关联是否完整

### Step 5: 能力边界
```bash
roboonto readiness robots/{robot_id}
```
**目标**: ≥ beta (90+), 目标 customer-ready (100)

### Step 6: 3D 可视化
```bash
python3 roboonto/tools/generate_3d.py robots/{robot_id}
```

---

## 3. 质量门

| 等级 | 条件 | 含义 |
|------|------|------|
| **alpha** | must ≥ 8/10, should ≥ 7/12 | 可内部测试 |
| **beta** | must 10/10, should ≥ 10/12 | 可外部试用 |
| **customer-ready** | must 10/10, should 12/12, may ≥ 3/4 | 可交付 |

---

## 4. LLM 审查检查点总结

每次构建新 ontology，LLM 在以下 7 个节点参与审查：

| 节点 | 审查内容 | 常见缺陷 |
|:--:|------|------|
| 1 | URDF 导入后 | 关节数不符、缺少限位 |
| 2 | 通信接口后 | 协议类型误标（ROS2 vs DDS）、invoker 类型错误 |
| 3 | Actions 后 | safety_class 过于宽松（MOTION 标成 INFO） |
| 4 | StatusBits 后 | **遗漏 IDL 字段**（最常见的质量杀手） |
| 5 | FaultCodes 后 | 遗漏 error 头文件 |
| 6 | Hardware 后 | 遗漏二开板（Orin 等差异化硬件） |
| 7 | Behaviors 后 | 遗漏 example 中的预设动作 |

---

## 5. 反面案例：G1 第一版

| 问题 | 根因 | 影响 |
|------|------|------|
| StatusBits: 3 × → 108 | 只读了 API 头文件的 API ID，没读 IDL 字段 | 诊断能力从 3 bit 变成 108 bit — 36 倍差距 |
| FaultCodes: 4 → 12 | 没读 error 头文件 | 手写的 fault 都是推测，不是 SDK 真值 |
| ComputeUnits: 1 → 2 | 没查硬件规格 | Orin NX 是 EDU 版最大卖点，遗漏了 |
| DerivedLinks: 60 → 81 | 关系网不够密 | agent 无法从故障关联到子系统 |

**根本原因**: 第二步就走偏了——读了 API 头文件就停，没继续深挖 IDL。

---

## 6. 使用方法

```bash
# 新机器人接入时，加载此文档作为 skill
# LLM agent 在每个审查节点执行对应检查

# 快速检查清单
python3 -c "
checks = [
    'URDF 导入了吗？关节数对吗？',
    '读完全部 IDL 头文件的每个字段了吗？',
    '读完全部 error 头文件了吗？',
    '找到全部计算单元（含二开板）了吗？',
    '从所有 example 代码提取了 PresetMotion 吗？',
    'StatusBits → Sensor 的 derived_links 完整吗？',
    'roboonto readiness 到 customer-ready 了吗？',
]
for i, c in enumerate(checks, 1):
    print(f'{i}. {c}')
"
```
