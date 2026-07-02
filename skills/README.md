# Skills

机器人运维 skill 库。三层结构。

## 层级

```
skills/
├── universal/       跨所有机器人的工程原理
├── humanoid/        双足共性
├── instances/       具体型号
│   ├── g1/
│   └── x2/
└── _meta/           skill 写作指南 + 故障目录
```

写作纪律见 `_meta/SKILL_LAYERING_GUIDE.md`。

## 谁在用

- `roboonto/diagnostics/`(规划中):诊断引擎读取 skill,生成修复建议
- agent runtime:把 skill 加载到 LLM context,让 agent 在合适场景引用
- 培训材料:工程师 onboarding 参考

## 写新 skill

参考 `_meta/SKILL_LAYERING_SPEC.md`。三步:
1. 先写 instance 层(具体经验)
2. 抽出 universal 层(工程原理)
3. 写 humanoid 层(类共性)

## 引用 ontology

skill 用 `{{ ontology.X }}` 语法引用 ontology 对象。
具体见 `_meta/SKILL_LAYERING_SPEC.md` §字段引用。
