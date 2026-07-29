"""One-time translation of the trusted legacy guard DSL into formula trees.

This module parses; it never evaluates.  Unsupported syntax is rejected so a
migrated target action can be marked non-executable for manual repair.
"""

from __future__ import annotations

import ast
import re

from .model import Formula


class LegacyFormulaError(ValueError):
    pass


_CONTAINS = re.compile(
    r"(?P<left>@?[A-Za-z_][\w.]*)\s+(?P<not>not\s+)?contains\s+"
    r"(?P<right>@?[A-Za-z_][\w.]*)"
)


def parse_legacy_formula(text: str) -> Formula:
    if text.strip() == (
        "all(joint.position within Joint(joint.name).position_limit "
        "for joint in params.joints)"
    ):
        return Formula(
            {
                "kind": "call",
                "namespace": "pack_query",
                "name": "all_joint_positions_within_limits",
                "arguments": [
                    {"kind": "ref", "scope": "parameter", "path": "joints"}
                ],
            }
        )
    if " within " in text or " for " in text:
        raise LegacyFormulaError("quantified/within legacy predicate requires manual typing")
    normalized = _CONTAINS.sub(
        lambda match: (
            f"{'not_contains' if match.group('not') else 'contains'}"
            f"({match.group('left')}, {match.group('right')})"
        ),
        text,
    )
    normalized = normalized.replace("@state.", "state.")
    normalized = normalized.replace("@ontology.", "ontology.")
    normalized = re.sub(r"\btrue\b", "True", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bfalse\b", "False", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\bnull\b", "None", normalized, flags=re.IGNORECASE)
    try:
        root = ast.parse(normalized, mode="eval").body
    except SyntaxError as exc:
        raise LegacyFormulaError(f"cannot parse legacy predicate: {text}") from exc
    return Formula(_convert(root))


def _convert(node: ast.AST):
    if isinstance(node, ast.Constant):
        return {"kind": "literal", "value": node.value}
    if isinstance(node, (ast.List, ast.Tuple)):
        return {"kind": "list", "items": [_convert(item) for item in node.elts]}
    if isinstance(node, ast.Attribute):
        root, path = _attribute_path(node)
        scope = {
            "state": "observation",
            "params": "parameter",
        }.get(root)
        if scope is None:
            return {"kind": "symbol", "path": ".".join((root, *path))}
        return {"kind": "ref", "scope": scope, "path": ".".join(path)}
    if isinstance(node, ast.Name):
        return {"kind": "symbol", "path": node.id}
    if isinstance(node, ast.BoolOp):
        operator = "and" if isinstance(node.op, ast.And) else "or"
        return {
            "kind": "boolean",
            "operator": operator,
            "terms": [_convert(item) for item in node.values],
        }
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return {"kind": "not", "term": _convert(node.operand)}
    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise LegacyFormulaError("chained comparisons require manual typing")
        operators = {
            ast.Eq: "eq",
            ast.NotEq: "ne",
            ast.Lt: "lt",
            ast.LtE: "le",
            ast.Gt: "gt",
            ast.GtE: "ge",
            ast.In: "in",
            ast.NotIn: "not_in",
        }
        op = operators.get(type(node.ops[0]))
        if op is None:
            raise LegacyFormulaError(f"unsupported comparator {type(node.ops[0]).__name__}")
        return {
            "kind": "compare",
            "operator": op,
            "left": _convert(node.left),
            "right": _convert(node.comparators[0]),
        }
    if isinstance(node, ast.Call):
        name = _call_name(node.func)
        namespace = "intrinsic"
        if name.startswith("ontology."):
            namespace = "ontology_query"
            name = name.removeprefix("ontology.")
        elif name.startswith("state."):
            namespace = "observation_query"
            name = name.removeprefix("state.")
        if name in {"contains", "not_contains"}:
            return {
                "kind": "compare",
                "operator": name,
                "left": _convert(node.args[0]),
                "right": _convert(node.args[1]),
            }
        if namespace == "intrinsic" and name not in {"abs"}:
            raise LegacyFormulaError(f"unsupported function {name!r}")
        return {
            "kind": "call",
            "namespace": namespace,
            "name": name,
            "arguments": [_convert(item) for item in node.args],
        }
    raise LegacyFormulaError(f"unsupported syntax node {type(node).__name__}")


def _attribute_path(node: ast.Attribute) -> tuple[str, tuple[str, ...]]:
    parts: list[str] = [node.attr]
    value = node.value
    while isinstance(value, ast.Attribute):
        parts.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name):
        raise LegacyFormulaError("attribute base must be a named scope")
    parts.reverse()
    return value.id, tuple(parts)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        root, path = _attribute_path(node)
        return ".".join((root, *path))
    raise LegacyFormulaError("call target must be a named function")
