"""RoboOnto 0.9 旧 ActionValidator 的弃用兼容导入。

新 PackModule 的 TargetAction 只供 Execution Compiler/Runtime Gate 使用；
本模块不再定义生产运行时语义。
"""

from ..compat.legacy_action_validator import (
    ActionValidator,
    Failure,
    ValidationReport,
)

__all__ = ["ActionValidator", "Failure", "ValidationReport"]
