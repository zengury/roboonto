# 变更记录

## 0.9.0

RoboOnto 从旧 Ontology 目录升级为面向 RoboOnto 3.0 的 Code-as-Object
PackModule 工具链。

主要变化：

- 新增类型化 `PackModule AST` 与 Canonical YAML/JSON 序列化；
- 新增 JSON Schema 2020-12、模型静态检查和 SHA-256 内容摘要；
- 新增旧 Pack 一次性 Migrator；
- X2 的 256 个旧对象、403 条关系和 22 个动作已生成规范 Artifact；
- 新增 executor-only TargetAction、结构化 Binding、ResourceSet、Formula、
  ObservationSource、EvidenceBoundary 与 MigrationIssue；
- URDF、SDK、AimDK 和关节构建前端直接返回 PackModule；
- 新增 RoboOnto 3.0 `PackRequirements` 与 `PackLinkManifest` 参考链接语义；
- 旧 Loader 与 ActionValidator 移到 `roboonto.compat`，保留导入兼容；
- 文档改为中文，并明确 Pack/Duty/Execution 三层边界。

迁移器不会补造来源事实。X2 当前有 5 个 TargetAction 因缺少 speaker 或末端执行器
实体而不可执行；旧 Capability 派生的 Observation 在补全 freshness/evidence
contract 前保持 `contract_required`。
