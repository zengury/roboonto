# URDF ↔ 旧 Ontology 差异报告

- URDF：`x2_ultra.urdf`（机器人名称：`x2t2.5`）
- 旧 Ontology：`robots/agibot_x2/hardware.yaml`（修订前）
- 差异总数：**53** 个关节冲突，**3** 个传感器补充建议

所有冲突均以 **URDF 为准**。URDF 是运动学与动力学的权威来源；AimDK 文档中的
部分数值是文档级近似，可能受到笔误、方向约定或“峰值 120 Nm”汇总规格影响。

## 位置限位冲突

| 关节 | 旧值 | 新值 | URDF 名称 |
|---|---|---|---|
| agibot_x2.hw.left_leg.hip_pitch | [-2.5569, 2.5569] rad | [-2.704, 2.556] rad | left_hip_pitch_joint |
| agibot_x2.hw.left_leg.hip_roll | [-0.2356, 2.906] rad | [-0.235, 2.906] rad | left_hip_roll_joint |
| agibot_x2.hw.left_leg.hip_yaw | [-3.4296, 1.6842] rad | [-1.684, 3.43] rad | left_hip_yaw_joint |
| agibot_x2.hw.left_leg.knee | [0.0, 2.4086] rad | [0.0, 2.4073] rad | left_knee_joint |
| agibot_x2.hw.left_leg.ankle_pitch | [-0.4538, 0.8029] rad | [-0.803, 0.453] rad | left_ankle_pitch_joint |
| agibot_x2.hw.left_leg.ankle_roll | [-0.2618, 0.2618] rad | [-0.262, 0.262] rad | left_ankle_roll_joint |
| agibot_x2.hw.right_leg.hip_pitch | [-2.5569, 2.5569] rad | [-2.704, 2.556] rad | right_hip_pitch_joint |
| agibot_x2.hw.right_leg.hip_roll | [-0.2356, 2.906] rad | [-2.906, 0.235] rad | right_hip_roll_joint |
| agibot_x2.hw.right_leg.hip_yaw | [-3.4296, 1.6842] rad | [-3.43, 1.684] rad | right_hip_yaw_joint |
| agibot_x2.hw.right_leg.knee | [0.0, 2.4086] rad | [0.0, 2.4073] rad | right_knee_joint |
| agibot_x2.hw.right_leg.ankle_pitch | [-0.4538, 0.8029] rad | [-0.803, 0.453] rad | right_ankle_pitch_joint |
| agibot_x2.hw.right_leg.ankle_roll | [-0.2618, 0.2618] rad | [-0.2625, 0.2625] rad | right_ankle_roll_joint |
| agibot_x2.hw.waist.waist_yaw | [-3.4296, 2.2078] rad | [-3.43, 2.382] rad | waist_yaw_joint |
| agibot_x2.hw.waist.waist_pitch | [-0.3142, 0.3142] rad | [-0.314, 0.314] rad | waist_pitch_joint |
| agibot_x2.hw.waist.waist_roll | [-0.4887, 0.4887] rad | [-0.488, 0.488] rad | waist_roll_joint |
| agibot_x2.hw.left_arm.shoulder_pitch | [-2.0333, 3.0805] rad | [-3.08, 2.04] rad | left_shoulder_pitch_joint |
| agibot_x2.hw.left_arm.shoulder_roll | [-0.0611, 3.0456] rad | [-0.061, 2.993] rad | left_shoulder_roll_joint |
| agibot_x2.hw.left_arm.shoulder_yaw | [-2.5569, 2.5569] rad | [-2.556, 2.556] rad | left_shoulder_yaw_joint |
| agibot_x2.hw.left_arm.elbow | [-2.3562, 0.0] rad | [-2.3556, 0.0] rad | left_elbow_joint |
| agibot_x2.hw.left_arm.wrist_yaw | [-2.5569, 2.5569] rad | [-2.556, 2.556] rad | left_wrist_yaw_joint |
| agibot_x2.hw.left_arm.wrist_pitch | [-0.576, 0.576] rad | [-0.558, 0.558] rad | left_wrist_pitch_joint |
| agibot_x2.hw.left_arm.wrist_roll | [-1.5097, 0.7243] rad | [-1.571, 0.724] rad | left_wrist_roll_joint |
| agibot_x2.hw.right_arm.shoulder_pitch | [-2.0333, 3.0805] rad | [-3.08, 2.04] rad | right_shoulder_pitch_joint |
| agibot_x2.hw.right_arm.shoulder_roll | [-0.0611, 3.0456] rad | [-2.993, 0.061] rad | right_shoulder_roll_joint |
| agibot_x2.hw.right_arm.shoulder_yaw | [-2.5569, 2.5569] rad | [-2.556, 2.556] rad | right_shoulder_yaw_joint |
| agibot_x2.hw.right_arm.elbow | [-2.3562, 0.0] rad | [-2.3556, 0.0] rad | right_elbow_joint |
| agibot_x2.hw.right_arm.wrist_yaw | [-2.5569, 2.5569] rad | [-2.556, 2.556] rad | right_wrist_yaw_joint |
| agibot_x2.hw.right_arm.wrist_pitch | [-0.576, 0.576] rad | [-0.558, 0.558] rad | right_wrist_pitch_joint |
| agibot_x2.hw.right_arm.wrist_roll | [-1.5097, 0.7243] rad | [-0.724, 1.571] rad | right_wrist_roll_joint |
| agibot_x2.hw.head.head_yaw | [-0.3491, 0.3491] rad | [-0.366, 0.366] rad | head_yaw_joint |
| agibot_x2.hw.head.head_pitch | [0.0, 0.0] rad | [-0.3838, 0.3838] rad | head_pitch_joint |

## 力矩冲突（旧 Ontology 对所有关节统一填写 120 Nm）

| 关节 | 旧值 | 新值 | URDF 名称 |
|---|---|---|---|
| agibot_x2.hw.left_leg.ankle_pitch | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | left_ankle_pitch_joint |
| agibot_x2.hw.left_leg.ankle_roll | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | left_ankle_roll_joint |
| agibot_x2.hw.right_leg.ankle_pitch | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | right_ankle_pitch_joint |
| agibot_x2.hw.right_leg.ankle_roll | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | right_ankle_roll_joint |
| agibot_x2.hw.waist.waist_pitch | torque_peak=120 Nm (ontology) | effort_limit=48.0 Nm (URDF) | waist_pitch_joint |
| agibot_x2.hw.waist.waist_roll | torque_peak=120 Nm (ontology) | effort_limit=48.0 Nm (URDF) | waist_roll_joint |
| agibot_x2.hw.left_arm.shoulder_pitch | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | left_shoulder_pitch_joint |
| agibot_x2.hw.left_arm.shoulder_roll | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | left_shoulder_roll_joint |
| agibot_x2.hw.left_arm.shoulder_yaw | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | left_shoulder_yaw_joint |
| agibot_x2.hw.left_arm.elbow | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | left_elbow_joint |
| agibot_x2.hw.left_arm.wrist_yaw | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | left_wrist_yaw_joint |
| agibot_x2.hw.left_arm.wrist_pitch | torque_peak=120 Nm (ontology) | effort_limit=4.8 Nm (URDF) | left_wrist_pitch_joint |
| agibot_x2.hw.left_arm.wrist_roll | torque_peak=120 Nm (ontology) | effort_limit=4.8 Nm (URDF) | left_wrist_roll_joint |
| agibot_x2.hw.right_arm.shoulder_pitch | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | right_shoulder_pitch_joint |
| agibot_x2.hw.right_arm.shoulder_roll | torque_peak=120 Nm (ontology) | effort_limit=36.0 Nm (URDF) | right_shoulder_roll_joint |
| agibot_x2.hw.right_arm.shoulder_yaw | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | right_shoulder_yaw_joint |
| agibot_x2.hw.right_arm.elbow | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | right_elbow_joint |
| agibot_x2.hw.right_arm.wrist_yaw | torque_peak=120 Nm (ontology) | effort_limit=24.0 Nm (URDF) | right_wrist_yaw_joint |
| agibot_x2.hw.right_arm.wrist_pitch | torque_peak=120 Nm (ontology) | effort_limit=4.8 Nm (URDF) | right_wrist_pitch_joint |
| agibot_x2.hw.right_arm.wrist_roll | torque_peak=120 Nm (ontology) | effort_limit=4.8 Nm (URDF) | right_wrist_roll_joint |
| agibot_x2.hw.head.head_yaw | torque_peak=120 Nm (ontology) | effort_limit=2.6 Nm (URDF) | head_yaw_joint |
| agibot_x2.hw.head.head_pitch | torque_peak=120 Nm (ontology) | effort_limit=0.6 Nm (URDF) | head_pitch_joint |

## 建议补充的实体

- **缺失传感器**：URDF `imu_in_torso_joint` 声明了传感器 Link，但旧 Ontology 中没有匹配的 Sensor。
  - 父级：`agibot_x2.hw.link.torso_link`
  - 子级：`agibot_x2.hw.link.imu_in_torso_link`
- **缺失传感器**：URDF `imu_in_head_joint` 声明了传感器 Link，但旧 Ontology 中没有匹配的 Sensor。
  - 父级：`agibot_x2.hw.link.head_pitch_link`
  - 子级：`agibot_x2.hw.link.imu_in_head_link`
- **缺失传感器**：URDF `stereo_head_front` 声明了传感器 Link，但旧 Ontology 中没有匹配的 Sensor。
  - 父级：`agibot_x2.hw.link.head_pitch_link`
  - 子级：`agibot_x2.hw.link.stereo_head_front`
