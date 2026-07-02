---
id: g1-power-system
name: G1 电源系统故障处理
layer: instance
category: electrical
severity: critical
version: 2.0.0
author: G1 Maintenance Team
applies_to:
  robot: g1
  firmware: ">=2.0"
extends:
  - universal/power-system-principles
  - humanoid/power-management
references:
  ontology:
    - robots/g1/ontology.yaml
  objects:
    - g1.hw.battery
    - g1.hw.bms
    - g1.event.battery.*
triggers:
  - id: T1
    description: 电量过低
    ontology_field: g1.hw.battery.level
    operator: "<="
    value: 20
    severity: notice
  - id: T2
    description: 电量严重不足
    ontology_field: g1.hw.battery.level
    operator: "<="
    value: 10
    severity: critical
  - id: T3
    description: 电池温度过高
    ontology_field: g1.hw.battery.temperature
    operator: ">="
    value: 45
    severity: warning
  - id: T4
    description: 电芯压差过大
    ontology_field: g1.hw.battery.cell_delta_v
    operator: ">"
    value: 0.1
    severity: warning
  - id: T5
    description: 充电异常
    ontology_field: g1.hw.charging.status
    operator: "=="
    value: error
    severity: warning
  - id: T6
    description: 电源突然断开
    ontology_field: g1.hw.power.connected
    operator: "=="
    value: false
    severity: critical
---

# Skill: G1 电源系统故障处理

## 引用上层 skill

- `universal/power-system-principles` — 优先级排查框架
- `humanoid/power-management` — 双足电源特殊性

本 skill 只覆盖 G1 特定内容。

## G1 阈值表

| 状态 | warning | critical | 备注 |
|---|---|---|---|
| 电池电量 | < 20% | < 10% | 系统提示 / 强制返航 |
| 电池温度 | ≥ 45°C | ≥ 50°C | 触发热保护 |
| 电芯压差 | > 0.1V | > 0.2V | 不平衡警告 |
| 充电温度 | < 0 或 > 45°C | / | 低温保护或高温拒充 |

## G1 充电器规格

- 输入:100-240V AC
- 输出:54.6V DC,500W
- 充电时间:0-100% 约 2-3 小时
- 必须用原装充电器(第三方功率不足)

## G1 处置步骤(在 universal 优先级框架下展开)

### 优先级 1 红线触发

参考 universal 红线条款。G1 特定动作:

```bash
# 立即切断主电源(物理按钮)— 不要走软件路径
# 软件路径在热失控早期可能已经无法响应
```

G1 急停按钮位于颈后,标记为红色 E-STOP。

### 优先级 2-3 处置

**电压异常**:
```bash
# 查 BMS 状态
{{ ontology.action.query_bms_state }}
# 如果 cell_under_voltage 触发,降负载 + 立即返充
```

**温度告警**:
- 移到通风处
- 切到 DAMPING 模式(关节零力矩,降低电流)
- 监控温度曲线,目标 5 分钟内开始下降

### 优先级 4 处置(电量低)

剩余时间估算:
```
剩余时间 (min) = 当前电量(%) × 总容量(Wh) / 平均功耗(W) / 100
```

G1 典型功耗参考:
- 静止 / damping:30W
- 站立(stand_default):80W
- 慢走:150W
- 快走 / 跑:300-500W
- 高强度任务(楼梯):500-700W

## G1 充电故障树

```
充电无反应
├── 充电器指示灯不亮 → 检查 100-240V AC 输入
├── 接口松动 → 重插紧
├── 温度 < 0 或 > 45°C → 等温度恢复
└── 联系售后

充电速度慢
├── 非原装充电器(< 500W)→ 换原装
├── 高温降流 → 移到低温环境
└── 电池容量 < 80% → 准备更换
```

## G1 维护建议

| 场景 | G1 建议 |
|---|---|
| 充电时机 | 20%-80% 区间循环 |
| 长期存放 | 50% 电量,每月点检 |
| 充电后 | 等 10 分钟冷却再使用 |
| 循环寿命 | ~800 次至 80% 容量 |
| 日历寿命 | ~3 年 |
| 更换标准 | 容量 < 70% 或内阻 > 150% |

## G1 案例库

### CASE-2024-003: 冬季充电失败
- **现象**:0°C 环境下无法充电
- **诊断**:温度保护触发(参考 universal 优先级 3)
- **处置**:移至室内(15°C)预热 30 分钟
- **教训**:G1 北方部署需考虑储存室温度

### CASE-2024-012: 电芯老化不均
- **现象**:续航下降 40%,充不满
- **诊断**:3 号电芯内阻异常高
- **处置**:更换整组电池(不建议单独换电芯)

### CASE-2024-021: 充电接口接触不良
- **现象**:充电时断时续
- **诊断**:充电口簧片松动
- **处置**:更换充电接口

## 引用资源

- G1 BMS 规格书
- 充电器使用手册
- 锂电池安全使用指南
