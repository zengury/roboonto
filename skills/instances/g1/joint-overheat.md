---
id: g1-joint-overheat
name: G1 关节过热处理
layer: instance
category: thermal
severity: high
version: 2.0.0
author: G1 Maintenance Team
applies_to:
  robot: g1
  firmware: ">=2.0"
extends:
  - universal/thermal-management-principles
  - humanoid/joint-thermal-management
references:
  ontology:
    - robots/g1/ontology.yaml
  objects:
    - g1.hw.joint.*
    - g1.event.thermal.*
    - g1.action.set_velocity
    - g1.if.topic.joint_state
triggers:
  - id: T1
    description: 温度超过警告阈值
    ontology_field: g1.hw.joint.*.motor_temperature
    operator: ">="
    value: 45
    severity: warning
  - id: T2
    description: 温度超过危险阈值
    ontology_field: g1.hw.joint.*.motor_temperature
    operator: ">="
    value: 50
    severity: critical
  - id: T3
    description: 高负载下的高温
    ontology_field: g1.hw.joint.*.torque_ratio
    operator: ">"
    value: 0.8
    additional_condition: motor_temperature >= 43
    severity: warning
  - id: T4
    description: 温度快速上升
    ontology_field: g1.hw.joint.*.temperature_rise_rate_5min
    operator: ">"
    value: 3.0
    severity: warning
---

# Skill: G1 关节过热处理

## 引用上层 skill

阅读本 skill 前请先理解:
- `universal/thermal-management-principles` — 三步诊断方法
- `humanoid/joint-thermal-management` — 双足特定关注点

本 skill 只覆盖 **G1 特定**的内容:阈值、命令、SOP。

## G1 阈值表

| 关节类型 | 警告阈值 | 危险阈值 | 工作温度上限 |
|---|---|---|---|
| 髋关节(pitch/roll/yaw) | 45°C | 50°C | 60°C |
| 膝关节 | 45°C | 50°C | 60°C |
| 踝关节(pitch/roll) | 45°C | 50°C | 60°C |
| 肩关节 | 42°C | 48°C | 55°C |
| 肘关节 | 42°C | 48°C | 55°C |
| 手腕关节 | 40°C | 45°C | 50°C |

## G1 数据查询命令

诊断时执行(替换 `<JOINT_NAME>` 为具体关节,如 `left_knee_joint`):

```bash
# 单关节实时温度
ros2 topic echo {{ ontology.if.topic.joint_state }} --once \
  | grep -A 2 '<JOINT_NAME>'

# 全部下肢关节温度对比(诊断左右温差)
ros2 topic echo {{ ontology.if.topic.joint_state }} --once \
  | grep -E '(hip|knee|ankle).*temperature'

# 历史温度曲线(过去 10 分钟)
ros2 bag info <bag-file> | grep temperature
```

## G1 处置 Action

**降速**:
{{ ontology.action.set_velocity }} 调用,参数 `velocity_scale=0.7`(降至 70%)。

**阻尼模式**(机械问题需停机时):
{{ ontology.action.set_mc_action }} 切换到 `DAMPING` 模式。

## G1 特定 SOP

### 减速器润滑(累计运行 200h)

G1 各关节使用谐波减速器,润滑脂规格:

| 关节 | 润滑脂型号 | 维护周期 |
|---|---|---|
| 髋/膝(高负荷) | 厂家专用脂 A | 200h |
| 踝(中负荷) | 厂家专用脂 B | 400h |
| 肩/肘/腕(低负荷) | 厂家专用脂 B | 600h |

### G1 特有的发热模式

#### 模式 1:夏季工厂高温多关节同热
- 触发条件:环境 > 35°C + 多关节同时升至 > 45°C
- 归因:环境因子(参考 universal 第三步)
- G1 特定建议:避开 11:00-15:00,任务排到早晚

#### 模式 2:左右温差异常(单腿过热)
- 触发条件:左右对称关节温差 > 5°C
- 归因:机械因子(参考 humanoid)
- G1 特定 SOP:先停机做"被动屈伸测试"(让 G1 进入 DAMPING 模式,人工活动腿)

## G1 案例库

### CASE-2024-001: 左膝关节过热 ★ 经典负载因子
- **环境**:连续上下楼梯测试 30 分钟
- **现象**:左膝 48°C,右膝 41°C
- **诊断**:torque_ratio 0.85,环境温度 32°C — 高负载 + 较高环境
- **处置**:降速至 70%,增加休息间隔
- **结果**:温度降至 42°C,任务恢复
- **教训**:楼梯任务必须监控温度,设阈值 43°C 而非 45°C

### CASE-2024-015: 右肩温度异常 ★ 经典机械因子
- **现象**:右肩 45°C,左肩 38°C,温差 7°C
- **诊断**:停机被动测试听到"咔哒声",润滑不足
- **处置**:补充润滑脂
- **结果**:恢复正常,左右温差 < 2°C
- **教训**:**单侧温度高优先查机械,不要先降速**

### CASE-2024-023: 夏季多关节过热 ★ 经典环境因子
- **现象**:左膝 46°C,右膝 46°C,左踝 45°C(温差均 < 2°C)
- **环境**:工厂 38°C
- **诊断**:多关节均匀升温 + 高环境温度 = 环境因子
- **处置**:增加工业风扇,任务调整到早晚
- **教训**:**均匀过热不要查机械**——浪费时间

## 预防措施(G1 特定)

1. **每 500h 检查润滑状态**(髋/膝)
2. **每月做被动测试**(各关节手动屈伸,听异响)
3. **温度预警阈值设 43°C**(比报警阈值低 2°C,提前响应)
4. **夏季巡检频率加倍**

## 引用资源

- 宇树 G1 维护手册 v2.1 第 3 章
- 电机驱动器规格书
- 减速器维护指南
- {{ ontology.if.topic.joint_state }} msg schema

## 升级记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.0.0 | 2026-03-01 | 原 mcp-ros-diagnosis 单文件版 |
| 2.0.0 | 2026-04-25 | 三层重构:抽取 universal + humanoid 上层,本文件只保留 G1 特定 |
