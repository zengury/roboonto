"""
roboonto.api.query
=====================

给 LLM agent 用的查询 API。设计原则:

  - 查询是"谓词 + 过滤器"式的,而不是 SQL/Cypher
  - 返回的永远是对象实例(dict),agent 可以直接读 properties
  - 所有查询是纯函数,不涉及 runtime 状态
  - 所有查询结果可 JSON 序列化,便于注入到 LLM context

典型用例:
  q = Query(ontology)
  q.objects_of_type("Mode")                       # 所有模式
  q.actions_affecting("agibot_x2.hw.left_arm.elbow")
  q.actions_allowed_in_mode("LOCOMOTION_DEFAULT")
  q.list_capabilities()
  q.find_capabilities(capability_kind="perception", detects="person")
  q.agent_affordance_menu()
  q.explain_service_fit("minibot.req.follow_person")
  q.status_bits_by_severity("error")
  q.actions_by_safety_class("MOTION")
"""

from __future__ import annotations
from typing import Any, Iterable
from .loader import Ontology


class Query:
    def __init__(self, ontology: Ontology):
        self.o = ontology

    # ============================================================
    # 基础:类型/属性过滤
    # ============================================================
    def objects_of_type(self, type_name: str) -> list[dict]:
        return list(self.o.objects_by_type.get(type_name, []))

    def get(self, object_id: str) -> dict | None:
        return self.o.objects_by_id.get(object_id) or self.o.actions_by_id.get(object_id)

    def exists(self, object_id: str) -> bool:
        return (object_id in self.o.objects_by_id) or (object_id in self.o.actions_by_id)

    def where(self, type_name: str, **props) -> list[dict]:
        """查询某类型里 properties 匹配的对象。props 是 key=value 过滤。"""
        out = []
        for obj in self.objects_of_type(type_name):
            p = obj.get("properties") or {}
            if all(p.get(k) == v for k, v in props.items()):
                out.append(obj)
        return out

    # ============================================================
    # Capability / Service 语义层(IEEE/RoSO-inspired)
    # ============================================================
    def list_capabilities(self) -> list[dict]:
        """列出所有 Capability 对象。Capability 描述 what it is / can do。"""
        return self.objects_of_type("Capability")

    def standard_mappings(self) -> dict:
        """返回标准术语映射注册表(IEEE/RoSO/CORA 等)。"""
        return self.o.standard_mappings or {}

    def capability_providers(self, capability_id: str) -> list[dict]:
        """通过 provides_capability 反查提供该能力的组件/传感器/进程。"""
        return [
            self._resolve_entity(link.get("source"))
            for link in self.o.links_by_type.get("provides_capability", [])
            if link.get("target") == capability_id and self._resolve_entity(link.get("source"))
        ]

    def capability_interfaces(self, capability_id: str) -> list[dict]:
        """查询能力通过哪些 Topic/Service/Action/MCP tool 暴露。"""
        return [
            self._resolve_entity(link.get("target"))
            for link in self.o.links_by_type.get("exposed_via", [])
            if link.get("source") == capability_id and self._resolve_entity(link.get("target"))
        ]

    def capability_parameters(self, capability_id: str) -> list[dict]:
        """查询能力的语义参数,如检测区域、最小周期、阈值。"""
        return [
            self.o.objects_by_id[link["target"]]
            for link in self.o.links_by_type.get("has_parameter", [])
            if link.get("source") == capability_id and link.get("target") in self.o.objects_by_id
        ]

    def capability_summary(self, capability_id: str) -> dict | None:
        """压缩单个 Capability,保留 agent 规划和工具选择需要的字段。"""
        cap = self.o.objects_by_id.get(capability_id)
        if not cap or cap.get("type") != "Capability":
            return None
        props = cap.get("properties") or {}
        exposed = self.capability_interfaces(capability_id)
        actions = [e for e in exposed if "type_id" in e]
        interfaces = [e for e in exposed if e.get("type") in {"Topic", "Service"}]
        return {
            "id": cap["id"],
            "name": props.get("name_human", cap["id"]),
            "kind": props.get("capability_kind"),
            "description": props.get("description", ""),
            "detects": props.get("detects", []),
            "produces": props.get("produces", []),
            "consumes": props.get("consumes", []),
            "providers": [
                {"id": p.get("id"), "type": p.get("type"), "properties": p.get("properties", {})}
                for p in self.capability_providers(capability_id)
            ],
            "parameters": [
                {"id": p.get("id"), **(p.get("properties") or {})}
                for p in self.capability_parameters(capability_id)
            ],
            "actions": [
                {
                    "id": a.get("type_id"),
                    "description": a.get("description", ""),
                    "safety_class": a.get("safety_class"),
                    "parameters": a.get("parameters", []),
                    "preconditions": a.get("preconditions", []),
                    "invoker": a.get("invoker"),
                }
                for a in actions
            ],
            "interfaces": [
                {
                    "id": i.get("id"),
                    "type": i.get("type"),
                    "name": (i.get("properties") or {}).get("name"),
                    "schema": (i.get("properties") or {}).get("msg_type")
                    or (i.get("properties") or {}).get("srv_type"),
                    "qos": (i.get("properties") or {}).get("qos"),
                    "frequency_hz": (i.get("properties") or {}).get("frequency_hz"),
                    "cross_unit_safe": (i.get("properties") or {}).get("cross_unit_safe"),
                    "cross_unit_reliable": (i.get("properties") or {}).get("cross_unit_reliable"),
                }
                for i in interfaces
            ],
            "boundaries": props.get("boundaries", []),
            "qos": props.get("qos", {}),
            "standard_mappings": props.get("standard_mappings", []),
        }

    def agent_affordance_menu(
        self,
        *,
        capability_kind: str | None = None,
        include_readonly: bool = True,
    ) -> list[dict]:
        """给 agent 的能力菜单:按 Capability 聚合 action/interface/boundary。

        相比 list_actions,这个输出先回答 "能做什么",再给 "怎么调用"。
        """
        caps = self.find_capabilities(capability_kind=capability_kind)
        menu = []
        for cap in caps:
            summary = self.capability_summary(cap["id"])
            if not summary:
                continue
            if not include_readonly:
                summary["actions"] = [
                    a for a in summary["actions"]
                    if a.get("safety_class") not in {"INFO"}
                ]
            menu.append(summary)
        return menu

    def find_capabilities(
        self,
        *,
        capability_kind: str | None = None,
        detects: str | None = None,
        provider: str | None = None,
        exposed_via: str | None = None,
        requirement: str | None = None,
    ) -> list[dict]:
        """按能力类型、检测语义、provider、接口或服务需求过滤 Capability。

        这是给 agent 的主入口:先找 "能不能做",再看 provider / exposed_via 决定怎么调用。
        """
        caps = self.list_capabilities()
        if capability_kind:
            caps = [
                c for c in caps
                if (c.get("properties") or {}).get("capability_kind") == capability_kind
            ]
        if detects:
            caps = [c for c in caps if self._capability_detects(c["id"], detects)]
        if provider:
            caps = [
                c for c in caps
                if any(p.get("id") == provider for p in self.capability_providers(c["id"]))
            ]
        if exposed_via:
            caps = [
                c for c in caps
                if any(i.get("id") == exposed_via or i.get("type_id") == exposed_via
                       for i in self.capability_interfaces(c["id"]))
            ]
        if requirement:
            caps = [
                c for c in caps
                if self._capability_satisfies_requirement(c["id"], requirement)
            ]
        return caps

    def explain_service_fit(self, requirement: str | dict) -> dict:
        """解释 ServiceRequirement 可以由哪些 Capability 满足。

        requirement 可以是 ServiceRequirement id,也可以是临时 dict:
        {"required_capabilities": ["perception"], "required_outputs": ["pose"]}.
        """
        req_obj = self._resolve_requirement(requirement)
        req_props = req_obj.get("properties") or req_obj
        req_id = req_obj.get("id")
        required_caps = set(req_props.get("required_capabilities") or [])
        required_outputs = set(req_props.get("required_outputs") or [])

        matches = []
        for cap in self.list_capabilities():
            props = cap.get("properties") or {}
            reasons = []
            if req_id and self._capability_satisfies_requirement(cap["id"], req_id):
                reasons.append("linked_by_satisfies_requirement")
            if cap["id"] in required_caps:
                reasons.append("capability_id_required")
            if props.get("capability_kind") in required_caps:
                reasons.append("capability_kind_required")
            outputs = set(props.get("produces") or [])
            if required_outputs and outputs & required_outputs:
                reasons.append("required_output_match")
            if reasons:
                matches.append({
                    "capability": cap,
                    "reasons": reasons,
                    "providers": self.capability_providers(cap["id"]),
                    "parameters": self.capability_parameters(cap["id"]),
                    "exposed_via": self.capability_interfaces(cap["id"]),
                })

        return {
            "requirement": req_obj,
            "required_capabilities": sorted(required_caps),
            "required_outputs": sorted(required_outputs),
            "matches": matches,
        }

    # ============================================================
    # Action 相关(kinetic 层查询)
    # ============================================================
    def all_actions(self) -> list[dict]:
        return list(self.o.actions_by_id.values())

    def actions_by_safety_class(self, safety: str) -> list[dict]:
        return [a for a in self.all_actions() if a.get("safety_class") == safety]

    def actions_affecting(self, target_id: str) -> list[dict]:
        """匹配 affects 字段中直接或 wildcard 包含 target_id 的 Action。"""
        hits = []
        for a in self.all_actions():
            affects = a.get("affects", []) or []
            # 也检查 affects_by_domain(set_joint_position 用)
            if not affects:
                by_dom = a.get("affects_by_domain") or {}
                affects = [x for v in by_dom.values() for x in v]
            if self._wildcard_match_any(target_id, affects):
                hits.append(a)
        return hits

    def actions_allowed_in_mode(self, mode_value: str) -> list[dict]:
        """通过 'allows' 链接 + mode_value 查找。"""
        mode_obj = self._find_mode_by_value(mode_value)
        if not mode_obj:
            return []
        allowed = []
        for link in self.o.links_by_type.get("allows", []):
            if link.get("source") == mode_obj["id"]:
                tgt = link.get("target")
                act = self.o.actions_by_id.get(tgt)
                if act:
                    allowed.append(act)
        return allowed

    def actions_forbidden_in_mode(self, mode_value: str) -> list[dict]:
        mode_obj = self._find_mode_by_value(mode_value)
        if not mode_obj:
            return []
        forb = []
        for link in self.o.links_by_type.get("forbidden_in", []):
            if link.get("target") == mode_obj["id"]:
                src = link.get("source")
                act = self.o.actions_by_id.get(src)
                if act:
                    forb.append(act)
        return forb

    # ============================================================
    # 事件 / 诊断查询
    # ============================================================
    def status_bits_by_severity(self, severity: str) -> list[dict]:
        return [
            s for s in self.objects_of_type("StatusBit")
            if (s.get("properties") or {}).get("severity") == severity
        ]

    def status_bits_on_field(self, field_name: str) -> list[dict]:
        """例如 field_name='pmu_bool_status' 返回该字段所有位。"""
        return [
            s for s in self.objects_of_type("StatusBit")
            if (s.get("properties") or {}).get("carrier_field") == field_name
        ]

    def events_indicating(self, hardware_id: str) -> list[dict]:
        """通过 'indicates' 链接,找出所有指向某硬件的事件。"""
        out = []
        for link in self.o.links_by_type.get("indicates", []):
            if link.get("target") == hardware_id:
                ev = self.o.objects_by_id.get(link.get("source"))
                if ev:
                    out.append(ev)
        return out

    # ============================================================
    # 关节/硬件特定
    # ============================================================
    def joints_in_position_range(self, axis: str | None = None) -> list[dict]:
        out = self.objects_of_type("Joint")
        if axis:
            out = [j for j in out if (j.get("properties") or {}).get("dof_axis") == axis]
        return out

    def joint_by_label(self, j_label: str, body_part: str | None = None) -> list[dict]:
        """按 'J1' / 'J4' 查找关节。body_part 限定 left_arm / right_arm / ..."""
        hits = []
        for j in self.objects_of_type("Joint"):
            p = j.get("properties") or {}
            if p.get("j_label") != j_label:
                continue
            if body_part and body_part not in j["id"]:
                continue
            hits.append(j)
        return hits

    # ============================================================
    # 模式迁移
    # ============================================================
    def allowed_transitions_from(self, mode_value: str) -> list[str]:
        mode_obj = self._find_mode_by_value(mode_value)
        if not mode_obj:
            return []
        return [
            self.o.objects_by_id[l["target"]].get("properties", {}).get("mode_value", l["target"])
            for l in self.o.links_by_type.get("transitions_to", [])
            if l.get("source") == mode_obj["id"] and l.get("target") in self.o.objects_by_id
        ]

    # ============================================================
    # 内部工具
    # ============================================================
    def _find_mode_by_value(self, mode_value: str) -> dict | None:
        for m in self.objects_of_type("Mode"):
            if (m.get("properties") or {}).get("mode_value") == mode_value:
                return m
        return None

    def _resolve_entity(self, entity_id: str | None) -> dict | None:
        if not entity_id:
            return None
        return self.o.objects_by_id.get(entity_id) or self.o.actions_by_id.get(entity_id)

    def _resolve_requirement(self, requirement: str | dict) -> dict:
        if isinstance(requirement, dict):
            return requirement
        obj = self.o.objects_by_id.get(requirement)
        if obj and obj.get("type") == "ServiceRequirement":
            return obj
        return {
            "id": requirement,
            "type": "ServiceRequirement",
            "properties": {"required_capabilities": [requirement]},
        }

    def _capability_detects(self, capability_id: str, target: str) -> bool:
        cap = self.o.objects_by_id.get(capability_id)
        props = (cap or {}).get("properties") or {}
        if target in (props.get("detects") or []):
            return True
        return any(
            link.get("source") == capability_id and link.get("target") == target
            for link in self.o.links_by_type.get("detects", [])
        )

    def _capability_satisfies_requirement(self, capability_id: str, requirement_id: str) -> bool:
        if any(
            link.get("source") == capability_id and link.get("target") == requirement_id
            for link in self.o.links_by_type.get("satisfies_requirement", [])
        ):
            return True
        req = self.o.objects_by_id.get(requirement_id)
        req_props = (req or {}).get("properties") or {}
        required = set(req_props.get("required_capabilities") or [])
        cap = self.o.objects_by_id.get(capability_id)
        cap_props = (cap or {}).get("properties") or {}
        return capability_id in required or cap_props.get("capability_kind") in required

    @staticmethod
    def _wildcard_match_any(target: str, patterns: Iterable[str]) -> bool:
        for pat in patterns:
            if pat == target:
                return True
            if pat.endswith(".*"):
                prefix = pat[:-2]
                if target.startswith(prefix + "."):
                    return True
                # 允许 pattern='a.b.*' 命中 target='a.b.c.d'
                if target == prefix:
                    return True
        return False


# ---------- Quick JSON helper for LLM context injection ----------

def action_for_llm(action: dict) -> dict:
    """把 Action 压缩成 LLM 友好的最小 JSON。"""
    return {
        "id": action.get("type_id"),
        "description": action.get("description", ""),
        "invoker": action.get("invoker"),
        "parameters": action.get("parameters", []),
        "preconditions": [p.get("expr") for p in action.get("preconditions", [])],
        "affects": action.get("affects", []),
        "safety_class": action.get("safety_class"),
    }
