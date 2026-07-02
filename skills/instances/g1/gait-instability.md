---
id: g1-gait-instability
name: G1 步态不稳/摔倒风险
layer: instance
category: mechanical
severity: critical
version: 2.0.0
author: G1 Maintenance Team
applies_to:
  robot: g1
  firmware: ">=2.0"
extends:
  - universal/balance-control-principles
  - humanoid/gait-stability
references:
  ontology:
    - robots/g1/ontology.yaml
  objects:
    - g1.hw.imu
    - g1.hw.foot_force_sensor.*
    - g1.hw.joint.*
    - g1.action.set_gait_parameters
    - g1.action.recalibrate_imu
    - g1.if.topic.imu
    - g1.if.topic.foot_force
triggers:
  - id: T1
    description: 平衡评分低
    ontology_field: g1.estimator.balance_score
    operator: "<"
    value: 0.7
    severity: warning
  - id: T2
    description: 足力分布不均
    ontology_field: g1.estimator.foot_force_variance
    operator: ">"
    value: 0.3
    severity: warning
  - id: T3
    description: 姿态估计置信度低
    ontology_field: g1.estimator.pose_confidence
    operator: "<"
    value: 0.8
    severity: warning
  - id: T4
    description: 检测到摔倒
    ontology_field: g1.event.fall_detected
    operator: "=="
    value: true
    severity: critical
---

# Skill: G1 步态不稳/摔倒风险处理

## 引用上层 skill

- `universal/balance-control-principles`
- `humanoid/gait-stability`

## G1 数据查询

```bash
# IMU 数据
ros2 topic echo {{ ontology.if.topic.imu }} --once

# 足力数据(双脚)
ros2 topic echo {{ ontology.if.topic.foot_force }} --once

# 平衡评分(G1 自带)
ros2 topic echo /rt/balance_status --once
```

## G1 步态参数默认值(参考)

```yaml
step_height: 0.05        # 5cm
step_length: 0.3         # 30cm
stance_width: 0.25       # 25cm
swing_time: 0.4          # 0.4s
double_support: 0.2      # 20%
```

## G1 处置方案

### 方案 1:紧急稳定

参考 humanoid 摔倒模式分类。G1 命令:

```bash
# 蹲下降低质心(手动 / agent action)
{{ ontology.action.set_height }} 0.85   # 从 1.0 降到 0.85m

# 增大支撑宽度
{{ ontology.action.set_gait_parameters }} stance_width=0.3

# 降伺服刚度(避免自激震荡)
{{ ontology.action.set_servo_stiffness }} 0.7
```

### 方案 2:标定恢复(估计器漂移)

```bash
# 静止站立 10 秒
# 然后:
ros2 service call /rt/calibration/full std_srvs/srv/Trigger
```

完整标定参考 `g1/sensor-calibration` skill。

### 方案 3:特定地面调参

| 地面 | step_height | step_length | stance_width | friction_coeff |
|---|---|---|---|---|
| 标准室内地面 | 0.05 | 0.3 | 0.25 | 0.8 |
| 瓷砖(光滑) | 0.04 | 0.25 | 0.3 | 0.6 |
| 地毯 | 0.06 | 0.25 | 0.27 | 0.85 |
| 室外水泥 | 0.05 | 0.3 | 0.25 | 0.75 |
| 楼梯 | 视台阶高 | 视台阶深 | 0.25 | 0.8 |

## G1 案例库

### CASE-2024-008: 瓷砖地面打滑
- **现象**:左右晃动,足力波动大
- **诊断**:摩擦不足
- **处置**:更换橡胶鞋底 + 调步态参数(参考瓷砖列)

### CASE-2024-019: IMU 零偏漂移
- **现象**:静止时姿态偏移 + 行走偏向
- **诊断**:IMU 温漂
- **处置**:重标定 + 上电预热 2 分钟

### CASE-2024-028: 多关节响应延迟
- **现象**:腿部动作不协调,有滞后
- **诊断**:网络延迟
- **处置**:参考 `g1/communication-fault`

## 监控建议

- 持续监控 `balance_score`(预警 < 0.85)
- `foot_force_variance` 长期 > 0.2 表示重心估计有偏
- 每周做姿态稳定性测试(站立 60s,角度漂移 < 1°)

## 引用资源

- 宇树 G1 控制手册 第 4 章
- IMU 标定指南
- 状态估计器调参文档
