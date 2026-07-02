#!/usr/bin/env python3
"""
RoboOnto × AgiBot X2 — 端到端 Demo
==================================

把本轮所有东西串成一个完整闭环:
  1. Loader   加载 143 个对象 + 22 个 action + 60+ link
  2. Query    agent 风格查询(给 LLM 的上下文)
  3. Validator 对候选 action 做 precondition 校验(给 agent 的门禁)

场景:一台灵犀 X2 的 runtime snapshot 显示异常,
      agent 需要决定:
        (a) 诊断:异常的 PMU 状态位代表什么
        (b) 决策:可以执行哪些 Action 来响应
        (c) 执行:对选中的 Action 做 precondition 校验
"""

from pathlib import Path
import json
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query, action_for_llm
from roboonto.api.action_validator import ActionValidator


def banner(text: str):
    print(f"\n{'='*70}\n  {text}\n{'='*70}")


def main():
    # ---------- STAGE 1:加载 ontology ----------
    banner("STAGE 1 · 加载 ontology")
    loader = OntologyLoader(HERE.parent / "robots" / "agibot_x2")
    ontology = loader.load()
    issues = loader.validate()
    c = ontology.count()
    print(f"  加载完毕: {c['objects']} objects, {c['actions']} actions, {c['links']} links")
    print(f"  校验: {sum(1 for i in issues if i.severity=='error')} errors, "
          f"{sum(1 for i in issues if i.severity=='warn')} warnings")

    q = Query(ontology)
    v = ActionValidator(ontology)

    # ---------- STAGE 2:模拟一个 runtime snapshot ----------
    banner("STAGE 2 · 模拟 runtime snapshot (由孪生/agent runtime 注入,不属于 ontology)")
    # 这份 snapshot 完全不属于 roboonto 仓库管理的"应然"知识,
    # 它是"实然"——来自真机当前的 state,或仿真环境,或上报系统。
    snapshot = {
        "timestamp": "2026-04-24T12:00:00Z",
        "mc_action": "LOCOMOTION_DEFAULT",              # 当前处于走跑模式
        "is_moving": False,                             # 但目前静止
        "registered_input_sources": ["rc", "vr", "app_proxy", "interaction", "pnc", "my_agent"],
        "hand_type": {"left": 2, "right": 2},           # 两手都是夹爪
        "native_hand_control_disabled": False,          # 原生运控手部模块仍在运行
        "pmu": {
            "bool_status": 0b00000000_11000000,         # bit 6, 7 置位 → 48V 过流 + 过温
            "battery_voltage": 48.2,
            "battery_temperature": 62.0,
        },
        "bms": {
            "status_bits": 0b0000_0000_0000_1000_0000_0000,   # bit 11 → cell discharge overtemp
        },
        "media_file_on_pc3": lambda path: False,        # 假设没有预置音频
    }
    print(f"  mc_action         = {snapshot['mc_action']}")
    print(f"  is_moving         = {snapshot['is_moving']}")
    print(f"  pmu.bool_status   = 0b{snapshot['pmu']['bool_status']:011b}  (bits 6,7 set)")
    print(f"  bms.status_bits   = 0b{snapshot['bms']['status_bits']:021b}  (bit 11 set)")

    # ---------- STAGE 3:诊断 —— ontology-based fault interpretation ----------
    banner("STAGE 3 · 诊断:将 raw bitmap 通过 ontology 翻译成人类可读 finding")

    def explain_bitmap(field_name: str, value: int) -> list[dict]:
        bits = q.status_bits_on_field(field_name)
        out = []
        for sb in bits:
            idx = (sb.get("properties") or {}).get("bit_index")
            if idx is None:
                continue
            if value & (1 << idx):
                out.append({
                    "id": sb["id"],
                    "bit": idx,
                    "severity": sb["properties"].get("severity"),
                    "semantic": sb["properties"].get("semantic"),
                })
        return out

    findings_pmu = explain_bitmap("pmu_bool_status", snapshot["pmu"]["bool_status"])
    findings_bms = explain_bitmap("bms_status_bits", snapshot["bms"]["status_bits"])
    print(f"  PMU bool_status 活跃位 ({len(findings_pmu)} 条):")
    for f in findings_pmu:
        print(f"    [bit {f['bit']}] [{f['severity'].upper()}] {f['semantic']}")
    print(f"  BMS status_bits 活跃位 ({len(findings_bms)} 条):")
    for f in findings_bms:
        print(f"    [bit {f['bit']}] [{f['severity'].upper()}] {f['semantic']}")

    # 反查 → 这些 event 指向哪些硬件?
    banner("STAGE 4 · 追溯:这些事件指示哪些硬件出了问题?")
    power_events = q.events_indicating("agibot_x2.hw.power")
    active_power_findings = [
        e for e in power_events
        if any(e["id"] == f["id"] for f in findings_pmu + findings_bms)
    ]
    print(f"  指向 agibot_x2.hw.power 的事件: {len(power_events)} 个登记,{len(active_power_findings)} 个此刻活跃")
    for e in active_power_findings:
        print(f"    → {e['id']:55s}  {(e.get('properties') or {}).get('semantic')}")

    # ---------- STAGE 5:可行动作 —— 查询 ----------
    banner("STAGE 5 · 决策:agent 在当前模式下可调用哪些 Action?")
    allowed = q.actions_allowed_in_mode(snapshot["mc_action"])
    print(f"  模式 {snapshot['mc_action']} 下允许的 Action ({len(allowed)} 个):")
    for a in allowed:
        print(f"    - {a['type_id']:30s}  safety={a.get('safety_class'):10s}  {a['description'][:40]}")

    forbidden = q.actions_forbidden_in_mode(snapshot["mc_action"])
    print(f"  模式 {snapshot['mc_action']} 下禁用的 Action ({len(forbidden)} 个):")
    for a in forbidden:
        print(f"    - {a['type_id']:30s}  {a['description'][:40]}")

    # ---------- STAGE 6:候选 Action #1 —— 校验通过 ----------
    banner("STAGE 6 · 候选 1:agent 想让机器人前进 0.5 m/s")
    params1 = {"forward_velocity": 0.5, "source": "my_agent"}
    print(f"  Action  : set_forward_velocity")
    print(f"  Params  : {params1}")
    report1 = v.check("set_forward_velocity", params=params1, state=snapshot)
    print(report1.summary())

    # ---------- STAGE 7:候选 Action #2 —— 启动门限违规 ----------
    banner("STAGE 7 · 候选 2:agent 想慢慢前进 0.05 m/s(静止起步)")
    params2 = {"forward_velocity": 0.05, "source": "my_agent"}
    print(f"  Action  : set_forward_velocity")
    print(f"  Params  : {params2}")
    report2 = v.check("set_forward_velocity", params=params2, state=snapshot)
    print(report2.summary())

    # ---------- STAGE 8:候选 Action #3 —— 未注册输入源 ----------
    banner("STAGE 8 · 候选 3:agent 用未注册的 source 名")
    params3 = {"forward_velocity": 0.5, "source": "unknown_source"}
    print(f"  Action  : set_forward_velocity")
    print(f"  Params  : {params3}")
    report3 = v.check("set_forward_velocity", params=params3, state=snapshot)
    print(report3.summary())

    # ---------- STAGE 9:候选 Action #4 —— 末端执行器控制,触发 fatal 门控 ----------
    banner("STAGE 9 · 候选 4:agent 想直接控制夹爪(但未关闭原生运控)")
    params4 = {
        "left_hand_type": 2, "left_hands": [{"position": 0.5}],
        "right_hand_type": 2, "right_hands": [{"position": 0.5}],
    }
    print(f"  Action  : set_hand_command")
    report4 = v.check("set_hand_command", params=params4, state=snapshot)
    print(report4.summary())

    # ---------- STAGE 10:候选 Action #5 —— 错误关节位置(超限) ----------
    banner("STAGE 10 · 候选 5:关节位置控制,参数类型/枚举检查")
    params5 = {"domain": "legs", "joints": []}      # 'legs' 不在 enum 里,应该是 'leg'
    report5 = v.check("set_joint_position", params=params5, state=snapshot)
    print(report5.summary())

    # ---------- STAGE 11:预设动作 —— 模式不兼容 ----------
    banner("STAGE 11 · 候选 6:agent 想执行挥手(当前走跑模式下禁用)")
    params6 = {"motion": 1002, "area": 2}   # 右手挥手
    report6 = v.check("set_preset_motion", params=params6, state=snapshot)
    print(report6.summary())

    # ---------- STAGE 12:LLM-friendly Action spec ----------
    banner("STAGE 12 · LLM-friendly Action JSON(注入到 agent context)")
    spec = action_for_llm(ontology.actions_by_id["set_forward_velocity"])
    print(json.dumps(spec, indent=2, ensure_ascii=False)[:2000])

    # ---------- 总结 ----------
    banner("DONE")
    passed = sum(1 for r in [report1, report2, report3, report4, report5, report6] if r.ok)
    print(f"  6 个候选 Action 中 {passed} 个通过校验,{6-passed} 个被 ontology 阻止")
    print(f"  没有任何校验逻辑写在应用代码里 —— 全部由 ontology 声明驱动")


if __name__ == "__main__":
    main()
