"""
roboonto.compat.legacy_action_validator
================================

把一个候选 Action + 参数 + runtime state 送进来,输出"能不能执行 + 为什么"。

这是 roboonto 从"知识库"跨越到"决策门禁"的关键一步。

设计纪律
-------
1. Ontology 永远是静态的:validator 不改 ontology,也不存状态
2. Runtime state 由调用方注入:调用方(agent runtime / 孪生)负责维护
3. DSL 故意保持简单:初版不引入完整表达式语言,只支持一组固定谓词
4. 所有失败都带人类可读的 error message + 原始表达式,便于 agent 反思

DSL 谓词(v0.1)
---------------
读取:
  @state.X                  runtime 状态字段
  @state.X.Y                嵌套字段
  @ontology.has_object(type, id)
  @ontology.has_preset_motion(motion_value, area_value)
  @ontology.has_link_from(link_type, source, target)
  params.X                  action 调用参数

运算:
  ==  !=  <  <=  >  >=
  in / not in                值在列表中
  contains / not contains    列表/集合包含值
  and / or / not
  abs(x)                     数值绝对值

布尔常量:
  true / false / null
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any
from .legacy_loader import Ontology


# ============================================================
# Result
# ============================================================
@dataclass
class Failure:
    expr: str
    error: str
    severity: str = "error"      # error / warn / fatal

    def __str__(self):
        return f"[{self.severity.upper()}] {self.error}   (expr: {self.expr})"


@dataclass
class ValidationReport:
    action_id: str
    ok: bool
    failures: list[Failure] = field(default_factory=list)
    warnings: list[Failure] = field(default_factory=list)
    evaluated: list[tuple[str, bool]] = field(default_factory=list)

    def summary(self) -> str:
        status = "✓ OK" if self.ok else "✗ BLOCKED"
        lines = [f"{status}  action={self.action_id}"]
        for f in self.failures:
            lines.append(f"  {f}")
        for w in self.warnings:
            lines.append(f"  {w}")
        return "\n".join(lines)


# ============================================================
# Validator
# ============================================================
class ActionValidator:
    """Precondition 求值器。

    用法:
      v = ActionValidator(ontology)
      report = v.check(action_id, params={...}, state={...})
    """
    def __init__(self, ontology: Ontology):
        self.o = ontology

    # --------- Public ---------
    def check(self, action_id: str, params: dict, state: dict) -> ValidationReport:
        act = self.o.actions_by_id.get(action_id)
        if not act:
            return ValidationReport(
                action_id=action_id, ok=False,
                failures=[Failure(expr="", error=f"Action not found in ontology: {action_id}")],
            )

        report = ValidationReport(action_id=action_id, ok=True)

        # 1) 参数结构校验
        self._check_parameters(act, params, report)

        # 2) Precondition 谓词求值
        for pre in act.get("preconditions", []) or []:
            expr = pre.get("expr", "")
            err = pre.get("error", f"precondition failed: {expr}")
            sev = pre.get("severity", "error")
            try:
                val = self._eval(expr, params=params, state=state)
            except Exception as e:
                report.failures.append(Failure(
                    expr=expr, severity="error",
                    error=f"precondition expression could not be evaluated: {e}",
                ))
                report.ok = False
                continue
            report.evaluated.append((expr, bool(val)))
            if not val:
                f = Failure(expr=expr, error=err, severity=sev)
                if sev in ("error", "fatal"):
                    report.failures.append(f)
                    report.ok = False
                else:
                    report.warnings.append(f)

        return report

    # --------- Parameter checks ---------
    def _check_parameters(self, act: dict, params: dict, report: ValidationReport):
        for spec in act.get("parameters", []) or []:
            pname = spec["name"]
            pval = params.get(pname)
            if spec.get("required", False) and pval is None:
                report.failures.append(Failure(
                    expr=f"params.{pname}", severity="error",
                    error=f"required parameter '{pname}' missing",
                ))
                report.ok = False
                continue
            if pval is None:
                continue
            # enum
            if spec.get("type") == "enum":
                values = spec.get("values", [])
                if pval not in values:
                    report.failures.append(Failure(
                        expr=f"params.{pname}", severity="error",
                        error=f"'{pname}'={pval!r} not in enum {values}",
                    ))
                    report.ok = False
            # constraints
            for c in spec.get("constraints", []) or []:
                self._check_constraint(pname, pval, c, report)

    def _check_constraint(self, pname: str, pval: Any, c: dict, report: ValidationReport):
        kind = c.get("type")
        if kind == "range":
            lo, hi = c.get("min"), c.get("max")
            try:
                n = float(pval)
            except (TypeError, ValueError):
                report.failures.append(Failure(
                    expr=f"range({pname})", severity="error",
                    error=f"'{pname}'={pval!r} is not numeric",
                )); report.ok = False
                return
            if lo is not None and n < lo:
                report.failures.append(Failure(
                    expr=f"{pname} >= {lo}", severity="error",
                    error=f"'{pname}'={n} below min {lo}",
                )); report.ok = False
            if hi is not None and n > hi:
                report.failures.append(Failure(
                    expr=f"{pname} <= {hi}", severity="error",
                    error=f"'{pname}'={n} exceeds max {hi}",
                )); report.ok = False
        elif kind == "not_in":
            vals = c.get("values", [])
            if pval in vals:
                report.failures.append(Failure(
                    expr=f"{pname} not in {vals}", severity="error",
                    error=f"'{pname}'={pval!r} is reserved",
                )); report.ok = False

    # ============================================================
    # Expression evaluator —— 极简实现
    # ============================================================
    def _eval(self, expr: str, params: dict, state: dict) -> Any:
        """把表达式求值。安全起见不用 Python eval,而是做最简 tokenize+evaluate。
           只支持本文件顶部 DSL 说明中的谓词和运算符。"""
        # 把 @state.X 和 @ontology.F(args) 替换成 sentinel,然后 eval Python 友好表达式
        # 但 Python eval 对我们不安全,所以手写一个小 evaluator。
        #
        # 实现策略:
        #   1. 把 `@state.a.b.c`     替换为 _s_ab_c_   (去点)
        #   2. 把 `@ontology.F(...)` 替换为 _o_F_(...)
        #   3. 把 `params.x`         替换为 _p_x_
        #   4. 其余运算符标准化
        #   5. 用受限命名空间 eval
        #
        # 这是 v0.1 —— 安全性可接受(输入是受信任的 ontology),
        # 长期应替换为真正的 parser/AST。
        locals_ns: dict[str, Any] = {
            "abs": abs,
            "true": True, "false": False, "null": None, "None": None,
        }

        # 替换 @state / @ontology / params 引用
        expr_py = expr

        # params.X
        for m in re.finditer(r'params\.([a-zA-Z_][a-zA-Z0-9_]*)', expr_py):
            name = m.group(1)
            key = f"__p_{name}__"
            locals_ns[key] = params.get(name)
        expr_py = re.sub(
            r'params\.([a-zA-Z_][a-zA-Z0-9_]*)',
            lambda m: f"__p_{m.group(1)}__", expr_py,
        )

        # @state.A.B.C
        for m in re.finditer(r'@state(\.[a-zA-Z_][\w.]*)', expr_py):
            path = m.group(1).lstrip(".")
            key = f"__s_{path.replace('.', '_')}__"
            locals_ns[key] = self._deep_get(state, path.split("."))
        expr_py = re.sub(
            r'@state(\.[a-zA-Z_][\w.]*)',
            lambda m: f"__s_{m.group(1).lstrip('.').replace('.', '_')}__",
            expr_py,
        )

        # @ontology.F(args)
        expr_py = self._lower_ontology_calls(expr_py, locals_ns)

        # contains → in(反向) — not contains 必须在 contains 之前,防止正则在 "not" 处重新匹配
        expr_py = re.sub(r'(\S+)\s+not contains\s+(\S+)', r'(\2) not in (\1)', expr_py)
        expr_py = re.sub(r'(\S+)\s+contains\s+(\S+)', r'(\2) in (\1)', expr_py)

        # 小写关键字处理
        expr_py = re.sub(r'\btrue\b', 'True', expr_py)
        expr_py = re.sub(r'\bfalse\b', 'False', expr_py)
        expr_py = re.sub(r'\bnull\b', 'None', expr_py)
        expr_py = re.sub(r'\band\b', ' and ', expr_py)
        expr_py = re.sub(r'\bor\b', ' or ', expr_py)
        expr_py = re.sub(r'\bnot\b', ' not ', expr_py)

        # 受限 eval
        return eval(expr_py, {"__builtins__": {}}, locals_ns)

    # --------- ontology.F(...) 的内置函数 ---------
    _ONTOLOGY_FUNCS = ("has_object", "has_preset_motion", "has_link_from", "joint_within_limit")

    def _lower_ontology_calls(self, expr: str, locals_ns: dict) -> str:
        """把 @ontology.F(args) 替换为 __onto_F__(args),并在 locals_ns 里注册函数。"""
        for fname in self._ONTOLOGY_FUNCS:
            locals_ns[f"__onto_{fname}__"] = getattr(self, f"_onto_{fname}")
            expr = re.sub(
                rf'@ontology\.{fname}\s*\(',
                f'__onto_{fname}__(',
                expr,
            )
        # 兜底:未实现的 @ontology.X 报错式替换
        remaining = re.search(r'@ontology\.(\w+)', expr)
        if remaining:
            raise ValueError(f"@ontology.{remaining.group(1)} not implemented in v0.1 evaluator")
        return expr

    # --------- 具体的 @ontology 谓词 ---------
    def _onto_has_object(self, type_name: str, object_id: str) -> bool:
        # 先尝试直接 ID 匹配
        if object_id in self.o.objects_by_id and \
                self.o.objects_by_id[object_id].get("type") == type_name:
            return True
        # 对 Mode 类型,尝试 value→ID 解析 (如 "LOCOMOTION_DEFAULT" → "agibot_x2.mode.locomotion_default")
        resolved = self._resolve_mode_or_id(object_id)
        return resolved in self.o.objects_by_id and \
               self.o.objects_by_id[resolved].get("type") == type_name

    def _onto_has_preset_motion(self, motion_value: int, area_value: int) -> bool:
        for m in self.o.objects_by_type.get("PresetMotion", []):
            p = m.get("properties") or {}
            if p.get("motion_value") == motion_value and p.get("area_value") == area_value:
                return True
        return False

    def _onto_has_link_from(self, link_type: str, source_ref: str, target_ref: str) -> bool:
        # source/target 这里传的往往是 mode_value 而不是 object_id,做一次宽容匹配
        source_obj = self._resolve_mode_or_id(source_ref)
        target_obj = self._resolve_mode_or_id(target_ref)
        for link in self.o.links_by_type.get(link_type, []):
            if link.get("source") == source_obj and link.get("target") == target_obj:
                return True
        return False

    def _onto_joint_within_limit(self, joint_id: str, position_rad: float) -> bool:
        j = self.o.objects_by_id.get(joint_id)
        if not j or j.get("type") != "Joint":
            return False
        pl = (j.get("properties") or {}).get("position_limit") or {}
        lo, hi = pl.get("min"), pl.get("max")
        if lo is None or hi is None:
            return False
        return lo <= position_rad <= hi

    # --------- helpers ---------
    def _resolve_mode_or_id(self, ref: str) -> str:
        """传入可能是 mode_value(如 'LOCOMOTION_DEFAULT')或完整 id,统一返回 id。"""
        if ref in self.o.objects_by_id:
            return ref
        for m in self.o.objects_by_type.get("Mode", []):
            if (m.get("properties") or {}).get("mode_value") == ref:
                return m["id"]
        return ref

    @staticmethod
    def _deep_get(d: dict, path: list[str]) -> Any:
        cur: Any = d
        for p in path:
            if cur is None:
                return None
            if isinstance(cur, dict):
                cur = cur.get(p)
            else:
                try:
                    cur = getattr(cur, p)
                except Exception:
                    return None
        return cur
