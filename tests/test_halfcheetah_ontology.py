"""Tests for the half-cheetah ontology + framework extensions (goals, policies)."""
from __future__ import annotations

from pathlib import Path

import pytest

from roboonto.api.loader import OntologyLoader
from roboonto.framework import Readiness


HALFCHEETAH_DIR = Path(__file__).resolve().parent.parent / "robots" / "halfcheetah"


@pytest.fixture(scope="module")
def hc_ontology():
    loader = OntologyLoader(HALFCHEETAH_DIR)
    ont = loader.load()
    issues = loader.validate()
    errors = [i for i in issues if i.severity == "error"]
    assert not errors, f"halfcheetah ontology has loader errors: {errors}"
    return ont


# ── ontology load + count ────────────────────────────────────────────

def test_halfcheetah_loads(hc_ontology):
    assert hc_ontology.robot_id == "halfcheetah"
    c = hc_ontology.count()
    assert c["objects"] >= 20
    assert c["actions"] >= 1


def test_six_actuated_joints(hc_ontology):
    joints = hc_ontology.objects_by_type.get("Joint", [])
    assert len(joints) == 6
    names = {j["properties"]["name_urdf"] for j in joints}
    assert names == {"bthigh", "bshin", "bfoot", "fthigh", "fshin", "ffoot"}


def test_apply_torques_action_modeled(hc_ontology):
    act = hc_ontology.actions_by_id.get("apply_torques")
    assert act is not None
    assert act["safety_class"] == "MOTION"
    assert act["invoker"]["type"] == "mujoco_torque"
    assert len(act["affects"]) == 6


# ── goals.yaml support ───────────────────────────────────────────────

def test_goals_loaded(hc_ontology):
    g = hc_ontology.goals
    assert g is not None
    assert g["primary_goal"]["metric"] == "forward_velocity"
    assert g["primary_goal"]["direction"] == "maximize"
    # constraints present
    constraint_ids = {c["id"] for c in g["constraints"]}
    assert "stay_upright" in constraint_ids
    assert "action_efficiency" in constraint_ids


def test_goals_hard_constraint_terminates():
    """The stay_upright hard constraint should be expressed as terminate_episode."""
    loader = OntologyLoader(HALFCHEETAH_DIR)
    ont = loader.load()
    g = ont.goals
    upright = next(c for c in g["constraints"] if c["id"] == "stay_upright")
    assert upright["on_violation"] == "terminate_episode"
    assert upright["severity"] == "hard"


# ── policies discovery ──────────────────────────────────────────────

def test_policies_discovered(hc_ontology):
    assert "gait" in hc_ontology.policies
    pol = hc_ontology.policies["gait"]
    assert pol["code_path"] == "policies/gait.py"
    assert pol["params_path"] == "policies/gait.yaml"
    # Params loaded
    assert pol["params"]["policy_kind"] == "programmatic"
    assert pol["params"]["controller_function"].endswith("trot_controller")


# ── readiness against learning_v1 ───────────────────────────────────

def test_halfcheetah_grades_customer_ready_on_learning_v1():
    r = Readiness(HALFCHEETAH_DIR, profile="learning_v1").run()
    assert r.grade == "customer-ready", r.to_text()
    assert r.counts["must"]["passed"] == r.counts["must"]["total"]
    assert r.counts["should"]["passed"] == r.counts["should"]["total"]


def test_minimal_valid_still_grades_customer_ready_on_customer_v1(minimal_valid_dir):
    """Adding new check types must not regress the existing fixture."""
    r = Readiness(minimal_valid_dir, profile="customer_v1").run()
    assert r.grade == "customer-ready"


def test_x2_still_grades_at_least_beta_on_customer_v1(x2_dir):
    """X2 must not regress on customer_v1 from new loader fields."""
    r = Readiness(x2_dir, profile="customer_v1").run()
    assert r.grade in ("beta", "customer-ready"), r.to_text()
