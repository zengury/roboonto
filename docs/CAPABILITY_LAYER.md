# Capability 层

RoboOnto 0.9 把旧普通对象中的 `Capability` 与 `ServiceRequirement` 提升为
PackModule 一等声明：

```text
Provider Entity
  → Capability
  → TargetAction / Interface
  → ServiceRequirement
```

Capability 描述机器人提供什么，TargetAction/Binding 描述具身执行编译器如何选择
目标入口。二者不能合并：同一能力可能有多个目标动作或接口，同一 TargetAction 也
不能直接承诺 Duty Action 的世界效果。

静态要求：

- Provider、Interface、TargetAction 和 Requirement 引用必须存在；
- Capability 必须带 `qualification`；
- 自然语言安全边界形成 MigrationIssue；
- 只有 `exports.capabilities` 中的符号可被 Duty 依赖；
- `review_required` 默认不能满足生产 Duty 链接。

具体语义见 [PackModule 0.9 规范](PACKMODULE_0.9_SPEC.md)。
