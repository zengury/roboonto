"""RoboOnto 0.9 旧 Ontology Loader 的弃用兼容导入。

规范生产链路应使用 :mod:`roboonto.pack`。此模块只保证 1.0 调用方在
0.9 迁移周期内继续工作，不会参与 Duty/Execution 编译。
"""

from ..compat.legacy_loader import (
    Ontology,
    OntologyLoader,
    ValidationIssue,
    load_and_report,
)

__all__ = ["Ontology", "OntologyLoader", "ValidationIssue", "load_and_report"]
