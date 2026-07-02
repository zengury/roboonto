"""
roboonto.importers.sdk_code — SDK 代码抽取

从 SDK 源代码（.msg / .srv 接口定义 + Python 示例代码）抽取 ontology 分片。

输入: SDK 源码目录 (lx2501_3-v0.9.0.4/src/)
输出: 
  - msg_schemas.yaml    MsgSchema 对象（字段名 + 类型 + 约束）
  - srv_schemas.yaml    SrvSchema 对象  
  - topic_defaults.yaml 从代码中推断的 topic→msg_type 默认映射 + QoS 默认值
  - DIFF_vs_doc.yaml    与 aimdk_doc 抽取结果的差异

抽取策略:
  1. .msg 文件 → 字段逐行解析 (field_type field_name = default)
  2. .srv 文件 → Request/Response 分别解析
  3. Python 示例 → 正则匹配 topic 名、QoS、参数默认值、模式约束
  4. 与已有 ontology (来自 aimdk_doc) 做 diff

来源标注: type="sdk_code", 区别于 document/urdf_import/log_observation
"""

from __future__ import annotations
import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class MsgField:
    name: str
    type: str                   # e.g. "float64", "string", "int32", "Header"
    default: str | None = None
    comment: str = ""


@dataclass  
class MsgSchema:
    name: str                   # e.g. "McLocomotionVelocity"
    package: str                # e.g. "aimdk_msgs"
    fields: list[MsgField] = field(default_factory=list)
    source_file: str = ""


@dataclass
class SrvSchema:
    name: str
    package: str
    request_fields: list[MsgField] = field(default_factory=list)
    response_fields: list[MsgField] = field(default_factory=list)
    source_file: str = ""


@dataclass
class TopicInference:
    """从 Python 示例代码推断的 topic 使用信息"""
    topic_name: str
    msg_type: str
    qos_reliability: str = "unknown"     # BEST_EFFORT / RELIABLE
    qos_durability: str = "unknown"      # VOLATILE / TRANSIENT_LOCAL
    example_file: str = ""
    line_number: int = 0


@dataclass
class SdkCodeResult:
    robot_id: str
    msg_schemas: list[MsgSchema] = field(default_factory=list)
    srv_schemas: list[SrvSchema] = field(default_factory=list)
    topic_inferences: list[TopicInference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ===================================================================
# .msg / .srv 文件解析
# ===================================================================

_MSG_FIELD_RE = re.compile(
    r'^\s*'                           # 前导空白
    r'(?P<type>[a-zA-Z_][\w/]*(?:\[\]|[<][^>]*[>])?)\s+'  # 类型 (支持 array[] 和 sequence<>)
    r'(?P<name>[a-zA-Z_]\w*)'         # 字段名
    r'(?:\s*=\s*(?P<default>[^#\n]+))?'  # 可选默认值
    r'\s*(?:#\s*(?P<comment>.*))?'    # 可选注释
    r'\s*$'
)

_SRV_SEPARATOR_RE = re.compile(r'^---\s*$')

class MsgSrvParser:
    """解析 ROS2 .msg 和 .srv 接口定义文件"""

    def parse_msg_file(self, filepath: Path) -> MsgSchema | None:
        """解析单个 .msg 文件 → MsgSchema"""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        # 从路径推断 package name
        package = self._infer_package(filepath)
        name = filepath.stem

        schema = MsgSchema(name=name, package=package, source_file=str(filepath))
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = _MSG_FIELD_RE.match(line)
            if m:
                schema.fields.append(MsgField(
                    name=m.group('name'),
                    type=m.group('type'),
                    default=(m.group('default') or '').strip() or None,
                    comment=(m.group('comment') or '').strip() or "",
                ))
        return schema if schema.fields else None

    def parse_srv_file(self, filepath: Path) -> SrvSchema | None:
        """解析单个 .srv 文件 → SrvSchema"""
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        package = self._infer_package(filepath)
        name = filepath.stem

        schema = SrvSchema(name=name, package=package, source_file=str(filepath))
        lines = content.splitlines()
        
        # 找到 --- 分隔符
        sep_idx = -1
        for i, line in enumerate(lines):
            if _SRV_SEPARATOR_RE.match(line):
                sep_idx = i
                break

        if sep_idx < 0:
            # 无分隔符，整个文件是 request
            for line in lines:
                m = _MSG_FIELD_RE.match(line.strip())
                if m:
                    schema.request_fields.append(MsgField(
                        name=m.group('name'), type=m.group('type'),
                        default=(m.group('default') or '').strip() or None,
                    ))
        else:
            # Request 部分
            for line in lines[:sep_idx]:
                m = _MSG_FIELD_RE.match(line.strip())
                if m:
                    schema.request_fields.append(MsgField(
                        name=m.group('name'), type=m.group('type'),
                        default=(m.group('default') or '').strip() or None,
                    ))
            # Response 部分
            for line in lines[sep_idx + 1:]:
                m = _MSG_FIELD_RE.match(line.strip())
                if m:
                    schema.response_fields.append(MsgField(
                        name=m.group('name'), type=m.group('type'),
                        default=(m.group('default') or '').strip() or None,
                    ))

        return schema if (schema.request_fields or schema.response_fields) else None

    @staticmethod
    def _infer_package(filepath: Path) -> str:
        """从路径推断 package 名: .../aimdk_msgs/interface/robot/common/msg/... → aimdk_msgs"""
        parts = filepath.parts
        for i, part in enumerate(parts):
            if part in ("interface", "msg", "srv"):
                # 向前找到包名 (通常是 interface 的父目录)
                for j in range(i - 1, max(i - 5, 0), -1):
                    if parts[j] in ("aimdk_msgs",):
                        return parts[j]
                return "unknown"
        return "unknown"


# ===================================================================
# Python 示例代码推断
# ===================================================================

# QoS 推断模式
_QOS_PATTERNS = [
    # QoSReliabilityPolicy.BEST_EFFORT
    (re.compile(r'QoSReliabilityPolicy\s*\.\s*BEST_EFFORT'), "BEST_EFFORT"),
    (re.compile(r'QoSReliabilityPolicy\s*\.\s*RELIABLE'), "RELIABLE"),
    (re.compile(r'reliability\s*=\s*QoSReliabilityPolicy\s*\.\s*(\w+)'), "CAPTURE"),
    # QoSDurabilityPolicy
    (re.compile(r'QoSDurabilityPolicy\s*\.\s*TRANSIENT_LOCAL'), "TRANSIENT_LOCAL"),
    (re.compile(r'QoSDurabilityPolicy\s*\.\s*VOLATILE'), "VOLATILE"),
    (re.compile(r'durability\s*=\s*QoSDurabilityPolicy\s*\.\s*(\w+)'), "CAPTURE"),
]

# Topic inference - 全文搜索(create_publisher/create_subscription/create_client 常跨多行)
# 使用 DOTALL 匹配跨行内容
_TOPIC_INFER_RE = re.compile(
    r'(?:create_publisher|create_subscription|create_client)'
    r'\s*\(\s*'
    r'(?P<msg_type>\w+)'
    r'\s*,\s*'
    r"'(?P<topic>/[^']+)'"
    , re.DOTALL
)


class PyExampleParser:
    """从 Python 示例代码推断 topic→msg_type 映射、QoS 默认值"""

    def parse_file(self, filepath: Path) -> list[TopicInference]:
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        inferences: list[TopicInference] = []

        # 全文搜索（create_publisher/create_subscription/create_client 常跨多行）
        for m in _TOPIC_INFER_RE.finditer(content):
            topic_name = m.group('topic')
            msg_type = m.group('msg_type')

            # 计算行号
            line_num = content[:m.start()].count('\n') + 1

            inf = TopicInference(
                topic_name=topic_name,
                msg_type=msg_type,
                example_file=str(filepath),
                line_number=line_num,
            )

            # 在匹配附近查找 QoS 配置
            ctx_start = max(0, m.start() - 300)
            ctx_end = min(len(content), m.end() + 300)
            context = content[ctx_start:ctx_end]
            for pattern, qos_val in _QOS_PATTERNS:
                qm = pattern.search(context)
                if qm:
                    if qos_val == "CAPTURE":
                        qos_val = qm.group(1)
                    if pattern.pattern.startswith('QoSDurability'):
                        inf.qos_durability = qos_val
                    else:
                        inf.qos_reliability = qos_val

            inferences.append(inf)

        return inferences


# ===================================================================
# 主 Importer
# ===================================================================

class SdkCodeImporter:
    """从 SDK 源码抽取 msg/srv schema + topic 使用信息"""

    def __init__(self, robot_id: str = "agibot_x2"):
        self.robot_id = robot_id
        self.msg_parser = MsgSrvParser()
        self.py_parser = PyExampleParser()

    def run(self, sdk_src_dir: Path) -> SdkCodeResult:
        result = SdkCodeResult(robot_id=self.robot_id)

        # 1. 解析 .msg 文件
        msg_dir = sdk_src_dir / "aimdk_msgs" / "interface"
        if msg_dir.exists():
            for msg_file in msg_dir.rglob("*.msg"):
                schema = self.msg_parser.parse_msg_file(msg_file)
                if schema:
                    result.msg_schemas.append(schema)

        # 2. 解析 .srv 文件
        for srv_file in msg_dir.rglob("*.srv") if msg_dir.exists() else []:
            schema = self.msg_parser.parse_srv_file(srv_file)
            if schema:
                result.srv_schemas.append(schema)

        # 3. 解析 Python 示例
        py_examples_dir = sdk_src_dir / "py_examples"
        if py_examples_dir.exists():
            for py_file in py_examples_dir.rglob("*.py"):
                if py_file.name.startswith("__"):
                    continue
                inferences = self.py_parser.parse_file(py_file)
                result.topic_inferences.extend(inferences)

        return result

    def diff_with_doc(self, code_result: SdkCodeResult, doc_topics: set[str]) -> list[dict]:
        """与 aimdk_doc 抽取结果做 diff"""
        diffs = []
        code_topics = set(inf.topic_name for inf in code_result.topic_inferences)

        for topic in code_topics - doc_topics:
            infs = [i for i in code_result.topic_inferences if i.topic_name == topic]
            diffs.append({
                "type": "code_has_doc_missing",
                "topic": topic,
                "msg_type": infs[0].msg_type if infs else "?",
                "source_files": list(set(i.example_file for i in infs)),
                "note": "Topic found in SDK code examples but not in aimdk_doc extraction",
            })

        for topic in doc_topics - code_topics:
            diffs.append({
                "type": "doc_has_code_missing",
                "topic": topic,
                "note": "Topic in aimdk_doc but no code example found using it",
            })

        return diffs


# ===================================================================
# CLI entry
# ===================================================================

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Extract ontology from SDK source code")
    ap.add_argument("sdk_src", type=Path, help="SDK src directory (e.g. lx2501_3-v0.9.0.4/src/)")
    ap.add_argument("--robot-id", default="agibot_x2")
    ap.add_argument("--output", type=Path, help="Output JSON file")
    args = ap.parse_args()

    importer = SdkCodeImporter(robot_id=args.robot_id)
    result = importer.run(args.sdk_src)

    output = {
        "robot_id": result.robot_id,
        "msg_schemas_count": len(result.msg_schemas),
        "srv_schemas_count": len(result.srv_schemas),
        "topic_inferences_count": len(result.topic_inferences),
    }

    if args.output:
        # 完整输出
        full = {
            "msg_schemas": [
                {"name": s.name, "package": s.package, 
                 "fields": [{"name": f.name, "type": f.type} for f in s.fields]}
                for s in result.msg_schemas
            ],
            "srv_schemas": [
                {"name": s.name, "package": s.package,
                 "request_fields": [{"name": f.name, "type": f.type} for f in s.request_fields],
                 "response_fields": [{"name": f.name, "type": f.type} for f in s.response_fields]}
                for s in result.srv_schemas
            ],
            "topic_inferences": [
                {"topic": i.topic_name, "msg_type": i.msg_type,
                 "qos": f"{i.qos_reliability}/{i.qos_durability}",
                 "from": i.example_file}
                for i in result.topic_inferences
            ],
        }
        args.output.write_text(json.dumps(full, ensure_ascii=False, indent=2))
        print(f"Wrote {args.output}")

    print(f"\nSDK Code Extraction Complete:")
    print(f"  .msg schemas: {len(result.msg_schemas)}")
    print(f"  .srv schemas: {len(result.srv_schemas)}")
    print(f"  Topic inferences (from code examples): {len(result.topic_inferences)}")
    print(f"  Warnings: {len(result.warnings)}")


def import_sdk_code(sdk_dir: str, output_dir: str, *, robot_id: str = "imported_robot") -> dict:
    """Public API: extract msg/srv schemas from SDK source into output_dir."""
    import json
    from pathlib import Path

    sdk_p = Path(sdk_dir)
    out_p = Path(output_dir)
    out_p.mkdir(parents=True, exist_ok=True)

    importer = SdkCodeImporter(robot_id=robot_id)
    result = importer.run(sdk_p)

    output = {
        "msg_schemas": [
            {"name": s.name, "package": s.package,
             "fields": [{"name": f.name, "type": f.type} for f in s.fields]}
            for s in result.msg_schemas
        ],
        "srv_schemas": [
            {"name": s.name, "package": s.package,
             "request_fields": [{"name": f.name, "type": f.type} for f in s.request_fields],
             "response_fields": [{"name": f.name, "type": f.type} for f in s.response_fields]}
            for s in result.srv_schemas
        ],
        "topic_inferences": [
            {"topic": i.topic_name, "msg_type": i.msg_type, "from": i.example_file}
            for i in result.topic_inferences
        ],
    }

    (out_p / "sdk_extraction.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    main()
