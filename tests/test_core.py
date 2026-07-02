"""Minimal smoke tests — validate loader + validator against the real X2 ontology."""
from pathlib import Path
import pytest

from roboonto.api.loader import OntologyLoader
from roboonto.api.query import Query
from roboonto.api.action_validator import ActionValidator

ROBOT_DIR = Path(__file__).parent.parent / "robots" / "agibot_x2"


@pytest.fixture(scope="module")
def ontology():
    loader = OntologyLoader(ROBOT_DIR)
    ont = loader.load()
    issues = loader.validate()
    errors = [i for i in issues if i.severity == "error"]
    assert not errors, f"ontology has errors: {errors}"
    return ont


# ------------- Loader -------------
def test_loads_expected_counts(ontology):
    c = ontology.count()
    assert c["objects"] > 150
    assert c["actions"] >= 20
    assert c["links"] > 40


def test_has_core_modes(ontology):
    """五个核心模式必须存在;ProductionTest 是从 log 反推的额外模式。"""
    modes = ontology.objects_by_type.get("Mode", [])
    mode_values = {m["properties"]["mode_value"] for m in modes}
    core_modes = {
        "PASSIVE_DEFAULT", "DAMPING_DEFAULT", "JOINT_DEFAULT",
        "STAND_DEFAULT", "LOCOMOTION_DEFAULT",
    }
    assert core_modes.issubset(mode_values), f"missing core modes: {core_modes - mode_values}"
    assert len(modes) >= 5


def test_has_30_plus_active_joints(ontology):
    # 30 主动 + 1 占位(head_pitch)= 31
    joints = ontology.objects_by_type.get("Joint", [])
    assert len(joints) == 31


def test_pmu_bit_semantics(ontology):
    q = Query(ontology)
    bits = q.status_bits_on_field("pmu_bool_status")
    assert len(bits) >= 10
    # 特定位:bit 6 = bus48vOverCurrent
    bit6 = [b for b in bits if (b["properties"] or {}).get("bit_index") == 6]
    assert len(bit6) == 1
    assert bit6[0]["properties"]["severity"] == "error"


# ------------- Query -------------
def test_actions_allowed_in_locomotion(ontology):
    q = Query(ontology)
    allowed = q.actions_allowed_in_mode("LOCOMOTION_DEFAULT")
    ids = {a["type_id"] for a in allowed}
    assert "set_forward_velocity" in ids
    assert "set_lateral_velocity" in ids
    assert "set_angular_velocity" in ids


def test_preset_motion_forbidden_in_locomotion(ontology):
    q = Query(ontology)
    forbidden = q.actions_forbidden_in_mode("LOCOMOTION_DEFAULT")
    ids = {a["type_id"] for a in forbidden}
    assert "set_preset_motion" in ids


# ------------- Validator -------------
def test_valid_forward_velocity(ontology):
    v = ActionValidator(ontology)
    state = {
        "mc_action": "LOCOMOTION_DEFAULT",
        "is_moving": True,
        "registered_input_sources": ["my_agent"],
    }
    report = v.check("set_forward_velocity",
                     params={"forward_velocity": 0.5, "source": "my_agent"},
                     state=state)
    assert report.ok, report.summary()


def test_startup_threshold_blocks(ontology):
    v = ActionValidator(ontology)
    state = {
        "mc_action": "LOCOMOTION_DEFAULT",
        "is_moving": False,             # 静止
        "registered_input_sources": ["my_agent"],
    }
    report = v.check("set_forward_velocity",
                     params={"forward_velocity": 0.05, "source": "my_agent"},
                     state=state)
    assert not report.ok
    assert any("启动门限" in f.error for f in report.failures)


def test_unregistered_source_blocks(ontology):
    v = ActionValidator(ontology)
    state = {
        "mc_action": "LOCOMOTION_DEFAULT", "is_moving": True,
        "registered_input_sources": ["rc"],
    }
    report = v.check("set_forward_velocity",
                     params={"forward_velocity": 0.5, "source": "my_agent"},
                     state=state)
    assert not report.ok
    assert any("注册输入源" in f.error for f in report.failures)


def test_preset_motion_wrong_mode_blocks(ontology):
    v = ActionValidator(ontology)
    state = {"mc_action": "LOCOMOTION_DEFAULT"}
    report = v.check("set_preset_motion",
                     params={"motion": 1002, "area": 2},
                     state=state)
    assert not report.ok


def test_hand_control_fatal_without_disabling_native(ontology):
    v = ActionValidator(ontology)
    state = {
        "hand_type": {"left": 2, "right": 2},
        "native_hand_control_disabled": False,
    }
    report = v.check("set_hand_command",
                     params={
                         "left_hand_type": 2, "left_hands": [],
                         "right_hand_type": 2, "right_hands": [],
                     }, state=state)
    assert not report.ok
    # 必须有 fatal 级别的失败
    assert any(f.severity == "fatal" for f in report.failures)


def test_enum_violation(ontology):
    v = ActionValidator(ontology)
    report = v.check("set_joint_position",
                     params={"domain": "legs", "joints": []},  # 拼写错误
                     state={"mc_action": "JOINT_DEFAULT"})
    assert not report.ok
    assert any("not in enum" in f.error for f in report.failures)
