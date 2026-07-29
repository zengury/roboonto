# 旧 MCP 查询接口

MCP 服务当前仍通过 0.9 compatibility 层查询旧 Ontology 目录，适用于知识检索和
迁移审查，不是 RoboOnto 3.0 的生产执行入口。

MCP 查询结果不能替代：

- PackModule 静态链接；
- 具身 Runtime Gate；
- Safety 与 Lease；
- Observation freshness；
- 物理效果验证；
- Ledger 证据。

未来 MCP 若用于 Coding Agent，应读取规范 PackModule 的 export surface，并把 Duty
程序交给正式 Duty Compiler；不得直接调用旧 ActionValidator 驱动机器人。
