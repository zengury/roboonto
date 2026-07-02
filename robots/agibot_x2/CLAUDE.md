# CLAUDE.md

**这份文件是 RoboOnto Pack 的一部分。** 当一个 LLM(包括 Claude / GPT / 其他)消费这个 Pack 时,这份文件是约束 LLM 行为的指南。

它不描述机器人是谁、有什么性格、依据什么伦理——那些由部署机器人的 runtime 通过 ROBOT.md 提供。这份文件只回答一件事:**作为消费者,如何正确使用 Pack 提供的实然信息**。

---

## 1. 你正在使用什么

你正在使用一份 **RoboOnto Pack**——这台机器人的实然结构档案。

### 1.1 Pack 是开发态认知工具,不是 runtime 控制工具

Pack 服务于:

- 写代码时的 action 用法验证
- 读 log 时的 phenomenon 语义解释
- 分析问题时的结构追溯
- 培训时的客观知识查询

Pack **不**服务于:

- 实时下发指令到机器人(那是 runtime + 控制算法的事,Pack 不在路径上)
- 运行时安全兜底(那是控制系统 + 安全网的事)
- 操作经验、维修方法(那是 RoboSkill 的事)

机器人在跑的时候有控制算法约束指令合法性。Pack 不参与那条路径——Pack 是给开发者、agent、工程师**理解和验证**用的。

### 1.2 Pack 包含

- **客观实体**: 零件(Joint/Link/ComputeUnit)、传感器(Sensor)、模式(Mode)、控制回路(ControlLoop)、输入源(InputSource)、Topic / Service / MsgSchema、Action(可调用动词)、StatusBit / FaultCode / TouchEvent
- **结构关系(已建)**: carried_by(状态由谁承载)、indicates(状态指向哪个硬件)、invocable_via(action 通过谁调用)、requires_mode / allows / grants / forbidden_in(action 与 mode 的关系)、has_parent_link / has_child_link(运动学拓扑)、used_by / hosts(归属计算单元)等
- **Action 约束(已建)**: parameter constraints、preconditions、affects、safety_class

### 1.3 Pack 不包含

- 机器人的"我是谁"(由 ROBOT.md 提供)
- 操作剧本、维修经验、SOP(由 RoboSkill 提供)
- 历史记忆、当下状态(由 runtime 的 Memory / Digital Twin 提供)
- 价值观、伦理约束(由 ROBOT.md 提供)
- **故障根因关系**(当前 Pack 不建模 cause-effect 层,见 § 3.2)

### 1.4 你跟 Pack 的交互方式

Pack 提供三个 API,**只有这三个**:

| API | 用途 | 例子 |
|---|---|---|
| `explain(id)` | "这是什么"——返回某个实体的语义、属性、所属 | "PMU bit 6 是什么" → 返回 bus48v_overcurrent 的 semantic / severity / affects |
| `query(criteria)` | "这个属于什么"——按结构关系追溯 | "/aima/hal/pmu/state 上承载哪些 StatusBit" → 返回 carried_by 反向集合 |
| `validate(action, params, state)` | "这个用法对吗"——检查 action 合法性 | "set_forward_velocity(1.5) 在 DAMPING 模式下" → 返回 invalid |

Pack 是被查询的对象,不主动反馈。所有交互都是 LLM 主动调三个 API 之一,Pack 返回结果。

---

## 2. Validator 的五级响应

`validate` 调用返回五级响应之一。`explain` 和 `query` 在查不到时也返回 unknown / unsupported(不返回猜测)。

| 响应 | 含义 | 你应该如何说话 |
|---|---|---|
| `valid` | Pack 明确支持这条关系/事实 | 直接陈述,作为事实 |
| `invalid` | Pack 明确排除(有反向证据,如 forbidden_in / 参数越界 / 模式错) | 直接否定,引用具体约束 |
| `unsupported` | Pack 没有证据支持,但也没说不可能 | 说"Pack 中没有支持这一判断的结构" |
| `requires_evidence` | 理论上可能,但需要中间链路或额外观测 | 说"这是一个待验证假设,需要以下证据:..." |
| `unknown` | 当前 Pack 覆盖不足以判断 | 说"这个领域当前 Pack 未建模" |

**这五级是认识论坐标,不是二元判断**。你的输出语气必须跟响应等级一致。把 `requires_evidence` 当成 `valid` 输出是幻觉。把 `unknown` 当成 `invalid` 输出是反向幻觉(因为 Pack 没写就断言世界中不可能)。

---

## 3. 反幻觉硬约束 — 当前 Pack 能做什么 / 不能做什么

这是这份文件**最重要的一节**。Pack 的反幻觉能力**不是均匀的**——某些类型的幻觉它能挡,某些它当前挡不住。诚实区分这两类,比任何宏大叙事更重要。

### 3.1 已成立的反幻觉(当前 Pack 真能挡)

✅ **动作合法性反幻觉**
通过 `validate(action, params, state)` 检查。LLM 想说"在 DAMPING 模式下可以调 set_forward_velocity"——Pack 检查 actions.preconditions,返回 invalid("必须处于 LOCOMOTION_DEFAULT 或 STAND_DEFAULT")。**强约束**。

✅ **参数范围反幻觉**
LLM 想说"forward_velocity 设 5 m/s"——Pack 检查 param constraints (range -1.8 ~ 1.8),返回 invalid。**强约束**。

✅ **接口映射反幻觉**
LLM 想说"通过 /xxx/yyy topic 控制走跑"——Pack 用 invocable_via 查不到这个 topic,返回 unsupported。LLM 不能编 topic 名。

✅ **状态位语义反幻觉**
LLM 想说"PMU bit 6 是温度告警"——Pack `explain(agibot_x2.event.pmu.bus48v_overcurrent)` 返回 semantic="48V 总线过流",LLM 不能改语义。

✅ **硬件归属反幻觉**
LLM 想说"orin_power_good 指示 PC1"——Pack 用 indicates 查到指向 pc2,返回 invalid。

✅ **模式约束反幻觉**
LLM 想说"模式 X 下能做 Y"——Pack 用 requires_mode / allows / forbidden_in 查证。

### 3.2 尚未成立的反幻觉(当前 Pack 挡不住,不要假装能挡)

❌ **故障根因反幻觉**
LLM 收到"DNS lookup error",想推"因为 apt-get upgrade 破坏了 dpkg"——**Pack 当前没有 cause-effect 层**,Validator 只能返 unknown。LLM 不能利用 Pack 阻止这种幻觉。

❌ **跨系统因果链反幻觉**
LLM 想说"DCU 启动失败导致 EtherCAT 不稳"——Pack 当前的 link 类型(carried_by / indicates / invocable_via 等)**全部是结构关系,不是因果关系**。Pack 挡不住因果幻觉。

❌ **诊断推理反幻觉**
"为什么 X 发生 / 该查什么 / 怎么修复"——这是 RoboSkill 的领地,不是 Pack。Pack 只能告诉你 X 是什么、X 在哪个 topic 上、X 指示哪块硬件,**不告诉你 X 为什么发生**。

### 3.3 处理 cause-effect 类查询的硬规则

当 LLM 需要回答"为什么"类问题时:

1. 不要假装 Pack 给了答案。
2. 用 explain / query 提取 phenomenon 的客观信息(语义、归属、承载)。
3. 输出格式必须明确标注边界,例如:
   > "Pack 告诉我:这是 48V 总线过流(severity=error,影响 power 子系统,由 /aima/hal/pmu/state 承载)。**Pack 不告诉我为什么过流**——可能原因需要查 RoboSkill 或工程师经验。"
4. 不要在 Pack 边界外给出"听起来合理"的根因推测。

---

## 4. 三个反幻觉硬约束(行为层)

除了 § 3 的能力边界,以下是 LLM 行为层的硬约束:

### 4.1 不为 Pack 没返回的内容编故事

如果 explain / query / validate 返回 unknown 或空集,**不要**靠训练数据补充答案。空集不是邀请你发挥,是边界提示。

### 4.2 不把训练数据里的"机器人常识"当成这台机器人的实然

你训练时见过的"通常机器人这样工作"的知识,**不适用**于具体机器人。每台机器人型号、配置、固件版本不同。说"这台机器人..."时,先调 explain / query 验证。

### 4.3 听到结论时不反向编排证据

当用户给你一个结论时,**不要**反向去 Pack 里找"对得上"的证据。这是事后合理化,不是分析。

正确顺序:
1. 收到 phenomenon
2. 调 explain 取语义,query 取归属
3. 报告 Pack 给出的客观信息
4. 标注 Pack 边界外的部分(根因等)需要其他来源

错误顺序:
1. 收到 conclusion
2. 在 Pack 里找哪些 fact "对得上"
3. 编一个看起来自洽的解释

### 4.4 用 Pack 返回的具体节点名说话

避免"系统不稳定"、"通信异常"、"环境破坏"这种没有 ontology 锚点的形容词。

Pack 返回的是具体节点(`event.pmu.bus48v_overcurrent`、`mode.damping_default`、`action.set_forward_velocity`)。**用这些名字说话**,让你每一句都能追溯到 Pack 节点。

---

## 5. 当用户给出 Pack 之外的信息时

用户(或工程师)经常带来 Pack 里没有的信息——"我刚做了 sudo apt-get upgrade"、"这台机器昨天改过 systemd 配置"。处理方式:

### 5.1 用户反馈是新证据,不是新事实

不要擅自把用户的话当成 Pack 内容。Pack 是 Ingestor 生成的,用户说的话进不了 Pack。

### 5.2 处理路径

- 调 explain / query 看 Pack 对用户提到的现象有什么客观信息
- 如果用户给出根因假设,响应 requires_evidence——告诉用户这条假设要成立需要什么中间证据
- 中间证据来源不是 Pack,可能是 log、工程师经验(RoboSkill)、运行时数据(runtime Memory)

### 5.3 不评价用户反馈真假

用户反馈可能真、可能假、可能部分真。**Pack 不评价用户**,只反映自己的状态。正确输出:"Pack 当前状态如下,用户反馈是这样,二者差距需要 [具体证据] 来弥合。"

---

## 6. 收到 log / 实测数据时

实测 log 是 phenomenon(现象),不是 cause(原因)。

### 6.1 数据是现象,不是原因

一条 log 行只告诉你"在某时刻发生了某事件",**不告诉你为什么**。

### 6.2 同时间不等于因果

两个事件在同一秒、甚至同一微秒发生,**不意味着因果**。它们可能是:

- 同一个上层失败的多层日志输出(同根多枝)
- 独立模块的巧合
- 真有因果,但 Pack 当前不能证明

**先用 query 检查 Pack 是否有结构关系连接两者**(carried_by / indicates / used_by / hosts)。如果没有,**不连因果**。

### 6.3 用 Pack 做 phenomenon mapping,不做 root cause inference

正确流程:

1. 从 log 提取 phenomenon: 比如 `event.pmu.bus48v_overcurrent`
2. 调 explain → 拿到 semantic / severity / affects
3. 调 query(carried_by) → 它在哪个 topic 上(/aima/hal/pmu/state)
4. 调 query(indicates) → 它指示哪个硬件(power 子系统)
5. 报告这些**客观事实**

**不做的事**:

- 不调"caused_by"——Pack 没有这种关系
- 不推"过流是因为线缆短路 / 电机堵转 / 软件 bug"——这超出 Pack 能力
- 不在 phenomenon 之间硬连因果

### 6.4 没查到关系时静默

log 里某个 phenomenon 在 Pack 中找不到对应节点——**静默处理**。不要为了"完整覆盖 log"而硬编关系。

### 6.5 不做事后合理化

最危险的反模式: 用户告诉你结论(比如"这次是升级失败"),你回头看 log,把每一类事件都解释成"对得上升级失败"。

每条 log 的解释**必须独立来自 Pack 查询**,跟用户结论无关。如果 Pack 查询结果跟用户结论一致 → 相互印证;不一致 → **报告差距,不要靠拢用户**。

---

## 7. cause-effect 层是 Pack v0.2 的范畴

如果你看到 Pack 里没有 cause-effect 关系,这不是 bug——是当前版本设计边界。

未来 v0.2 可能新增的 link 类型(候选):
- causes / caused_by
- contributes_to
- mitigated_by
- triggered_by
- observed_as

但**慎建**——如果手写 cause-effect 关系,反幻觉系统会变成"人工幻觉图谱"。v0.2 的 cause-effect 层只会做 5-10 个高频高确定性场景,不会一口气做全诊断。

**当前 Pack 的能力边界,跟产品价值是匹配的**——一个能真实挡住非法 action 的 Pack,比一个号称能诊断一切但没有因果图的 Pack 更值得信任。

---

## 附录: 你跟 Pack 的关系总结

```
你(LLM)                  Pack
---------                ---------
explain(id)     ────→    返回语义 / 属性 / 所属
query(criteria) ────→    返回结构关系结果
validate(action) ───→    返回五级响应
                           ↓
                        (Pack 不主动反馈)
                        (Pack 不评价你的查询)
                        (Pack 不替你解释 cause-effect)
```

Pack 是开发态认知工具:**告诉你 what / where / how-invoked / what's-allowed,不告诉你 why**。

后者由 RoboSkill / Ingestor 长期积累、cause-effect 层逐步建模来回答。

**剩下的,是你的工作**。
