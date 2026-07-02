"""Unit tests for the precondition DSL evaluator inside ActionValidator.

Covers each documented predicate: comparison ops, in/not-in, contains/not contains,
and/or/not, abs(), @state.X, @ontology.has_object/has_link_from/has_preset_motion,
parameter references, and error propagation.
"""
from __future__ import annotations

import pytest

from roboonto.api.action_validator import ActionValidator
from roboonto.api.loader import Ontology


# ── helpers ──────────────────────────────────────────────────────────

def _ont() -> Ontology:
    """Tiny ontology supporting all the namespaces the DSL touches."""
    o = Ontology(robot_id="dslbot")
    o.objects_by_id["dslbot.mode.active"] = {
        "id": "dslbot.mode.active", "type": "Mode",
        "properties": {"mode_value": "ACTIVE"},
    }
    o.objects_by_type["Mode"] = [o.objects_by_id["dslbot.mode.active"]]
    o.objects_by_id["dslbot.motion.wave"] = {
        "id": "dslbot.motion.wave", "type": "PresetMotion",
        "properties": {"motion_value": 1, "area_value": 2},
    }
    o.objects_by_type["PresetMotion"] = [o.objects_by_id["dslbot.motion.wave"]]
    o.links.append({"type": "fixed_to", "source": "a", "target": "b"})
    o.links_by_type["fixed_to"] = [o.links[-1]]
    return o


def _action_with_pre(*exprs: str) -> dict:
    return {
        "type_id": "test_action",
        "description": "test",
        "invoker": {"type": "ros2_topic", "name": "/x"},
        "parameters": [],
        "preconditions": [{"expr": e, "error": f"failed: {e}"} for e in exprs],
        "affects": [],
        "safety_class": "INFO",
    }


def _check(ont: Ontology, exprs: list[str], *, params=None, state=None):
    ont.actions_by_id["test_action"] = _action_with_pre(*exprs)
    v = ActionValidator(ont)
    return v.check("test_action", params=params or {}, state=state or {})


# ── comparisons ──────────────────────────────────────────────────────

@pytest.mark.parametrize("expr, state, ok", [
    ('@state.x == 5', {"x": 5}, True),
    ('@state.x == 5', {"x": 6}, False),
    ('@state.x != 5', {"x": 6}, True),
    ('@state.x < 10', {"x": 5}, True),
    ('@state.x <= 10', {"x": 10}, True),
    ('@state.x > 0',  {"x": 1}, True),
    ('@state.x >= 0', {"x": 0}, True),
])
def test_comparisons(expr, state, ok):
    r = _check(_ont(), [expr], state=state)
    assert r.ok is ok, r.summary()


# ── in / not in ──────────────────────────────────────────────────────

def test_in_list_literal():
    r = _check(_ont(), ['@state.mode in ["A", "B"]'], state={"mode": "A"})
    assert r.ok


def test_not_in_list_literal():
    r = _check(_ont(), ['@state.mode not in ["A", "B"]'], state={"mode": "C"})
    assert r.ok


# ── boolean ops + abs() ──────────────────────────────────────────────

def test_and_or_not_combination():
    r = _check(_ont(),
               ['@state.x > 0 and (@state.y < 5 or not @state.z)'],
               state={"x": 1, "y": 3, "z": False})
    assert r.ok


def test_abs_function():
    assert _check(_ont(), ['abs(@state.x) >= 0.1'], state={"x": -0.5}).ok
    assert not _check(_ont(), ['abs(@state.x) >= 0.1'], state={"x": 0.05}).ok


# ── parameter references ─────────────────────────────────────────────

def test_param_reference_in_comparison():
    r = _check(_ont(), ['params.v >= 0.1'], params={"v": 0.5})
    assert r.ok


def test_state_contains_param():
    r = _check(_ont(),
               ['@state.allowed contains params.who'],
               state={"allowed": ["a", "b"]}, params={"who": "a"})
    assert r.ok


# ── ontology helpers ─────────────────────────────────────────────────

def test_ontology_has_object():
    r = _check(_ont(), ['@ontology.has_object("Mode", "dslbot.mode.active")'])
    assert r.ok


def test_ontology_has_object_negative():
    r = _check(_ont(), ['@ontology.has_object("Mode", "dslbot.mode.nonexist")'])
    assert not r.ok


def test_ontology_has_preset_motion():
    r = _check(_ont(), ['@ontology.has_preset_motion(1, 2)'])
    assert r.ok


def test_ontology_has_link_from():
    r = _check(_ont(), ['@ontology.has_link_from("fixed_to", "a", "b")'])
    assert r.ok


# ── error reporting ──────────────────────────────────────────────────

def test_unknown_action_returns_failure():
    o = _ont()
    v = ActionValidator(o)
    r = v.check("nope", params={}, state={})
    assert not r.ok
    assert any("not found" in f.error for f in r.failures)


def test_failed_precondition_propagates_error_text():
    r = _check(_ont(), ['@state.x == 1'], state={"x": 2})
    assert not r.ok
    assert "failed" in r.failures[0].error
