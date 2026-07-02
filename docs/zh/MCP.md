# roboonto MCP — AI Agent 接入指南

roboonto 作为 MCP (Model Context Protocol) 服务运行后，任何支持 MCP 的 AI Agent（Claude Code、Cursor、Continue 等）都可以直接查询机器人 ontology，获得零幻觉的硬件/动作/约束信息。

---

## 快速开始

### 1. 安装 roboonto

```bash
pip install roboonto
```

### 2. 配置 Claude Code

编辑 `~/.claude/mcp.json`:

```json
{
  "mcpServers": {
    "roboonto": {
      "command": "roboonto",
      "args": ["serve", "--mcp"]
    }
  }
}
```

重启 Claude Code 后，Agent 自动获得 roboonto 工具，包括 action 查询、能力菜单、服务需求匹配和 readiness 检查。

### 3. 开始提问

```
你: X2 有哪些传感器？
Claude: [调用 roboonto.query_objects type="Sensor"]
        → X2 有 9 个传感器: IMU×3, RGBD×1, RGB×2, Stereo×1, LiDAR×1, Touch×1

你: set_forward_velocity 的参数范围是多少？
Claude: [调用 roboonto.get_action action="set_forward_velocity"]
        → forward_velocity: float, [-1.8, 1.8] m/s
        → safety_class: MOTION
        → preconditions: 必须在 LOCOMOTION 模式下

你: 电池还剩 10%，能不能让机器人走路？
Claude: [调用 roboonto.check_action action="set_forward_velocity" params={...} state={battery:10}]
        → ❌ 不能。根据 X2 capability_boundary，
           电池 < 15% 时 MOTION 类动作被安全策略拒绝。

你: 这个故障码 agibot_x2.event.pmu.bus48v_overcurrent 什么意思？
Claude: [调用 roboonto.explain id="agibot_x2.event.pmu.bus48v_overcurrent"]
        → 48V 总线过流, severity=error, 影响电源子系统。
           相关联: PMU, PowerSubsystem。

你: G1 的 ontology 现在能打多少分？
Claude: [调用 roboonto.readiness robot="g1"]
        → Grade: alpha, Score: 72.3/100
           差: sensors≥1 (缺), modes≥3 (只有1), actions.affects (3个没填)

你: X2 能不能安全地做底盘运动？应该调用什么？
Claude: [调用 roboonto.agent_affordances capability_kind="navigation"]
        → Locomotion velocity control
        → actions: set_forward_velocity, set_lateral_velocity, set_angular_velocity
        → preconditions: LOCOMOTION/STAND mode, registered input source, static-start thresholds
        → interface: /aima/mc/locomotion/velocity

你: 生成健康报告需要哪些能力？
Claude: [调用 roboonto.explain_service_fit requirement="agibot_x2.req.robot_health_report"]
        → power_diagnostics + body_state_observation
        → 同时返回 PMU topic、IMU/body/DCU streams 和 MCAP 盲区
```

---

## 工具参考

### roboonto.list_robots

列出所有可用的机器人 ontology packs。

```json
// 无参数
// 返回:
{
  "robots": {
    "agibot_x2": {"objects": 250, "actions": 22, "validation_errors": 0},
    "halfcheetah": {"objects": 29, "actions": 3, "validation_errors": 0}
  }
}
```

### roboonto.list_actions

列出指定机器人的所有 agent 可调用动作。

```json
// 参数: robot (可选, 默认 agibot_x2)
{"robot": "agibot_x2"}
// 返回每个动作的: id, description, safety_class, idempotent, parameters
```

### roboonto.get_action

获取某个动作的完整规格。

```json
// 参数: robot (可选), action (必填)
{"robot": "agibot_x2", "action": "set_forward_velocity"}
// 返回: parameters (含约束), preconditions, affects, safety_class, invoker
```

### roboonto.check_action

验证动作在指定参数和状态下能否执行。

```json
// 参数: robot (可选), action (必填), params (可选), state (可选)
{
  "robot": "agibot_x2",
  "action": "set_forward_velocity",
  "params": {"forward_velocity": 0.5},
  "state": {"system.battery_pct": 10, "motion.mc_action": "DAMPING"}
}
// 返回: {ok: false, summary: "..."}
```

### roboonto.query_objects

按类型查询 ontology 对象。

```json
// 参数: robot (可选), type (可选 — Joint, Sensor, Mode, Topic, StatusBit 等)
{"robot": "agibot_x2", "type": "Joint"}
// 不填 type 返回全部对象
```

### roboonto.list_capabilities

查询机器人声明的 Capability，可按能力类型、检测对象、provider、exposed_via 或 ServiceRequirement 过滤。

```json
{"robot": "agibot_x2", "capability_kind": "diagnosis"}
```

### roboonto.agent_affordances

给 agent planner 的首选入口。返回按 Capability 聚合后的可用能力菜单，每个条目包含 provider、actions、interfaces、parameters、preconditions、safety_class、boundaries 和标准映射。

```json
{"robot": "agibot_x2", "capability_kind": "navigation"}
```

### roboonto.explain_service_fit

解释某个 ServiceRequirement 由哪些 Capability 满足，并返回相关 provider / action / topic / service。

```json
{"robot": "agibot_x2", "requirement": "agibot_x2.req.safe_base_motion"}
```

### roboonto.infer_capabilities

从现有 actions 和 invokes_via links 生成可审阅的 `capabilities.yaml` 草稿。它不会替代人工建模，只负责降低迁移成本。

```json
{"robot": "agibot_x2"}
```

### roboonto.explain

解释一个 ontology 实体的完整信息。

```json
// 参数: robot (可选), id (必填)
{"robot": "agibot_x2", "id": "agibot_x2.hw.left_leg.hip_pitch"}
// 返回: type, properties, description, source
// 支持: 硬件、传感器、关节、事件(故障码)、动作、Topic/Service
```

### roboonto.readiness

按 customer profile 评估 ontology 完整度。

```json
// 参数: robot (可选), profile (可选, 默认 customer_v1)
{"robot": "agibot_x2", "profile": "customer_v1"}
// 返回: grade (fail/alpha/beta/customer-ready), score, must/should/may 逐条结果
```

---

## Python API

如果要在代码中直接调用（不通过 MCP）：

```python
from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query, action_for_llm
from roboonto.api.action_validator import ActionValidator
from roboonto.framework.readiness import Readiness

# 加载
loader = OntologyLoader("robots/agibot_x2")
ontology = loader.load()
issues = loader.validate()
print(loader.summary())
# → RoboOnto loaded: agibot_x2
#   objects: 250  actions: 22  links: 324
#   validation: 0 errors, 0 warnings

# 查询对象
q = Query(ontology)
joints = q.objects_of_type("Joint")         # 31 个关节
sensors = q.objects_of_type("Sensor")        # 9 个传感器
modes = q.objects_of_type("Mode")            # 6 种模式
affordances = q.agent_affordance_menu()       # capability-first agent menu

# 查询动作
actions = q.actions_allowed_in_mode("LOCOMOTION")  # 该模式下可用的动作
spec = action_for_llm(ontology.actions_by_id["set_forward_velocity"])
# → 包含完整参数约束、前置条件、安全等级的 dict

# 验证动作
v = ActionValidator(ontology)
result = v.check(
    "set_forward_velocity",
    params={"forward_velocity": 5.0},
    state={"motion.mc_action": "DAMPING"}
)
print(result.summary())
# → invalid: forward_velocity 5.0 exceeds max 1.8;
#   mode DAMPING does not allow MOTION action

# 评级
r = Readiness("robots/agibot_x2", profile="customer_v1")
report = r.run()
print(f"Grade: {report.grade}  Score: {report.score}/100")
# → Grade: customer-ready  Score: 100.0/100
```

---

## 反幻觉机制

roboonto 的核心价值是让 LLM 不再猜测机器人信息。通过 MCP 接口：

| 传统方式 (LLM 猜) | roboonto MCP |
|---|---|
| "X2 大概有 30 个关节" | 精确返回 31 个 Joint，每个带 limit、effort |
| "速度参数可能是 -2 到 2" | 精确返回 [-1.8, 1.8] |
| "在任意模式都能调动作" | 返回 preconditions: 必须在 LOCOMOTION 模式 |
| "这个故障码可能是..." | 精确返回 severity=error, 影响电源子系统 |
| "先列 22 个 action 再猜用途" | 返回 11 个 Capability,每个带 actions/interfaces/boundaries |
| "任务能不能做要靠 prompt 推理" | ServiceRequirement 直接匹配 Capability,同时返回缺口 |

**Agent 的每句话都被 ontology 的客观结构约束。**
