# 快速上手

> English version: [../QUICKSTART.md](../QUICKSTART.md)

五分钟内从零到一个 agent 可查询的机器人本体。

## 安装

```sh
git clone https://github.com/zengury/roboonto
cd roboonto
pip install -e .
pip install pyyaml            # 唯一运行时依赖
pytest tests/ -q              # 107 passed
```

## 1 · 校验自带的 pack

仓库自带两台真实机器人,均为 `customer-ready` 评级:

```sh
roboonto validate robots/unitree_g1_edu
roboonto readiness robots/unitree_g1_edu --profile customer_v1
#   Grade:     customer-ready
#   Score:     100.0 / 100
```

## 2 · 查询

```python
from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query

q = Query(OntologyLoader("robots/unitree_g1_edu").load())

# 这台机器人能做什么?(能力层)
for cap in q.list_capabilities():
    print(cap["id"], "—", cap["properties"]["description"])

# agent 做导航所需的一切,一次调用拿全:
menu = q.agent_affordance_menu(capability_kind="navigation")
# → 能力 + 提供方 + 动作(含前置条件与安全等级)
#   + 接口 + 边界声明,已聚合分组

# 哪些动作是危险的?
for a in q.actions_by_safety_class("MOTION"):
    print(a["type_id"], a.get("preconditions"))
```

## 3 · 执行前校验动作

pack 知道**此刻**哪些调用是合法的。注入运行时状态,在任何东西碰到硬件之前拿到带原因的判决:

```python
from roboonto.api.action_validator import ActionValidator

v = ActionValidator(q.o)
report = v.check("set_velocity",
                 params={"velocity": [0.5, 0.0, 0.0], "duration": 2.0},
                 state={"fsm_mode": "PASSIVE"})
print(report.ok)          # False
print(report.failures)    # fsm_mode == WALKRUN — 机器人必须先进入行走模式
```

## 4 · 通过 MCP 提供给 AI agent

```jsonc
// ~/.claude/mcp.json
{
  "mcpServers": {
    "roboonto": { "command": "roboonto", "args": ["serve", "--mcp"] }
  }
}
```

任何 MCP 客户端(Claude Code、Cursor 等)即可获得 `list_actions`、`check_action`、`agent_affordances`、`explain_service_fit`、`readiness` 等工具——零幻觉的机器人事实,每个回答都可溯源到 `source` 定位。详见 [MCP.md](MCP.md)。

## 5 · 为你自己的机器人构建 pack

```sh
cp -r robots/_template robots/my_robot

# 能自动导入的先导入
roboonto import urdf my_robot.urdf -o robots/my_robot
roboonto import sdk-code path/to/sdk -o robots/my_robot

# 起草能力层,然后人工审校
roboonto infer-capabilities robots/my_robot --yaml > robots/my_robot/capabilities.yaml

# 在审计日志下工作(每一步记录到 .build/log.jsonl)
roboonto build init robots/my_robot --operator you
roboonto build run robots/my_robot validate -- roboonto validate robots/my_robot

# 评分
roboonto readiness robots/my_robot --profile customer_v1
```

readiness 报告会精确告诉你缺什么、每条差距怎么修(每条规则带 `hint`)。在让 agent 驱动机器人之前,把 pack 做到 `customer-ready`——各级别含义见 [ARL.md](ARL.md)。

## 接着读

- [SPEC.md](SPEC.md) — 规范(类型、动作、溯源、能力层)
- [ARL.md](ARL.md) — Agent 就绪度等级
- [../CAPABILITY_LAYER.md](../CAPABILITY_LAYER.md) — 为什么是能力而不只是 API
- [../ONTOLOGY_QUALITY_METHODOLOGY.md](../ONTOLOGY_QUALITY_METHODOLOGY.md) — pack 是怎么构建的
