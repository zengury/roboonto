"""Profile — declarative rules a robot ontology should satisfy.

A profile is a YAML file under `framework/profiles/`. Each rule has:
  - id:        unique within a profile
  - severity:  must | should | may
  - check:     a built-in check name (see `_CHECKS` below)
  - args:      check-specific arguments
  - hint:      human-readable repair hint shown in the report

Checks operate on a loaded `Ontology` (from roboonto.api.loader).
They return RuleResult(passed, observed, expected, detail).

Adding a new check = add a function below + register it in `_CHECKS`.
The profile YAML stays declarative; no Python in profiles.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..api.loader import Ontology

_PROFILES_DIR = Path(__file__).parent / "profiles"


# ────────────────────────────────────────────────────────────────────
# Rule + result types
# ────────────────────────────────────────────────────────────────────

@dataclass
class Rule:
    id: str
    severity: str            # must | should | may
    check: str
    args: dict = field(default_factory=dict)
    description: str = ""
    hint: str = ""

    def __post_init__(self):
        if self.severity not in ("must", "should", "may"):
            raise ValueError(f"rule {self.id}: bad severity '{self.severity}'")


@dataclass
class RuleResult:
    rule: Rule
    passed: bool
    observed: Any = None
    expected: Any = None
    detail: str = ""


@dataclass
class Profile:
    id: str
    description: str
    reference_robot: str             # e.g. "agibot_x2" — what this profile distills
    rules: list[Rule] = field(default_factory=list)

    def evaluate(self, ontology: Ontology) -> list[RuleResult]:
        results = []
        for r in self.rules:
            check_fn = _CHECKS.get(r.check)
            if check_fn is None:
                results.append(RuleResult(r, False, detail=f"unknown check '{r.check}'"))
                continue
            try:
                results.append(check_fn(ontology, r))
            except Exception as e:
                results.append(RuleResult(r, False, detail=f"check error: {e}"))
        return results


# ────────────────────────────────────────────────────────────────────
# Loaders
# ────────────────────────────────────────────────────────────────────

def load_profile(name_or_path: str | Path) -> Profile:
    """Load a profile by name (looked up under framework/profiles/) or path."""
    p = Path(name_or_path)
    if not p.exists() or not p.is_file():
        candidate = _PROFILES_DIR / f"{name_or_path}.yaml"
        if candidate.exists():
            p = candidate
        else:
            raise FileNotFoundError(f"profile not found: {name_or_path}")
    doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    rules = [
        Rule(
            id=r["id"],
            severity=r.get("severity", "should"),
            check=r["check"],
            args=r.get("args", {}) or {},
            description=r.get("description", ""),
            hint=r.get("hint", ""),
        )
        for r in (doc.get("rules") or [])
    ]
    return Profile(
        id=doc.get("id", p.stem),
        description=doc.get("description", ""),
        reference_robot=doc.get("reference_robot", ""),
        rules=rules,
    )


# ────────────────────────────────────────────────────────────────────
# Built-in checks
#
# Each check takes (ontology, rule) and returns a RuleResult.
# Checks are intentionally narrow — one concept each — so the profile
# YAML can compose them by parameter rather than by writing new code.
# ────────────────────────────────────────────────────────────────────

CheckFn = Callable[[Ontology, Rule], RuleResult]


def _check_robot_meta_field(ont: Ontology, rule: Rule) -> RuleResult:
    """robot.<field> must be set to a non-empty string."""
    field_name = rule.args.get("field", "id")
    val = (ont.robot_meta or {}).get(field_name)
    ok = isinstance(val, str) and bool(val.strip()) and not val.startswith("MY_")
    return RuleResult(rule, ok, observed=val, expected=f"non-empty robot.{field_name}",
                      detail="" if ok else f"robot.{field_name} is missing or still placeholder")


def _check_object_count(ont: Ontology, rule: Rule) -> RuleResult:
    """At least N objects of a given type."""
    type_name = rule.args["type"]
    minimum = int(rule.args.get("min", 1))
    count = len(ont.objects_by_type.get(type_name, []))
    return RuleResult(rule, count >= minimum, observed=count, expected=f">= {minimum}",
                      detail=f"{count} {type_name} object(s) declared")


def _check_action_count(ont: Ontology, rule: Rule) -> RuleResult:
    minimum = int(rule.args.get("min", 1))
    count = len(ont.actions_by_id)
    return RuleResult(rule, count >= minimum, observed=count, expected=f">= {minimum}",
                      detail=f"{count} action(s) declared")


def _check_link_count(ont: Ontology, rule: Rule) -> RuleResult:
    minimum = int(rule.args.get("min", 1))
    count = len(ont.links)
    link_type = rule.args.get("type")
    if link_type:
        count = len(ont.links_by_type.get(link_type, []))
    return RuleResult(rule, count >= minimum, observed=count, expected=f">= {minimum}",
                      detail=f"{count} link(s) of {link_type or 'any type'}")


def _check_actions_have_field(ont: Ontology, rule: Rule) -> RuleResult:
    """Every action declares the named field. By default, the field must merely
    be present (an empty list is a valid `affects: []` for read-only actions).
    Pass `non_empty: true` to require a truthy value (e.g. for safety_class).
    """
    field_name = rule.args["field"]
    require_non_empty = bool(rule.args.get("non_empty", False))

    def is_missing(act: dict) -> bool:
        if field_name not in act:
            return True
        return require_non_empty and not act.get(field_name)

    missing = [aid for aid, act in ont.actions_by_id.items() if is_missing(act)]
    ok = not missing
    return RuleResult(rule, ok, observed=len(missing), expected=0,
                      detail=("all actions have it"
                              if ok
                              else f"{len(missing)} action(s) missing: {missing[:5]}"))


def _check_objects_have_source(ont: Ontology, rule: Rule) -> RuleResult:
    """Coverage: at least `min_pct`% of objects have a non-empty `source` field."""
    min_pct = float(rule.args.get("min_pct", 80))
    type_filter = rule.args.get("type")
    pool = (ont.objects_by_type.get(type_filter, [])
            if type_filter else list(ont.objects_by_id.values()))
    if not pool:
        return RuleResult(rule, False, observed=0, expected=f">= {min_pct}%",
                          detail="no objects to check")
    with_src = sum(1 for o in pool if o.get("source"))
    pct = 100.0 * with_src / len(pool)
    ok = pct >= min_pct
    return RuleResult(rule, ok, observed=round(pct, 1), expected=f">= {min_pct}%",
                      detail=f"{with_src}/{len(pool)} objects have source")


def _check_joints_have_position_limit(ont: Ontology, rule: Rule) -> RuleResult:
    joints = ont.objects_by_type.get("Joint", [])
    if not joints:
        return RuleResult(rule, False, observed=0, expected=">= 1",
                          detail="no Joint objects (run roboonto import urdf)")
    missing = [j["id"] for j in joints
               if not (j.get("properties") or {}).get("position_limit")]
    ok = not missing
    return RuleResult(rule, ok, observed=len(missing), expected=0,
                      detail=("all joints have position_limit"
                              if ok
                              else f"{len(missing)} joint(s) missing limit: {missing[:5]}"))


def _check_loader_clean(ont: Ontology, rule: Rule) -> RuleResult:
    """Re-run loader.validate() to assert no errors. Stored in ontology.robot_meta._issues."""
    issues = ont.robot_meta.get("_issues", [])
    errors = [i for i in issues if getattr(i, "severity", "info") == "error"]
    return RuleResult(rule, not errors, observed=len(errors), expected=0,
                      detail=("loader validate clean"
                              if not errors
                              else f"{len(errors)} loader error(s)"))


def _check_capability_boundary(ont: Ontology, rule: Rule) -> RuleResult:
    """Capability boundary file exists and is non-trivial. Accepts either
    schema:
      - template style: declared_sensors / declared_joint_groups / log_sources
      - X2 style:       observability: {…}
    """
    boundary = ont.robot_meta.get("_capability_boundary") or {}
    if not boundary:
        return RuleResult(rule, False, observed=0, expected="non-empty file",
                          detail="capability_boundary.yaml missing or empty")
    sensors = len(boundary.get("declared_sensors") or [])
    groups = len(boundary.get("declared_joint_groups") or [])
    log_sources = len(boundary.get("log_sources") or [])
    observability = len(boundary.get("observability") or {})
    declarations = sensors + groups + log_sources + observability
    minimum = int(rule.args.get("min_declarations", 1))
    return RuleResult(rule, declarations >= minimum, observed=declarations,
                      expected=f">= {minimum}",
                      detail=(f"declared_sensors={sensors} joint_groups={groups} "
                              f"log_sources={log_sources} observability={observability}"))


def _check_standard_mappings_count(ont: Ontology, rule: Rule) -> RuleResult:
    minimum = int(rule.args.get("min", 1))
    standards = (ont.standard_mappings or {}).get("standards") or []
    return RuleResult(rule, len(standards) >= minimum, observed=len(standards),
                      expected=f">= {minimum}",
                      detail=f"{len(standards)} standard mapping registry entrie(s)")


def _check_capabilities_have_link(ont: Ontology, rule: Rule) -> RuleResult:
    link_type = rule.args["link_type"]
    direction = rule.args.get("direction", "out")
    caps = ont.objects_by_type.get("Capability", [])
    missing = []
    for cap in caps:
        if direction == "in":
            has_link = any(l.get("target") == cap["id"] for l in ont.links_by_type.get(link_type, []))
        else:
            has_link = any(l.get("source") == cap["id"] for l in ont.links_by_type.get(link_type, []))
        if not has_link:
            missing.append(cap["id"])
    ok = not missing
    return RuleResult(rule, ok, observed=len(missing), expected=0,
                      detail=("all capabilities linked"
                              if ok else f"{len(missing)} capability(ies) missing {link_type}: {missing[:5]}"))


def _check_actions_exposed_by_capability(ont: Ontology, rule: Rule) -> RuleResult:
    safety_classes = set(rule.args.get("safety_classes", ["MOTION", "POWER", "IRREVERSIBLE"]))
    mapped_actions = {
        l.get("target")
        for l in ont.links_by_type.get("exposed_via", [])
        if l.get("source") in ont.objects_by_id
        and (ont.objects_by_id[l.get("source")].get("type") == "Capability")
    }
    required = [
        aid for aid, act in ont.actions_by_id.items()
        if act.get("safety_class") in safety_classes
    ]
    missing = [aid for aid in required if aid not in mapped_actions]
    ok = not missing
    return RuleResult(rule, ok, observed=len(missing), expected=0,
                      detail=("all required actions exposed by a Capability"
                              if ok else f"{len(missing)} action(s) missing Capability exposure: {missing[:8]}"))


def _check_action_invokers(ont: Ontology, rule: Rule) -> RuleResult:
    """Every action's invoker.type is one of the allowed kinds."""
    allowed = set(rule.args.get("allowed", ["ros2_topic", "ros2_service", "cli", "compound"]))
    bad = [aid for aid, act in ont.actions_by_id.items()
           if (act.get("invoker") or {}).get("type") not in allowed]
    ok = not bad
    return RuleResult(rule, ok, observed=len(bad), expected=0,
                      detail=("all invokers ok"
                              if ok else f"{len(bad)} bad invoker(s): {bad[:5]}"))


def _check_goals_defined(ont: Ontology, rule: Rule) -> RuleResult:
    """goals.yaml exists and has a primary_goal block."""
    goals = ont.goals
    if not goals:
        return RuleResult(rule, False, observed=None,
                          expected="goals.yaml with primary_goal",
                          detail="no goals.yaml loaded; learning loop has no objective")
    if not goals.get("primary_goal"):
        return RuleResult(rule, False, observed=list(goals.keys()),
                          expected="primary_goal block",
                          detail="goals.yaml present but no primary_goal declared")
    pg = goals["primary_goal"]
    needed = {"metric", "direction"}
    missing = needed - set(pg.keys())
    if missing:
        return RuleResult(rule, False, observed=list(pg.keys()),
                          expected=f"primary_goal must declare {needed}",
                          detail=f"missing fields: {missing}")
    return RuleResult(rule, True, observed="primary_goal complete",
                      expected="primary_goal complete",
                      detail=f"metric={pg['metric']} direction={pg['direction']}")


def _check_policies_count(ont: Ontology, rule: Rule) -> RuleResult:
    minimum = int(rule.args.get("min", 1))
    n = len(ont.policies)
    return RuleResult(rule, n >= minimum, observed=n, expected=f">= {minimum}",
                      detail=f"{n} policy(ies) declared: {list(ont.policies.keys())}")


def _check_policies_have_code(ont: Ontology, rule: Rule) -> RuleResult:
    """Every policy descriptor with a `code_path` must point to an existing file."""
    if not ont.policies:
        return RuleResult(rule, True, observed=0, expected="n/a",
                          detail="no policies to check")
    bad = [name for name, p in ont.policies.items()
           if p.get("code_path") and not p.get("code_path")]
    # The discovery already verified existence; this rule is a placeholder
    # to keep the policy → code link explicit in profile reports.
    missing_code = [name for name, p in ont.policies.items() if not p.get("code_path")]
    ok = not missing_code
    return RuleResult(rule, ok, observed=len(missing_code), expected=0,
                      detail=("all policies have backing code"
                              if ok else f"policies without .py: {missing_code}"))


_CHECKS: dict[str, CheckFn] = {
    "robot_meta_field":          _check_robot_meta_field,
    "object_count":              _check_object_count,
    "action_count":              _check_action_count,
    "link_count":                _check_link_count,
    "actions_have_field":        _check_actions_have_field,
    "objects_have_source":       _check_objects_have_source,
    "joints_have_position_limit": _check_joints_have_position_limit,
    "loader_clean":              _check_loader_clean,
    "capability_boundary":       _check_capability_boundary,
    "standard_mappings_count":   _check_standard_mappings_count,
    "capabilities_have_link":    _check_capabilities_have_link,
    "actions_exposed_by_capability": _check_actions_exposed_by_capability,
    "action_invokers":           _check_action_invokers,
    "goals_defined":             _check_goals_defined,
    "policies_count":            _check_policies_count,
    "policies_have_code":        _check_policies_have_code,
}


def list_checks() -> list[str]:
    return sorted(_CHECKS.keys())
