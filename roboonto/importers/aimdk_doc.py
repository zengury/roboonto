"""
roboonto.importers.aimdk_doc
============================

从 AgiBot AimDK 文档(.docx)抽取 ontology 分片。

输入:aimdk.docx
输出:ontology YAML 分片(hardware.yaml, interfaces.yaml, actions.yaml, events.yaml)

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
from typing import Iterable
import re


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
    """从 AimDK.docx 产出 roboonto ontology 分片。"""

    def __init__(self, robot_id: str = "agibot_x2"):
        self.robot_id = robot_id

    # ------------- 顶层 -------------
    def run(self, docx_path: Path) -> ImportResult:
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

def main():
    """CLI 入口:`python -m roboonto.importers.aimdk_doc <docx> --out <dir>`"""
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('docx', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--robot-id', default='agibot_x2')
    args = parser.parse_args()

    importer = AimDKImporter(robot_id=args.robot_id)
    result = importer.run(args.docx)

    # TODO: 分片写出到 hardware.yaml / interfaces.yaml / actions.yaml / events.yaml
    # 每个对象/action 带 source,方便后续 review。
    print(f"Extracted {len(result.objects)} objects, {len(result.actions)} actions, "
          f"{len(result.links)} links, {len(result.warnings)} warnings.")


if __name__ == "__main__":
    main()
