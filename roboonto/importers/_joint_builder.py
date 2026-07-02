#!/usr/bin/env python3
"""批量生成灵犀 X2 的 30 DOF 关节 YAML 片段。
这既是 importer 雏形,也是 Sprint 0 产出的一部分。"""
import math
import yaml
from pathlib import Path

# ------- 关节限位(来自 AimDK §1.7,单位:度) -------
ARM_LIMITS_DEG = {
    "shoulder_pitch": (-116.5, 176.5),
    "shoulder_roll":  (-3.5, 174.5),
    "shoulder_yaw":   (-146.5, 146.5),
    "elbow":          (-135, 0),
    "wrist_yaw":      (-146.5, 146.5),
    "wrist_pitch":    (-33, 33),
    "wrist_roll":     (-86.5, 41.5),
}
LEG_LIMITS_DEG = {
    "hip_pitch":      (-146.5, 146.5),
    "hip_roll":       (-13.5, 166.5),
    "hip_yaw":        (-196.5, 96.5),
    "knee":           (0, 138),
    "ankle_pitch":    (-26, 46),
    "ankle_roll":     (-15, 15),
}
WAIST_LIMITS_DEG = {
    "waist_yaw":      (-196.5, 126.5),
    "waist_pitch":    (-18, 18),
    "waist_roll":     (-28, 28),
}
HEAD_LIMITS_DEG = {
    "head_pitch":     (0, 0),        # AimDK: "0°" = 未启用
    "head_yaw":       (-20, 20),
}

# 臂关节与 J 编号的对应(AimDK §1.7.1 表头)
ARM_J_MAPPING = [
    ("shoulder_pitch", "J1", "Shoulder pitch"),
    ("shoulder_roll",  "J2", "Shoulder roll"),
    ("shoulder_yaw",   "J3", "Shoulder yaw"),
    ("elbow",          "J4", "Elbow"),
    ("wrist_yaw",      "J5", "Wrist yaw"),
    ("wrist_pitch",    "J6", "Wrist pitch"),
    ("wrist_roll",     "J7", "Wrist roll"),
]
LEG_J_MAPPING = [
    ("hip_pitch",   "J1", "Hip pitch"),
    ("hip_roll",    "J2", "Hip roll"),
    ("hip_yaw",     "J3", "Hip yaw"),
    ("knee",        "J4", "Knee"),
    ("ankle_pitch", "J5", "Ankle pitch"),
    ("ankle_roll",  "J6", "Ankle roll"),
]


def deg_range_to_rad(lo_deg, hi_deg):
    return {
        "min": round(math.radians(lo_deg), 4),
        "max": round(math.radians(hi_deg), 4),
        "unit": "rad",
    }


def joint(id_, name_human, dof_axis, limits_deg, parent_link, child_link, j_label, source_anchor):
    return {
        "type": "Joint",
        "id": id_,
        "properties": {
            "name_human": name_human,
            "dof_axis": dof_axis,
            "joint_kind": "revolute",
            "parent_link": parent_link,
            "child_link": child_link,
            "position_limit": deg_range_to_rad(*limits_deg),
            "torque_peak": 120,
            "torque_peak_unit": "Nm",
            "j_label": j_label,
        },
        "source": {
            "type": "document",
            "locator": f"aimdk.docx#{source_anchor}",
        },
    }


def build_arm(side):
    objs = []
    for slug, j_label, human in ARM_J_MAPPING:
        axis = slug.split("_")[-1]  # pitch/roll/yaw/elbow(特判)
        dof_axis = axis if axis in ("pitch", "roll", "yaw") else "pitch"
        id_ = f"agibot_x2.hw.{side}_arm.{slug}"
        side_cn = "左" if side == "left" else "右"
        name_human = f"{side_cn}{human}"
        parent = f"agibot_x2.hw.link.{side}_arm_above_{slug}"
        child = f"agibot_x2.hw.link.{side}_arm_below_{slug}"
        objs.append(joint(id_, name_human, dof_axis,
                          ARM_LIMITS_DEG[slug],
                          parent, child, j_label, "§1.7.1"))
    return objs


def build_leg(side):
    objs = []
    for slug, j_label, human in LEG_J_MAPPING:
        axis = slug.split("_")[-1]
        dof_axis = axis if axis in ("pitch", "roll", "yaw") else "pitch"
        id_ = f"agibot_x2.hw.{side}_leg.{slug}"
        side_cn = "左" if side == "left" else "右"
        name_human = f"{side_cn}{human}"
        parent = f"agibot_x2.hw.link.{side}_leg_above_{slug}"
        child = f"agibot_x2.hw.link.{side}_leg_below_{slug}"
        objs.append(joint(id_, name_human, dof_axis,
                          LEG_LIMITS_DEG[slug],
                          parent, child, j_label, "§1.7.2"))
    return objs


def build_waist():
    objs = []
    for slug, (lo, hi) in WAIST_LIMITS_DEG.items():
        axis = slug.split("_")[-1]
        id_ = f"agibot_x2.hw.waist.{slug}"
        objs.append(joint(id_, f"腰{axis}", axis, (lo, hi),
                          "agibot_x2.hw.link.pelvis",
                          "agibot_x2.hw.link.torso",
                          slug.upper(), "§1.7.4"))
    return objs


def build_head():
    objs = []
    for slug, (lo, hi) in HEAD_LIMITS_DEG.items():
        axis = slug.split("_")[-1]
        id_ = f"agibot_x2.hw.head.{slug}"
        notes = "v0.8 未启用" if slug == "head_pitch" else None
        j = joint(id_, f"头{axis}", axis, (lo, hi),
                  "agibot_x2.hw.link.torso",
                  "agibot_x2.hw.link.head",
                  slug.upper(), "§1.7.3")
        if notes:
            j["properties"]["notes"] = notes
        objs.append(j)
    return objs


def build_all_joints():
    out = []
    out.extend(build_arm("left"))
    out.extend(build_arm("right"))
    out.extend(build_leg("left"))
    out.extend(build_leg("right"))
    out.extend(build_waist())
    out.extend(build_head())
    return out


if __name__ == "__main__":
    joints = build_all_joints()
    print(yaml.safe_dump(
        {"objects": joints},
        allow_unicode=True, sort_keys=False, width=120,
    ))
    print(f"# Total: {len(joints)} joints", flush=True)
