# 旧 Agent-Readiness Level 说明

ARL 是 RoboOnto 0.4 旧 Ontology 的描述完整度评分，只能说明旧 Loader 能否读取
对象、动作、来源和关系。它不是安全认证，也不能证明机器人可以无人值守运行。

RoboOnto 0.9 不把旧 `customer-ready` 或 `ARL-3` 直接映射为可部署 Duty。生产准入
至少还必须满足：

- PackModule Schema、静态语义和 digest 有效；
- 所需 Capability 已 `qualified`；
- critical Observation 具有 freshness、sentinel 和 evidence contract；
- TargetAction 可执行；
- 具身端实时 Safety、Authority、Lease、Window、Drift 和 Budget 门禁通过；
- 物理效果具有独立 Evidence。

旧评分器保留在 compatibility 层，供迁移对照，不作为 RoboOnto 3.0 的运行保证。
