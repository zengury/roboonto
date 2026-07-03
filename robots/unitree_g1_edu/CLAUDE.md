# CLAUDE.md — Unitree G1 EDU RoboOnto Pack

**这份文件是 RoboOnto Pack 的一部分。** 当 LLM 消费这个 Pack 时，此文件是行为约束指南。

## 1. Pack 概览

正在使用 Unitree G1 EDU (23-DOF rev_1_0) 的应然结构档案。Pack 告诉 LLM **what / where / how-invoked / what's-allowed**，不告诉 **why**。

三个 API: `explain(id)`, `query(criteria)`, `validate(action, params, state)`

## 2. 已建模内容

- [x] 硬件: Link / Joint / Sensor / ComputeUnit / Power (23 关节, IMU, BMS, Livox Mid-360 LiDAR, RealSense D435 深度相机)
- [x] 接口: DDS Service (sport/arm/audio) · Topic (low_state, imu_state, bms_state, sport_mode_state)
- [x] 行为: Mode (PASSIVE / WALKRUN / user_ctrl) + transitions
- [x] 事件: StatusBit ×108 / FaultCode ×12
- [x] Action: 17 个 agent 可调用动词 (全部带 safety_class)
- [x] Capability: 7 个能力 + 4 个 SoftwareComponent (IEEE 1872.x / RoSO 锚定)
- [x] 关系: provides_capability / exposed_via / transitions_to / indicates

## 3. 未覆盖内容 (诚实声明)

- 无 cause-effect 关系 (agent 无法诊断根因)
- perception 传感器已建 Sensor 语义 (Mid-360 LiDAR / D435 深度相机, mounted_on 链接), 但仍无点云/图像数据流或环境语义建模
- 无环境建模
- 关节历史不落 mcap — 需运行时实时采集 (见 capability_boundary.yaml)

## 4. 反幻觉约束

详见 docs/CLAUDE.md 通用约束。核心: Pack 没说的不编、不把训练常识当应然、不事后合理化。
