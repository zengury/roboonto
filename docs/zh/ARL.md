# ARL — Agent 就绪度等级

*这台机器人被 AI agent 驱动的就绪程度如何?*

> English version: [../ARL.md](../ARL.md)

ARL 是一个四级指数,由 pack 的可复现就绪检查计算得出。评分规则开源(`roboonto/framework/profiles/`)、工具开源(`roboonto readiness`),任何人都能在本地重算等级——**等级是一个可验证的主张,不是一枚只能选择相信的徽章。**

| 级别 | 名称 | 含义 | 可验证门槛(customer_v1) |
|---|---|---|---|
| **ARL-0** | 可观测 | 机器人已被描述;只读查询可用。 | pack 可加载;`robot` 元数据齐全 |
| **ARL-1** | 可校验 | agent 可以*试运行*调用:动作带前置条件和安全等级。 | 评级 ≥ `alpha`(全部 `must` 规则:loader 零错误、每个动作有 `safety_class` + 标准 invoker、≥1 个 Mode、计算与电源已建模) |
| **ARL-2** | 可安全驱动 | agent 可以按*能力*规划,且每个危险动作都可经由能力到达。 | 评级 ≥ `beta` **且**全部能力规则通过:每个 Capability 有提供方和暴露接口;每个 MOTION/POWER/IRREVERSIBLE 动作映射到 Capability;锚定 ≥2 个外部标准词表 |
| **ARL-3** | 可托管运行 | 审计级溯源;故障语义已建模;可在运行时安全门之下无人值守运行。 | 评级 = `customer-ready`(100% `should`)、来源覆盖 ≥90%、FaultCode/StatusBit 深度、关系图稠密 |

当前自带 pack(用 `roboonto readiness robots/<r> --profile customer_v1` 重算):

| Pack | 评级 | 分数 | ARL |
|---|---|---|---|
| `agibot_x2` | customer-ready | 100.0 | **ARL-3** |
| `unitree_g1_edu` | customer-ready | 100.0 | **ARL-3** |
| `halfcheetah`(仿真) | — | — | 按仿真 profile 评估,不适用 customer_v1 |

## ARL 不是什么

- **不是安全认证。** ARL 度量的是对机器人的*描述*——agent 是否拿到了它需要的事实与约束。它不评价固件的正确性或部署的安全性。
- **不是对 IEEE 1872.x / RoSO 的合规声明。** Pack 通过 `standard_mappings.yaml` 将术语锚定到这些词表,属参考性对齐。
- **不评价 agent。** ARL 只评机器人侧。agent 面对机器人的行为是否规范(先校验再执行、尊重拒绝、该退让时退让而非盲目重试)是另一个需要运行时测试框架的行为学度量——规划中的配套指数 ACL(Agent 合规度)。

## 版本化

标尺会演进:一个 pack 在某版 profile 下得 100 分,在更严格的后继版本下可能失分(我们自己的 G1 pack 在能力规则落地时就经历了这一幕)。因此任何公开等级都必须钉住 **(profile 版本, pack 版本)** 二元组——例如 `ARL-3 @ customer_v1 / g1-pack 0.3.0`。Profile 是仓库内的版本化文件,旧版本永远可通过 git 取回。
