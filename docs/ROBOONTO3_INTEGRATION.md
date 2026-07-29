# PackModule 0.9 与 RoboOnto 3.0 集成契约

## 1. 唯一架构主线

```text
Pack Frontend ─→ PackModule 0.9 ───────────────┐
                                               │
Duty Frontend ─→ Authoring AST ─→ Duty IR 3.0 ├→ Execution Compiler
                                               │
StateBus / Lease / Window / Rulebook Context ──┘
                                      ↓
                               Execution IR 1.0
                                      ↓
                        Robot Codebook / Adapter / Robot
```

Pack Compiler 和 Execution Compiler 是两个编译阶段，不是两套语言或两套运行时。

- Pack Compiler 消除来源格式差异，产出稳定 Code-as-Object 模块。
- Duty Compiler 把作者程序编译成可移植责任程序。
- Execution Compiler 在具身端把两者与实时 Context 链接和特化。

Pack 编译通常发生在机器人型号或固件发生变化时；Execution 编译发生在每次获准执行
之前。把前者完全塞进后者会迫使具身端重复解析 URDF、SDK 与旧 YAML，也会让来源
错误直到动作准入时才暴露。

## 2. Duty 声明什么

Duty 不复制机器人事实，只声明依赖：

```python
PackRequirements(
    pack_id="agibot_x2",
    pack_version="0.9.0",
    content_digest="sha256:...",
    capabilities=("agibot_x2.cap.locomotion_velocity_control",),
    observations=("agibot_x2.observation.base_motion",),
    target_actions=("agibot_x2.action.set_forward_velocity",),
)
```

未来 Duty IR 应把这一结构作为静态部署依赖。0.9 的 `PackRequirements` 与
`PackLinkManifest` 已提供可执行参考语义。

## 3. 链接阶段

`link_pack()` 检查：

1. Pack ID、版本、digest 精确匹配；
2. 请求符号存在且已 export；
3. Capability 已 qualified；
4. Observation 具有可部署 freshness/evidence contract；
5. TargetAction 可执行；
6. Binding 和 ResourceSet 可以封闭展开。

产出的 `PackLinkManifest` 固定所用 Pack 的 digest，并展开：

- Capability → provider / interface / target action；
- Observation → source / type / frame / adapter binding；
- TargetAction → parameter / guard / resource set / adapter binding。

它仍是静态链接结果，不含实时授权。

## 4. Execution Compiler 阶段

具身端只有在以下条件同时成立时才生成 Execution IR：

- Duty IR 合法；
- PackLinkManifest 合法；
- 当前 context version 一致；
- Rulebook version 一致；
- Observation 新鲜且非 sentinel；
- Safety Guard 允许；
- Authority 与 Lease 有效；
- Autonomy Window 与 Budget 足以覆盖动作；
- Pack digest 与本地 Codebook 安装版本一致。

Execution IR 应携带：

```text
execution_id
duty_id
context_id
duty_contract_hash
pack_id
pack_version
pack_content_digest
target_action_id
binding
resources
authority
stop_conditions
```

这样 Ledger 可以证明一个具体执行使用了哪一版 Duty 与哪一版机器人目标包。

## 5. Codebook 与 Adapter

`TargetAction` 是 Codebook 的输入符号，`Binding` 是 Adapter 的目标契约。

```text
Duty Action
→ Execution Compiler 选择 TargetAction
→ Codebook 生成 LowLevelPlan
→ Adapter 发送 ROS/DDS/SDK Payload
```

Provider receipt 只能记录 command acceptance。独立 Observation 才能证明 physical
execution 或 verified effect。Pack 的 EvidenceBoundary 可以声明已知观测盲区，但
不能绕过 Duty 的 Verification Contract。

## 6. Cloud 与具身端

Cloud 可以保存 Pack/Duty Artifact、期望状态和版本；它不能声称当前 Lease、物理执行
或已验证效果。

具身端拥有：

- 本地 Pack 安装与 digest；
- 实时 StateBus；
- Safety Gate；
- Lease/Authority；
- Window；
- Execution Compiler；
- Adapter/Verifier；
- Ledger。

Cloud 下发不同 Pack digest 时，具身端必须拒绝或显式重新同步，不能按相同简语码静默
执行不同绑定。

## 7. 与当前 RoboOnto 3.0 仓库的最小集成改动

Duty IR 增加 `pack_requirements`；Execution IR 增加 `pack` 与
`target_action_id`。ReferenceRuntime 在特化 Execution IR 前调用等价于
`link_pack()` 的逻辑，并把 Pack digest 写入 Ledger。

不需要引入第二个 Machine、Lease Manager 或 Ledger。PackModule 只进入既有
Compiler/Runtime 权威路径。
