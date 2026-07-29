# RoboOnto 0.9 一次性迁移指南

## 1. 迁移目标

保留旧 RoboOnto 中有证据价值的内容：

- X2 硬件、关节、接口和能力事实；
- ROS Topic/Service Binding；
- 参数范围、单位与 Frame；
- 可观测性盲区；
- 来源与证据；
- 动作影响资源；
- 固件限制。

退出规范层的旧机制：

- `includes` 分片语义；
- wildcard；
- 自由结构 `properties`；
- 字符串 Predicate；
- 隐式关系；
- 自然语言安全边界；
- Loader 特殊合并规则；
- 旧 ActionValidator 运行时语义。

## 2. 执行迁移

```sh
roboonto pack migrate \
  robots/agibot_x2 \
  -o robots/agibot_x2/agibot_x2.pack.yaml
```

先检查但允许迁移缺口：

```sh
roboonto pack validate robots/agibot_x2/agibot_x2.pack.yaml
roboonto pack inspect robots/agibot_x2/agibot_x2.pack.yaml --json
```

生产门禁使用：

```sh
roboonto pack migrate robots/agibot_x2 \
  -o /tmp/agibot_x2.pack.yaml \
  --strict
```

`--strict` 失败不表示 Artifact 无法审查，而表示至少一个动作仍不能安全部署。

## 3. X2 迁移结果

| 输入/输出 | 数量 |
|---|---:|
| 旧对象 | 256 |
| 旧关系 | 403 |
| 旧动作 | 22 |
| EntityType | 30 |
| Entity | 242 |
| Capability | 11 |
| ServiceRequirement | 3 |
| Relation | 403 |
| ObservationSource | 19 |
| TargetAction | 22 |

Capability 与 ServiceRequirement 被提升为一等声明，所以 Entity 数减少，但知识
没有被丢弃。

## 4. 已知阻塞项

旧源中动作引用了未声明资源：

- `agibot_x2.hw.speaker`；
- 左右末端执行器实体。

因此 `play_media_file`、`play_tts`、`set_mute`、`set_volume` 和
`set_hand_command` 保留为 TargetAction，但 `executable: false`。迁移器不会为了
让检查通过而补造实体。

修复方式是补充具有真实来源的 Entity、更新 ResourceSet，然后重新生成并审定
Artifact。

## 5. Observation 审定

旧 Capability 的 `produces/detects` 只能证明存在语义输出名称，不能证明：

- 准确 value type；
- half-life 或 max-age；
- sentinel values；
- 最低 freshness score；
- 独立 Evidence Channel。

迁移后这些 Observation 标记为 `contract_required`。在用于 Duty critical
observation 前，需要人工或新 Importer 补全契约并改为 `qualified`。

## 6. 新前端

0.9 后所有维护入口直接产出 PackModule：

```text
URDF Importer ─┐
SDK Importer ──┼→ PackModule AST → Canonical YAML/JSON
AimDK Importer ┤
Python Builder ┘
```

不得再生成 `hardware.yaml + interfaces.yaml + actions.yaml` 供 Loader 二次解释。

## 7. 兼容期

旧入口继续存在：

```text
roboonto.api.loader
roboonto.api.action_validator
roboonto validate/query/check-action
```

它们通过 `roboonto.compat` 工作，并输出弃用提示。新生产链路不得使用旧
ActionValidator 代替 Runtime Gate。

## 8. 退出旧格式

完成以下条件后可删除某机器人目录中的旧分片：

1. PackModule 在 clean checkout 可确定性重建；
2. 所有 blocking MigrationIssue 已处理或明确永久禁用；
3. Capability 与 critical Observation 已 qualified；
4. Manastone 安装并核对 Pack digest；
5. Duty/Execution trace 记录 Pack digest；
6. 回滚包与迁移来源已归档。

在此之前，旧目录作为迁移来源保留，但不是规范生产 Artifact。
