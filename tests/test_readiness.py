"""Tests for the framework profile + readiness grading."""
from __future__ import annotations

from pathlib import Path

import pytest

from roboonto.framework import (
    Profile,
    Readiness,
    ReadinessReport,
    grade,
    load_profile,
)
from roboonto.framework.profile import RuleResult, Rule, list_checks


# ── profile loading ──────────────────────────────────────────────────

def test_customer_v1_loads_with_rules():
    p = load_profile("customer_v1")
    assert p.id == "customer_v1"
    assert p.reference_robot == "agibot_x2"
    assert len(p.rules) >= 15
    severities = {r.severity for r in p.rules}
    assert severities == {"must", "should", "may"}


def test_unknown_profile_raises():
    with pytest.raises(FileNotFoundError):
        load_profile("__no_such_profile__")


def test_list_checks_includes_built_ins():
    checks = list_checks()
    for name in ("object_count", "actions_have_field",
                 "joints_have_position_limit", "loader_clean",
                 "capabilities_have_link", "actions_exposed_by_capability"):
        assert name in checks, f"check '{name}' missing"


# ── grade math ───────────────────────────────────────────────────────

def _result(severity: str, passed: bool) -> RuleResult:
    rule = Rule(id=f"r-{severity}-{passed}", severity=severity,
                check="object_count")
    return RuleResult(rule=rule, passed=passed)


def test_grade_must_failure_is_fail():
    g, _ = grade([_result("must", False), _result("should", True)])
    assert g == "fail"


def test_grade_alpha_when_must_pass_but_low_should():
    g, _ = grade([_result("must", True),
                  _result("should", False), _result("should", False)])
    assert g == "alpha"


def test_grade_beta_when_70_pct_should():
    results = [_result("must", True)] * 3
    # 7 of 10 should pass (70%)
    results += [_result("should", True)] * 7
    results += [_result("should", False)] * 3
    g, _ = grade(results)
    assert g == "beta"


def test_grade_customer_ready_when_all_should_pass():
    results = [_result("must", True)] * 2
    results += [_result("should", True)] * 5
    results += [_result("may", False)] * 5  # `may` doesn't block
    g, _ = grade(results)
    assert g == "customer-ready"


# ── end-to-end on real ontologies ────────────────────────────────────

def test_x2_grades_at_least_beta(x2_dir):
    r = Readiness(x2_dir).run()
    assert r.grade in ("beta", "customer-ready"), \
        f"X2 reference should grade beta+, got {r.grade}\n{r.to_text()}"
    assert r.score >= 80
    assert r.counts["must"]["passed"] == r.counts["must"]["total"]


def test_minimal_fixture_grades_customer_ready(minimal_valid_dir):
    r = Readiness(minimal_valid_dir).run()
    assert r.grade == "customer-ready", r.to_text()
    assert r.counts["must"]["passed"] == r.counts["must"]["total"]
    assert r.counts["should"]["passed"] == r.counts["should"]["total"]


def test_template_fails(template_dir):
    """The empty _template/ should not pass — every must rule fails."""
    r = Readiness(template_dir).run()
    assert r.grade == "fail"
    must_fails = r.failures_by_severity("must")
    assert len(must_fails) >= 5  # most must rules fail on placeholder data


# ── report serialization ─────────────────────────────────────────────

def test_report_to_dict_round_trip(minimal_valid_dir):
    r = Readiness(minimal_valid_dir).run()
    d = r.to_dict()
    assert {"robot_id", "profile", "grade", "score", "counts", "results"}.issubset(d)
    assert all({"id", "severity", "passed"}.issubset(rr) for rr in d["results"])


def test_report_to_text_renders(minimal_valid_dir):
    r = Readiness(minimal_valid_dir).run()
    text = r.to_text(color=False)
    assert "minibot" in text
    assert "MUST" in text
    assert "SHOULD" in text


# ── individual checks ────────────────────────────────────────────────

def test_check_object_count_passes(minimal_valid_ontology):
    rule = Rule(id="t", severity="must", check="object_count",
                args={"type": "Mode", "min": 2})
    p = Profile(id="t", description="", reference_robot="", rules=[rule])
    res = p.evaluate(minimal_valid_ontology)
    assert res[0].passed


def test_check_object_count_fails(minimal_valid_ontology):
    rule = Rule(id="t", severity="must", check="object_count",
                args={"type": "Mode", "min": 100})
    p = Profile(id="t", description="", reference_robot="", rules=[rule])
    res = p.evaluate(minimal_valid_ontology)
    assert not res[0].passed
    assert ">= 100" in str(res[0].expected)
