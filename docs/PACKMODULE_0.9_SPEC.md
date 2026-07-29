# RoboOnto Target PackModule 0.9 规范

## 1. 规范地位

`PackModule` 是 RoboOnto 3.0 的 Code-as-Object 正式程序单元。Python dataclass
模型定义类型化 AST；`packmodule.schema.json` 定义序列化约束；本文件定义静态与
链接语义。

YAML 与 JSON 没有独立语义。两者必须可无损构造同一个 `PackModule`，并产生相同
内容摘要。

## 2. 模块类型

0.9 定义：

```text
Target PackModule
```

它描述一个机器人目标：

- EntityType、Entity 与带签名的 RelationType/Relation；
- Capability 与 ServiceRequirement；
- Observation 与 ObservationSource；
- executor-only TargetAction；
- ResourceSet；
- Adapter Binding；
- EvidenceBoundary；
- Provenance 与 MigrationIssue；
- 显式 Export Surface。

模块不包含 Duty、Policy、Invariant、实时 Observation、Lease、Autonomy Window、
Budget、Drift Estimator、Recovery State 或 Ledger Event。

## 3. 规范化的准确含义

规范化不是 YAML 换 JSON，也不是只跑一次 Schema。规范化是把允许缩写、隐式信息
和不完整约束的来源，编译成一个封闭的类型化目标模块。

规范化必须完成：

1. 每个符号具有稳定、唯一的 canonical ID。
2. 每个 Entity 引用已声明 EntityType。
3. 每条 Relation 引用已声明 RelationType，且 source/target 类型满足签名。
4. Unit 与 Frame 进入 TypeRef，而不是埋在说明文字中。
5. wildcard Resource 被展开为确定成员；不能展开则动作不可执行。
6. Adapter Binding 显式声明 provider、protocol、endpoint、消息类型和参数映射。
7. 字符串 Guard 被解析为 Formula Tree；无法解析则动作不可执行。
8. TargetAction 只表示 executor codebook 入口，`world_effect` 必须为 `null`。
9. ObservationSource 只陈述来源中可证明的实时性、回放性、频率与 Frame。
10. 不得凭空生成 freshness、sentinel、confidence 或 evidence policy。
11. 所有迁移缺口形成可定位、可阻塞的 `MigrationIssue`。
12. 集合排序确定，序列化稳定，并生成覆盖完整静态内容的 SHA-256 digest。

## 4. 类型与值

`TypeRef.kind` 的合法值是：

```text
opaque | bool | int | float | string | enum | entity
| quantity | range | list | record
```

物理类型必须具有 dimension 与 unit。Action 的线速度、角速度参数还必须具有
coordinate frame。`list` 必须声明 item type，`enum` 必须声明非空 values。

`TypedValue` 是封闭递归值：

```text
null | bool | int | float | string | quantity | ref
| range | list<TypedValue> | record<Attribute>
```

因此旧 `properties: {任意键: 任意值}` 不会原样穿透；它会被编译成带名字的
`Attribute(name, TypedValue)`。

## 5. TargetAction

TargetAction 是目标机器人执行词表中的动作，不是 Agent 可见的契约 Action。

静态规则：

- ID 位于 `<module.id>.action.*` 命名空间；
- `visibility == "executor"`；
- `world_effect == null`；
- Binding 必须存在；
- Parameter 名称唯一，TypeRef 合法；
- Guard 是结构化 Formula；
- ResourceSet 必须存在且不含 wildcard；
- ResourceSet 成员必须是已声明 Entity；
- `executable == false` 时必须提供 `blocked_reasons`；
- `executable == true` 时不得保留 `blocked_reasons`。

TargetAction 的发布、Provider 返回或 API Receipt 都不能证明物理效果。Duty
Action 的 `ensures/settles/verify` 由 RoboOnto 3.0 语言定义。

## 6. Observation

`ObservationSource` 描述具体绑定和原始证据通道。`Observation` 描述可被 Duty
程序引用的语义观测契约。

Importer 可以证明 Topic、消息类型、Frame 或标称频率时可以写入。Importer 无法从
来源证明 freshness、sentinel 或 evidence independence 时，必须使用
`qualification: contract_required`，不能猜测默认值。

Execution Compiler 默认拒绝把未审定 Observation 链接为 Duty 的 critical
observation。

## 7. Capability

Capability 必须：

- 至少具有一个已声明 provider；
- 引用已声明 TargetAction、Interface 和 ServiceRequirement；
- 用 `qualification` 表达是否完成类型化审定；
- 把仍是自然语言的边界链接到 `MigrationIssue`。

`review_required` Capability 可以被检查和修订，但默认不能满足生产 Duty 的静态
依赖。

## 8. Formula

Formula 是纯数据树，不能携带 Python callback。0.9 支持：

```text
literal, list, symbol, ref,
boolean(and/or), not, compare, call
```

`call.namespace` 只能是：

```text
intrinsic | ontology_query | observation_query | pack_query
```

迁移器只解析受支持的旧表达式，从不使用 `eval`。不支持的量词或自然语言条件必须
失败关闭。

## 9. Provenance 与冲突

每个来源引用稳定 Provenance ID。Provenance 记录 kind、locator、extractor、
extracted_at 和可选 confidence。

多源冲突不能通过 last-write-wins 隐藏。0.9 迁移器保留来源和迁移问题；未来
Importer 应在构造 AST 时产出显式 conflict/review issue。

## 10. Schema、模型检查与摘要

写入顺序：

```text
PackModule.validate()
→ 计算不含 content_digest 的 canonical JSON
→ SHA-256
→ 写入 module.content_digest
→ JSON Schema 2020-12 验证
→ YAML/JSON 序列化
```

读取顺序：

```text
解析 YAML/JSON
→ JSON Schema 验证
→ 构造 PackModule
→ 模型静态检查
→ 重算并核对 digest
```

任一步失败，Pack 不得进入 Duty/Execution Compiler。

## 11. Export Surface

只有 `exports` 中的 `types`、`capabilities`、`observations` 和
`target_actions` 可以被外部模块引用。内部 Entity 和 Binding 仍可由链接器展开，
但不是稳定的 Duty 作者接口。

## 12. 动态语义

PackModule 自身没有动态状态。加载成功只表示静态目标包有效，不表示：

- 当前机器人在线；
- Provider 接受命令；
- 机器人发生物理运动；
- 世界效果已经验证；
- Duty 条件持续成立。

这些阶段由 Execution Compiler、具身 Runtime Gate、Adapter、Effect Verifier 和
Ledger 分别负责。
