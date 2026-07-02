---
id: g1-sensor-calibration
name: G1 传感器标定
layer: instance
category: software
severity: medium
version: 2.0.0
author: G1 Maintenance Team
applies_to:
  robot: g1
  firmware: ">=2.0"
extends:
  - universal/sensor-calibration-principles
  - humanoid/sensor-calibration
references:
  ontology:
    - robots/g1/ontology.yaml
  objects:
    - g1.hw.imu
    - g1.hw.foot_force_sensor.*
    - g1.hw.joint.*
    - g1.action.calibrate_imu
    - g1.action.calibrate_foot_force
    - g1.action.calibrate_joint_zero
---

# Skill: G1 传感器标定

## 引用上层 skill

- `universal/sensor-calibration-principles`
- `humanoid/sensor-calibration`

## G1 标定服务

### 1. IMU 标定

**前置条件**(参考 universal + humanoid):
- 绝对水平面
- 上电后等 5 分钟(温度稳定)
- 完全静止

**命令**:
```bash
ros2 service call /rt/calibration/imu std_srvs/srv/Trigger
# 等待 ~30 秒
```

**G1 验证标准**:
```
加速度计零偏:|bias| < 0.05 m/s²
陀螺仪零偏:  |bias| < 0.01 rad/s
```

**验证查询**:
```bash
ros2 topic echo {{ ontology.if.topic.imu }} --once
```

---

### 2. 足力传感器标定

**前置条件**:
- 双脚站立在平坦硬质地面
- 标准站立姿态
- 无外力作用

**命令**:
```bash
ros2 service call /rt/calibration/force std_srvs/srv/Trigger
```

**G1 验证标准**(假设 G1 重量 ~35kg):
```
双脚力之和:330N - 360N(正常)
左右力之差:< 20N(重心居中)
```

---

### 3. 关节零位标定

**触发场景**:更换电机后、关节实际位置与指令不符、行走姿态异常。

**步骤**:
```bash
ros2 service call /rt/calibration/joint_zero std_srvs/srv/Trigger
# 机器人会缓慢移动到标定姿态
# 人工对齐机械零位标记
ros2 service call /rt/calibration/joint_confirm std_srvs/srv/Trigger
```

**G1 各关节零位特征**:

| 关节 | 零位特征 |
|---|---|
| 髋关节 | 大腿竖直向下 |
| 膝关节 | 小腿与大腿成 90° |
| 踝关节 | 脚掌水平 |
| 肩关节 | 手臂自然下垂 |
| 肘关节 | 前臂水平 |

⚠️ 关节零位标定需要精确对齐,**建议由培训过的工程师执行**。

---

### 4. 完整标定(一键)

```bash
ros2 service call /rt/calibration/full std_srvs/srv/Trigger
# 约 5 分钟,自动跑:姿态检查 → IMU → 足力 → 关节零位检查 → 行走验证
```

## G1 标定参数管理

### 备份

```bash
cp -r ~/.config/g1/calibration ~/backups/calibration_$(date +%Y%m%d)
```

### 恢复

```bash
cp -r ~/backups/calibration_<date>/* ~/.config/g1/calibration/
# 重启
```

### 保存

```bash
ros2 service call /rt/calibration/save std_srvs/srv/Trigger
```

## G1 案例库

### CASE-2024-007: 运输后姿态漂移
- **现象**:运输后行走偏向一侧
- **诊断**:IMU 零偏因振动改变
- **处置**:重新执行 IMU + 足力标定

### CASE-2024-014: 更换右膝电机后异常
- **现象**:更换电机后步态不协调
- **诊断**:新电机零点未标定
- **处置**:执行关节零位标定

### CASE-2024-022: 夏季高温导致 IMU 漂移
- **现象**:连续运行 2 小时后姿态偏移
- **诊断**:IMU 温漂
- **处置**:增加预热时间 + 重标定 + 改善散热

## G1 常见问题

### Q1:IMU 标定失败
- 地面不水平 → 用水平仪确认
- 没完全静止 → 排除风、振动
- 温度未稳定 → 多预热

### Q2:足力标定后读数仍异常
- 地面不平 → 换平坦地面
- 姿态不标准 → 调整为标准站姿
- 力传感器故障 → 联系售后

### Q3:标定参数丢失(重启后需要重做)
- 标定结果未正确保存 → 手动 save
- 检查参数文件:`ls ~/.config/g1/calibration/`

## 引用资源

- G1 传感器规格书
- IMU 标定算法文档
- 力传感器技术手册
- G1 维护手册第 5 章
