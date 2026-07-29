"""
roboonto.importers.aimdk_doc
============================

从 AgiBot AimDK 文档(.docx)直接编译 Target PackModule。

输入:aimdk.docx
输出:PackModule AST；Canonical YAML/JSON 由 roboonto.pack.dump_pack 序列化

抽取策略
--------

AimDK 文档结构化程度高,分三类信息:

1. **表格类**(确定性强,正则 + 解析即可):
   - §1.2 整机参数
   - §1.3 计算单元规格
   - §1.6 传感器参数
   - §1.7 关节活动范围
   - §5.x 各模块的 topic/service 表
   - §5.4.2 PMU 位状态

2. **msg/srv 定义块**(确定性强,有统一语法):
   例如: `McLocomotionVelocity ros2-msg @ mc/motion/McLocomotionVelocity.msg`
   随后是字段逐行声明。可以用简单状态机识别。

3. **散文类约束**(需要 LLM 辅助抽取):
   - "走跑启动门限 forward_velocity 0.09"
   - "禁止在运控单元 PC1 上部署二开程序"
   - "末端执行器为灵巧手或夹爪时禁止执行平躺站起"

   这类信息抽完后仍然有必要保留原文 anchor,交人工 review。

总原则:**表格和 msg 定义 100% 自动化,散文约束 LLM 辅助 + 人工 confirm**。
每个产出属性都带 source。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import re

from ..pack import dump_pack, pack_digest
from ..pack.builder import attributes_from_mapping, type_ref_from_legacy, typed_value
from ..pack.formula import LegacyFormulaError, parse_legacy_formula
from ..pack.model import (
    Binding,
    Entity,
    EntityType,
    Guard,
    MigrationIssue,
    ModuleHeader,
    PackModule,
    Parameter,
    Provenance,
    Relation,
    RelationType,
    ResourceSet,
    TargetAction,
)


# ==================================================================
# Data Classes(与 meta-schema 对齐的内部表示)
# ==================================================================

@dataclass
class Source:
    type: str                         # "document"
    locator: str                      # "aimdk.docx#§5.1.2"
    extractor: str = "aimdk_doc@0.1"
    extracted_at: str = ""            # ISO timestamp, 由 run() 填入
    confidence: float = 1.0


@dataclass
class ObjectInstance:
    type: str                         # "Joint", "Topic", ...
    id: str
    properties: dict = field(default_factory=dict)
    source: Source | None = None


@dataclass
class ActionInstance:
    type_id: str
    description: str
    invoker: dict
    parameters: list[dict] = field(default_factory=list)
    preconditions: list[dict] = field(default_factory=list)
    param_constraints: dict = field(default_factory=dict)
    affects: list[str] = field(default_factory=list)
    safety_class: str = "INFO"
    source: Source | None = None


@dataclass
class LinkInstance:
    type: str
    source_id: str
    target_id: str
    properties: dict = field(default_factory=dict)


@dataclass
class ImportResult:
    robot_id: str
    objects: list[ObjectInstance] = field(default_factory=list)
    actions: list[ActionInstance] = field(default_factory=list)
    links: list[LinkInstance] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ==================================================================
# 主入口
# ==================================================================

class AimDKImporter:
    """从 AimDK.docx 直接产出 PackModule AST。"""

    def __init__(self, robot_id: str = "agibot_x2", *, version: str = "0.9.0"):
        self.robot_id = robot_id
        self.version = version

    # ------------- 顶层 -------------
    def run(self, docx_path: Path) -> PackModule:
        """抽取文档并直接构造规范 PackModule。"""

        return self._to_pack(self.extract(docx_path), docx_path)

    def extract(self, docx_path: Path) -> ImportResult:
        """主流程:
           1. 解压 .docx 得到原生 XML / 用 pandoc 转 markdown
           2. 按章节切分
           3. 分派给各个 section handler
           4. 合并结果
        """
        sections = self._load_and_split(docx_path)
        result = ImportResult(robot_id=self.robot_id)

        # 确定性抽取(表格类)
        self._extract_compute_units(sections.get("1.3"), result)
        self._extract_joints(sections.get("1.7"), result)
        self._extract_sensors(sections.get("1.6"), result)
        self._extract_modes(sections.get("5.1.1"), result)
        self._extract_locomotion_action(sections.get("5.1.2"), result)
        self._extract_pmu_status_bits(sections.get("5.4.2"), result)
        self._extract_topics_and_services(sections, result)
        self._extract_priority_levels(sections.get("5.2.1"), result)

        # LLM 辅助抽取(散文约束)
        # self._extract_safety_constraints_with_llm(sections, result)

        return result

    def _to_pack(self, result: ImportResult, docx_path: Path) -> PackModule:
        provenance: dict[str, Provenance] = {}

        def provenance_for(source: Source | None) -> tuple[str, ...]:
            locator = source.locator if source else docx_path.name
            identity = f"prov:aimdk:{_slug(locator)}"
            provenance.setdefault(
                identity,
                Provenance(
                    id=identity,
                    kind=source.type if source else "document",
                    locator=locator,
                    extractor=source.extractor if source else "aimdk_doc@0.9",
                    extracted_at=source.extracted_at if source else "",
                    confidence=source.confidence if source else None,
                ),
            )
            return (identity,)

        entities = tuple(
            Entity(
                id=item.id,
                type=item.type,
                attributes=attributes_from_mapping(item.properties),
                provenance=provenance_for(item.source),
            )
            for item in sorted(result.objects, key=lambda value: value.id)
        )
        entity_types = tuple(
            EntityType(type_id, _category(type_id))
            for type_id in sorted({item.type for item in result.objects})
        )
        entity_index = {item.id: item for item in entities}
        action_ids = {
            item.type_id: f"{self.robot_id}.action.{item.type_id}"
            for item in result.actions
        }

        bindings: list[Binding] = []
        resource_sets: list[ResourceSet] = []
        target_actions: list[TargetAction] = []
        issues: list[MigrationIssue] = []
        for action in sorted(result.actions, key=lambda value: value.type_id):
            canonical_id = action_ids[action.type_id]
            binding_id = f"{self.robot_id}.binding.{action.type_id}"
            invoker = action.invoker or {}
            parameters = tuple(
                Parameter(
                    name=str(item["name"]),
                    type=type_ref_from_legacy(item),
                    required=bool(item.get("required", True)),
                    default=(
                        typed_value(item["default"], item)
                        if "default" in item
                        else None
                    ),
                    constraints=tuple(
                        typed_value(value)
                        for value in item.get("constraints") or ()
                    ),
                )
                for item in action.parameters
            )
            bindings.append(
                Binding(
                    id=binding_id,
                    provider=self.robot_id,
                    protocol=str(invoker.get("type") or "unbound"),
                    endpoint=str(
                        invoker.get("name")
                        or invoker.get("name_template")
                        or invoker.get("command")
                        or f"{self.robot_id}.unbound"
                    ),
                    message_type=str(invoker.get("msg_type", "")),
                    request_type=str(invoker.get("srv_type", "")),
                    argument_mapping=tuple(
                        (
                            parameter.name,
                            f"$arguments.{parameter.name}",
                        )
                        for parameter in parameters
                    ),
                    provenance=provenance_for(action.source),
                )
            )

            blocked: list[str] = []
            guards: list[Guard] = []
            for index, raw_guard in enumerate(action.preconditions):
                try:
                    guards.append(
                        Guard(
                            formula=parse_legacy_formula(str(raw_guard["expr"])),
                            code=f"PACK-GUARD-{action.type_id.upper()}-{index + 1}",
                            message=str(raw_guard.get("error", "guard failed")),
                            severity=_severity(str(raw_guard.get("severity", "error"))),
                        )
                    )
                except (KeyError, LegacyFormulaError) as exc:
                    issue_id = f"migration:aimdk:{_slug(action.type_id)}:guard:{index + 1}"
                    issues.append(
                        MigrationIssue(
                            id=issue_id,
                            path=f"target_actions.{canonical_id}.guards[{index}]",
                            kind="untyped_guard",
                            severity="error",
                            message=str(exc),
                            blocks_execution=True,
                            legacy_text=str(raw_guard),
                        )
                    )
                    blocked.append(issue_id)

            members = tuple(sorted(set(action.affects) & set(entity_index)))
            missing = sorted(set(action.affects) - set(entity_index))
            resource_ids: tuple[str, ...] = ()
            if members:
                resource_id = f"{self.robot_id}.resource_set.{action.type_id}"
                resource_sets.append(
                    ResourceSet(resource_id, members, purpose=action.description)
                )
                resource_ids = (resource_id,)
            if missing:
                issue_id = f"migration:aimdk:{_slug(action.type_id)}:resource"
                issues.append(
                    MigrationIssue(
                        id=issue_id,
                        path=f"target_actions.{canonical_id}.resources",
                        kind="unresolved_resource",
                        severity="error",
                        message=f"unknown affected resources: {missing!r}",
                        blocks_execution=True,
                    )
                )
                blocked.append(issue_id)
            if action.param_constraints:
                issue_id = f"migration:aimdk:{_slug(action.type_id)}:constraints"
                issues.append(
                    MigrationIssue(
                        id=issue_id,
                        path=f"target_actions.{canonical_id}.parameter_constraints",
                        kind="untyped_constraint",
                        severity="error",
                        message="document constraint requires typed Parameter constraints",
                        blocks_execution=True,
                        legacy_text=str(action.param_constraints),
                    )
                )
                blocked.append(issue_id)
            target_actions.append(
                TargetAction(
                    id=canonical_id,
                    legacy_id=action.type_id,
                    description=action.description,
                    binding=binding_id,
                    parameters=parameters,
                    guards=tuple(guards),
                    resource_sets=resource_ids,
                    safety_class=action.safety_class,
                    executable=not blocked,
                    blocked_reasons=tuple(blocked),
                    provenance=provenance_for(action.source),
                )
            )

        symbol_types = {item.id: item.type for item in entities}
        symbol_types.update({value: "TargetAction" for value in action_ids.values()})
        relation_rows = []
        for link in result.links:
            source = action_ids.get(link.source_id, link.source_id)
            target = action_ids.get(link.target_id, link.target_id)
            relation_rows.append((link, source, target))
        relation_types = []
        for predicate in sorted({item.type for item in result.links}):
            matching = [
                row for row in relation_rows if row[0].type == predicate
            ]
            relation_types.append(
                RelationType(
                    predicate,
                    tuple(
                        sorted({symbol_types[row[1]] for row in matching})
                    ),
                    tuple(
                        sorted({symbol_types[row[2]] for row in matching})
                    ),
                )
            )
        relations = tuple(
            Relation(
                id=f"{self.robot_id}.relation.{link.type}.{index:04d}",
                predicate=link.type,
                source=source,
                target=target,
                attributes=attributes_from_mapping(link.properties),
            )
            for index, (link, source, target) in enumerate(
                sorted(
                    relation_rows,
                    key=lambda row: (row[0].type, row[1], row[2]),
                ),
                start=1,
            )
        )
        pack = PackModule(
            module=ModuleHeader(
                id=self.robot_id,
                version=self.version,
                target=self.robot_id,
                description=f"由 {docx_path.name} 直接生成的 Target PackModule",
            ),
            types=entity_types,
            relation_types=tuple(relation_types),
            entities=entities,
            relations=relations,
            target_actions=tuple(target_actions),
            resource_sets=tuple(resource_sets),
            bindings=tuple(bindings),
            provenance=tuple(sorted(provenance.values(), key=lambda item: item.id)),
            exports={
                "types": tuple(item.id for item in entity_types),
                "target_actions": tuple(item.id for item in target_actions),
            },
            migration_issues=tuple(issues),
        )
        pack.validate()
        return pack.with_digest(pack_digest(pack))

    # ------------- 文档加载 -------------
    def _load_and_split(self, docx_path: Path) -> dict[str, str]:
        """用 pandoc / extract-text 将 docx 转为结构化 markdown,然后按 §X.Y 切分。
           返回 {section_key: raw_text}。"""
        # TODO: subprocess call to `extract-text` or python-docx
        raise NotImplementedError

    # ------------- Section Handlers -------------

    def _extract_compute_units(self, section_text: str | None, result: ImportResult):
        """§1.3 计算单元 → ComputeUnit objects"""
        if not section_text:
            return
        # 典型表格行:
        # | 处理器       | Jetson Orin NX |
        # | AI 性能      | 157 Tops       |
        # | GPU          | 1024 核 NVIDIA Ampere, 32 Tensor Cores |
        # parse_markdown_table(section_text) -> rows
        # for each compute unit block, create ObjectInstance(type="ComputeUnit", ...)
        raise NotImplementedError

    def _extract_joints(self, section_text: str | None, result: ImportResult):
        """§1.7 关节活动范围 → Joint objects
           典型行:J1 (Shoulder pitch) | -116.5~+176.5° | ...
           需要做:
             - 解析关节名 J1..J7,映射到语义名(Shoulder pitch, Elbow, ...)
             - 角度字符串 '-116.5~+176.5°' → {min, max} in radians
             - 为左右臂分别生成对象(文档只写单臂)
        """
        if not section_text:
            return
        # 单元测试 anchor:确保 J4 的范围 -135~0° 正确转换为 rad
        raise NotImplementedError

    def _extract_sensors(self, section_text: str | None, result: ImportResult):
        """§1.6 传感器参数 → Sensor objects
           每种传感器一张小表,字段不统一,需要 per-kind 解析。"""
        raise NotImplementedError

    def _extract_modes(self, section_text: str | None, result: ImportResult):
        """§5.1.1 运动模式 → Mode objects + transitions 关系(部分)
           表头:模式 | 取值 | 说明 | 使用场景
        """
        raise NotImplementedError

    def _extract_locomotion_action(self, section_text: str | None, result: ImportResult):
        """§5.1.2 走跑控制 → ActionInstance(set_forward_velocity, set_lateral_velocity, set_angular_velocity)
           关键抽取:
             - msg 字段(forward/lateral/angular velocity + source)
             - 启动门限表 → param_constraints
             - "稳定站立模式下执行" → precondition
             - "必须先注册输入源" → precondition
           启动门限是版本敏感的,importer 应打标:
             param_constraints.startup_threshold_version_sensitive = True
        """
        raise NotImplementedError

    def _extract_pmu_status_bits(self, section_text: str | None, result: ImportResult):
        """§5.4.2 PMU 位状态 → StatusBit objects
           两张表:pmu_bool_status (11 位) 和 bms_status_bits (22+ 位)
           对每一位生成 StatusBit,并推断 severity:
             - "过流"/"短路"/"禁止" → error
             - "过压"/"欠压"/"电阻超上限" → warn
             - "开路"/"异常" → warn/error 视情况
        """
        raise NotImplementedError

    def _extract_topics_and_services(self, sections: dict, result: ImportResult):
        """全局扫描所有 §5.x 的表格,抽取 Topic/Service
           识别模式:
             Topic:   name 以 `/aima/` 或 `/agent/` 开头,带 msg_type + QoS + 频率
             Service: name 以 `/aimdk_msgs/srv/` 开头,带 srv_type
           同时抽取 msg/srv 定义块,填充 MsgSchema / SrvSchema
        """
        raise NotImplementedError

    def _extract_priority_levels(self, section_text: str | None, result: ImportResult):
        """§5.2.1 TtsPriorityLevel 表 → PriorityLevel objects"""
        raise NotImplementedError


# ==================================================================
# 辅助工具
# ==================================================================

_DEG_RANGE = re.compile(r'(-?\d+(?:\.\d+)?)\s*[~～]\s*[+]?(-?\d+(?:\.\d+)?)\s*°')

def parse_deg_range(text: str) -> dict | None:
    """'-116.5~+176.5°' -> {min: -2.034, max: 3.080, unit: 'rad'}
       '±146.5°'       -> {min: -2.558, max: 2.558, unit: 'rad'}
    """
    import math
    # ± 写法
    m_sym = re.match(r'±\s*(\d+(?:\.\d+)?)\s*°', text)
    if m_sym:
        v = float(m_sym.group(1))
        return {'min': round(math.radians(-v), 3),
                'max': round(math.radians(v), 3),
                'unit': 'rad'}
    m = _DEG_RANGE.search(text)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return {'min': round(math.radians(lo), 3),
                'max': round(math.radians(hi), 3),
                'unit': 'rad'}
    return None


def parse_markdown_table(text: str) -> list[dict]:
    """把 | h1 | h2 | ... | 的 markdown 表格转成 [{h1:.., h2:..}, ...]。
       skip 分隔行 (|---|---|)。"""
    lines = [l for l in text.splitlines() if l.strip().startswith('|')]
    if len(lines) < 2:
        return []
    def split_row(row: str) -> list[str]:
        return [cell.strip().strip('*') for cell in row.strip('|').split('|')]
    headers = split_row(lines[0])
    rows = []
    for line in lines[2:]:                # skip separator
        cells = split_row(line)
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells)))
    return rows


# ==================================================================
# CLI 入口(roboonto import aimdk ... 的实现基础)
# ==================================================================

def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _severity(value: str) -> str:
    return {"warn": "warning", "fatal": "error"}.get(value.lower(), value.lower())


def _category(type_id: str) -> str:
    if type_id in {"Topic", "Service", "MsgSchema", "SrvSchema"}:
        return "interface"
    if type_id in {"Mode", "PresetMotion"}:
        return "behavior"
    if type_id in {"StatusBit", "TouchEvent", "FaultCode"}:
        return "event"
    return "hardware"


def main():
    """CLI 入口:`python -m roboonto.importers.aimdk_doc <docx> --out <dir>`"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('docx', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--robot-id', default='agibot_x2')
    args = parser.parse_args()

    importer = AimDKImporter(robot_id=args.robot_id)
    pack = importer.run(args.docx)
    dump_pack(pack, args.out)
    print(f"已写入 PackModule: {args.out}；{pack.count()}")


if __name__ == "__main__":
    main()
