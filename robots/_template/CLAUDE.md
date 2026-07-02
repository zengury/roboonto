# CLAUDE.md — MY_ROBOT RoboOnto Pack

**这份文件是 RoboOnto Pack 的一部分。** 当 LLM 消费这个 Pack 时，此文件是行为约束指南。

## 1. Pack 概览

正在使用 MY_ROBOT 的实然结构档案。Pack 告诉 LLM **what / where / how-invoked / what's-allowed**，不告诉 **why**。

三个 API: `explain(id)`, `query(criteria)`, `validate(action, params, state)`

## 2. 已建模内容

<!-- 完成后手动填写 -->
- [ ] 硬件: Link / Joint / Sensor / ComputeUnit / Power
- [ ] 接口: Topic / Service / MsgSchema
- [ ] 行为: Mode / PresetMotion
- [ ] 事件: StatusBit / FaultCode
- [ ] Action: agent 可调用的动词
- [ ] 关系: carries / indicates / allows / forbids / transitions_to

## 3. 未覆盖内容 (诚实声明)

<!-- 完成后手动更新 -->
- 无 cause-effect 关系 (agent 无法诊断根因)
- 无 perception 建模
- 无环境建模

## 4. 反幻觉约束

详见 docs/CLAUDE.md 通用约束。核心: Pack 没说的不编、不把训练常识当实然、不事后合理化。
