# RoboOnto 0.9

RoboOnto 0.9 是面向 RoboOnto 3.0 的 **Code-as-Object 目标包工具链**。它把
URDF、SDK、厂商文档以及旧 RoboOnto 目录编译成一个封闭、类型化、可版本化的
`Target PackModule`。

它不负责维护 Duty，也不执行机器人动作。它回答的是：

> 这类机器人是什么、提供哪些能力、有哪些可观测来源、如何绑定到底层接口，
> 以及哪些目标动作可以被具身执行编译器安全引用。

## 在 RoboOnto 3.0 中的位置

```text
URDF / SDK / 文档 / 旧 Ontology
              ↓ Pack Frontend
      PackModule AST 0.9
              ↓ Schema + 静态检查 + 规范化 + 哈希
       *.pack.yaml / *.pack.json
                         ┐
Python Duty Frontend     │
        ↓                │
      Duty IR 3.0        ├→ Execution Compiler + 实时 Context
                         │             ↓
                         ┘       Execution IR 1.0
                                      ↓
                          Codebook / Adapter / 机器人
```

整个体系只有三个正式产物：

| 产物 | 生命周期 | 职责 |
|---|---|---|
| `PackModule 0.9` | 长期版本化 | 机器人事实、能力、观测源、TargetAction 和 Adapter Binding |
| `Duty IR 3.0` | 长期版本化 | Coding Agent 编译出的常驻责任程序 |
| `Execution IR 1.0` | 单次、短生命周期 | Pack、Duty 与实时 Context 链接后的具体执行计划 |

PackModule 不保存实时 Observation、Lease、Window、Budget 或 Ledger。它也不声明
物理世界效果；`TargetAction.world_effect` 固定为 `null`。物理效果、验证与长期维持
属于 Duty/Execution 语言和具身运行时。

## 安装

```sh
git clone https://github.com/zengury/roboonto
cd roboonto
python3 -m pip install -e .
python3 -m pytest -q
```

## 一次性迁移旧 Pack

```sh
roboonto pack migrate \
  robots/agibot_x2 \
  -o robots/agibot_x2/agibot_x2.pack.yaml

roboonto pack validate robots/agibot_x2/agibot_x2.pack.yaml
roboonto pack inspect robots/agibot_x2/agibot_x2.pack.yaml
```

`--strict` 会在任何迁移缺口阻塞执行时返回非零状态：

```sh
roboonto pack migrate robots/agibot_x2 \
  -o /tmp/agibot_x2.pack.yaml \
  --strict
```

旧 `includes`、wildcard、自由 `properties`、字符串 Predicate 和隐式关系只在
`roboonto.compat` 中读取一次。生产运行时只加载规范 PackModule。

## 新前端直接产出 PackModule

URDF：

```sh
roboonto import urdf robot.urdf \
  --robot-id my_robot \
  -o my_robot.pack.yaml
```

SDK：

```sh
roboonto import sdk-code /path/to/sdk/src \
  --robot-id my_robot \
  -o my_robot.sdk.pack.yaml
```

Python：

```python
from pathlib import Path

from roboonto.importers.urdf import URDFImporter
from roboonto.pack import dump_pack

pack = URDFImporter("my_robot", version="0.9.0").run(
    Path("robot.urdf")
)
dump_pack(pack, "my_robot.pack.yaml")
```

Importer 的 `run()` 返回 `PackModule AST`，不再返回旧 YAML 分片。YAML 与 JSON
只是同一 AST 的两种规范序列化。

## 与 RoboOnto 3.0 链接

Duty Compiler 声明稳定的 Pack 依赖；Execution Compiler 用精确版本和摘要完成链接：

```python
from roboonto.pack import PackRequirements, link_pack, load_pack

pack = load_pack("robots/agibot_x2/agibot_x2.pack.yaml")
requirements = PackRequirements(
    pack_id="agibot_x2",
    pack_version="0.9.0",
    content_digest=pack.module.content_digest,
    capabilities=("agibot_x2.cap.tactile_head_events",),
    target_actions=("agibot_x2.action.delete_input_source",),
)
manifest = link_pack(pack, requirements)
```

链接默认拒绝：

- Pack ID、版本或 digest 不一致；
- 未导出的符号；
- 未审定的 Capability；
- 缺少 freshness/evidence contract 的 Observation；
- 因迁移问题被标记为不可执行的 TargetAction。

`PackLinkManifest` 是静态链接结果，不是 Execution IR。具身运行时仍必须检查实时
Context、Authority、Lease、Safety、Freshness、Window、Drift 和 Budget，之后才可
生成 Execution IR。

## X2 迁移状态

当前规范产物保留了旧 X2 Pack 的全部 403 条关系和 22 个动作声明：

| 项目 | 数量 |
|---|---:|
| 旧对象输入 | 256 |
| 规范实体 | 242 |
| Capability | 11 |
| Relation | 403 |
| ObservationSource | 19 |
| TargetAction | 22 |

Capability 与 ServiceRequirement 从普通对象提升为一等模块声明，因此规范实体数
不等于旧对象数。

迁移器不会补造来源中不存在的硬件。旧 Pack 引用了未声明的 speaker 和末端执行器，
所以相关动作会保留但标记 `executable: false`。旧能力输出没有完整的 value type、
freshness、sentinel 和 evidence contract，因此 Observation 会标记
`qualification: contract_required`，不能直接作为 3.0 Duty 的当前事实。

## 兼容边界

0.9 继续兼容旧导入路径：

```python
from roboonto.api.loader import OntologyLoader
from roboonto.api.action_validator import ActionValidator
```

这些符号已经转移到 `roboonto.compat`，只用于旧程序和迁移校验。旧
`ActionValidator` 不再是生产 Runtime Gate，也不会参与 Duty/Execution 编译。

## 文档

- [PackModule 0.9 规范](docs/PACKMODULE_0.9_SPEC.md)
- [RoboOnto 3.0 集成契约](docs/ROBOONTO3_INTEGRATION.md)
- [0.9 一次性迁移指南](docs/MIGRATION_0.9.md)
- [旧 Pack 数据来源与证据](SOURCES.md)

## 许可证

代码与 Schema 使用 Apache-2.0。机器人事实来自公开厂商资料；原始资料版权属于各自
权利人，具体来源见 [SOURCES.md](SOURCES.md)。
