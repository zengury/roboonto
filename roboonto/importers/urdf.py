"""
roboonto.importers.urdf
========================

从 URDF 抽取机器人运动学 + 动力学 + 传感器挂载关系。

输入:
    URDF 文件路径 + mesh 目录根路径
输出:
    - kinematics.yaml    Link 对象 + parent_of 关系 + fixed 挂载
    - joints_patch.yaml  覆盖/补全 hardware.yaml 里的 Joint 对象(用 URDF 权威数据)
    - diff_report.md     URDF vs 现有 ontology 的冲突报告

设计纪律:
    1. URDF 是运动学/动力学权威。文档里的数字若冲突,URDF 赢。
    2. 但文档给了中文 name_human、业务语义(如 safety_note),这些保留。
    3. Importer 不"合并",而是"patch"—— 产出可审阅的 YAML 片段。
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
import math
from dataclasses import dataclass, field
from pathlib import Path
import yaml


# ============================================================
# Helpers
# ============================================================

def _parse_xyz(text: str | None) -> list[float]:
    if not text:
        return [0.0, 0.0, 0.0]
    return [float(x) for x in text.split()]


def _parse_inertia(el: ET.Element | None) -> dict | None:
    if el is None:
        return None
    return {
        "ixx": float(el.get("ixx", 0)),
        "ixy": float(el.get("ixy", 0)),
        "ixz": float(el.get("ixz", 0)),
        "iyy": float(el.get("iyy", 0)),
        "iyz": float(el.get("iyz", 0)),
        "izz": float(el.get("izz", 0)),
    }


# ============================================================
# Main importer
# ============================================================

@dataclass
class URDFImportResult:
    robot_id: str
    urdf_name: str
    links: list[dict] = field(default_factory=list)
    joints: list[dict] = field(default_factory=list)          # revolute joints, to patch hardware.yaml
    fixed_mounts: list[dict] = field(default_factory=list)    # fixed joints (sensor mounts)
    parent_of_links: list[dict] = field(default_factory=list) # parent_of relations
    warnings: list[str] = field(default_factory=list)


class URDFImporter:
    def __init__(self, robot_id: str = "agibot_x2"):
        self.robot_id = robot_id

    def run(self, urdf_path: Path) -> URDFImportResult:
        tree = ET.parse(urdf_path)
        root = tree.getroot()
        result = URDFImportResult(
            robot_id=self.robot_id,
            urdf_name=root.get("name", "unknown"),
        )

        urdf_rel = urdf_path.name
        src_locator = f"{urdf_rel}"

        # Links
        for link_el in root.findall("link"):
            result.links.append(self._parse_link(link_el, src_locator))

        # Joints
        for joint_el in root.findall("joint"):
            jtype = joint_el.get("type")
            if jtype == "revolute":
                result.joints.append(self._parse_revolute(joint_el, src_locator))
            elif jtype == "fixed":
                result.fixed_mounts.append(self._parse_fixed(joint_el, src_locator))
            else:
                result.warnings.append(f"unsupported joint type '{jtype}' on {joint_el.get('name')}")

        # parent_of relations from all joints (revolute + fixed both define tree structure)
        for joint_el in root.findall("joint"):
            parent_link = joint_el.find("parent")
            child_link = joint_el.find("child")
            if parent_link is not None and child_link is not None:
                result.parent_of_links.append({
                    "type": "parent_of",
                    "source": f"{self.robot_id}.hw.link.{parent_link.get('link')}",
                    "target": f"{self.robot_id}.hw.link.{child_link.get('link')}",
                    "via_joint": joint_el.get("name"),
                })

        return result

    # ---------- Element parsers ----------

    def _parse_link(self, link_el: ET.Element, src: str) -> dict:
        name = link_el.get("name")
        inertial = link_el.find("inertial")
        visual = link_el.find("visual")
        collision = link_el.find("collision")

        props: dict = {"name_urdf": name}

        if inertial is not None:
            mass_el = inertial.find("mass")
            if mass_el is not None:
                props["mass"] = float(mass_el.get("value"))
                props["mass_unit"] = "kg"
            origin = inertial.find("origin")
            if origin is not None:
                props["inertial_origin_xyz"] = _parse_xyz(origin.get("xyz"))
                props["inertial_origin_rpy"] = _parse_xyz(origin.get("rpy"))
            props["inertia"] = _parse_inertia(inertial.find("inertia"))

        if visual is not None:
            mesh = visual.find("geometry/mesh")
            if mesh is not None:
                props["visual_mesh"] = mesh.get("filename")

        if collision is not None:
            mesh = collision.find("geometry/mesh")
            if mesh is not None:
                props["collision_mesh"] = mesh.get("filename")

        return {
            "type": "Link",
            "id": f"{self.robot_id}.hw.link.{name}",
            "properties": props,
            "source": {"type": "urdf", "locator": f"{src}#link[{name}]"},
        }

    def _parse_revolute(self, joint_el: ET.Element, src: str) -> dict:
        name = joint_el.get("name")
        parent = joint_el.find("parent").get("link")
        child = joint_el.find("child").get("link")
        origin = joint_el.find("origin")
        axis = joint_el.find("axis")
        limit = joint_el.find("limit")

        props: dict = {
            "urdf_name": name,
            "joint_kind": "revolute",
            "parent_link": f"{self.robot_id}.hw.link.{parent}",
            "child_link": f"{self.robot_id}.hw.link.{child}",
        }
        if origin is not None:
            props["origin_xyz"] = _parse_xyz(origin.get("xyz"))
            props["origin_rpy"] = _parse_xyz(origin.get("rpy"))
        if axis is not None:
            axis_xyz = _parse_xyz(axis.get("xyz"))
            props["axis_xyz"] = axis_xyz
            # 推断 dof_axis: 如果是纯 x/y/z 单位向量,映射到 roll/pitch/yaw
            if abs(sum(axis_xyz)) == 1 and max(abs(x) for x in axis_xyz) == 1:
                idx = [abs(x) for x in axis_xyz].index(1)
                props["dof_axis"] = ["roll", "pitch", "yaw"][idx]  # x→roll, y→pitch, z→yaw (URDF convention)
        if limit is not None:
            lo = float(limit.get("lower"))
            hi = float(limit.get("upper"))
            props["position_limit"] = {
                "min": round(lo, 4), "max": round(hi, 4), "unit": "rad",
            }
            props["velocity_limit"] = {
                "value": float(limit.get("velocity")),
                "unit": "rad/s",
            }
            props["effort_limit"] = {
                "value": float(limit.get("effort")),
                "unit": "Nm",
            }

        return {
            "type": "Joint",
            "id_by_urdf_name": name,   # 供 patch 阶段做 mapping
            "properties": props,
            "source": {"type": "urdf", "locator": f"{src}#joint[{name}]"},
        }

    def _parse_fixed(self, joint_el: ET.Element, src: str) -> dict:
        name = joint_el.get("name")
        parent = joint_el.find("parent").get("link")
        child = joint_el.find("child").get("link")
        origin = joint_el.find("origin")
        props: dict = {
            "joint_name_urdf": name,
            "parent_link": f"{self.robot_id}.hw.link.{parent}",
            "child_link": f"{self.robot_id}.hw.link.{child}",
        }
        if origin is not None:
            props["origin_xyz"] = _parse_xyz(origin.get("xyz"))
            props["origin_rpy"] = _parse_xyz(origin.get("rpy"))

        return {
            "type_hint": "FixedMount",   # 后面处理为 Frame 或 sensor mount 关系
            "source": {"type": "urdf", "locator": f"{src}#joint[{name}]"},
            "properties": props,
        }


# ============================================================
# Ontology joint patcher — 把 URDF 权威数据和现有 ontology 的业务语义合并
# ============================================================

# URDF joint name → ontology id  (保持现有 ontology 结构)
_URDF_TO_ONTO = {
    # arms
    "left_shoulder_pitch_joint":  "agibot_x2.hw.left_arm.shoulder_pitch",
    "left_shoulder_roll_joint":   "agibot_x2.hw.left_arm.shoulder_roll",
    "left_shoulder_yaw_joint":    "agibot_x2.hw.left_arm.shoulder_yaw",
    "left_elbow_joint":           "agibot_x2.hw.left_arm.elbow",
    "left_wrist_yaw_joint":       "agibot_x2.hw.left_arm.wrist_yaw",
    "left_wrist_pitch_joint":     "agibot_x2.hw.left_arm.wrist_pitch",
    "left_wrist_roll_joint":      "agibot_x2.hw.left_arm.wrist_roll",
    "right_shoulder_pitch_joint": "agibot_x2.hw.right_arm.shoulder_pitch",
    "right_shoulder_roll_joint":  "agibot_x2.hw.right_arm.shoulder_roll",
    "right_shoulder_yaw_joint":   "agibot_x2.hw.right_arm.shoulder_yaw",
    "right_elbow_joint":          "agibot_x2.hw.right_arm.elbow",
    "right_wrist_yaw_joint":      "agibot_x2.hw.right_arm.wrist_yaw",
    "right_wrist_pitch_joint":    "agibot_x2.hw.right_arm.wrist_pitch",
    "right_wrist_roll_joint":     "agibot_x2.hw.right_arm.wrist_roll",
    # legs
    "left_hip_pitch_joint":       "agibot_x2.hw.left_leg.hip_pitch",
    "left_hip_roll_joint":        "agibot_x2.hw.left_leg.hip_roll",
    "left_hip_yaw_joint":         "agibot_x2.hw.left_leg.hip_yaw",
    "left_knee_joint":            "agibot_x2.hw.left_leg.knee",
    "left_ankle_pitch_joint":     "agibot_x2.hw.left_leg.ankle_pitch",
    "left_ankle_roll_joint":      "agibot_x2.hw.left_leg.ankle_roll",
    "right_hip_pitch_joint":      "agibot_x2.hw.right_leg.hip_pitch",
    "right_hip_roll_joint":       "agibot_x2.hw.right_leg.hip_roll",
    "right_hip_yaw_joint":        "agibot_x2.hw.right_leg.hip_yaw",
    "right_knee_joint":           "agibot_x2.hw.right_leg.knee",
    "right_ankle_pitch_joint":    "agibot_x2.hw.right_leg.ankle_pitch",
    "right_ankle_roll_joint":     "agibot_x2.hw.right_leg.ankle_roll",
    # waist
    "waist_yaw_joint":            "agibot_x2.hw.waist.waist_yaw",
    "waist_pitch_joint":          "agibot_x2.hw.waist.waist_pitch",
    "waist_roll_joint":           "agibot_x2.hw.waist.waist_roll",
    # head
    "head_yaw_joint":             "agibot_x2.hw.head.head_yaw",
    "head_pitch_joint":           "agibot_x2.hw.head.head_pitch",
}


def patch_joints(urdf_result: URDFImportResult, existing_joints: list[dict]) -> tuple[list[dict], list[dict]]:
    """Merge URDF-authoritative joint data with existing ontology business semantics.

    Returns:
        (patched_joints, diff_entries)
        - patched_joints: new Joint list,每个是 URDF 权威数据 + 现有 name_human/notes
        - diff_entries: 变更清单,用于 diff_report.md
    """
    existing_by_id = {j["id"]: j for j in existing_joints}
    patched = []
    diffs = []

    for uj in urdf_result.joints:
        urdf_name = uj["id_by_urdf_name"]
        onto_id = _URDF_TO_ONTO.get(urdf_name)
        if not onto_id:
            diffs.append({
                "joint": urdf_name, "kind": "no_mapping",
                "note": "URDF joint has no ontology id mapping registered",
            })
            continue

        existing = existing_by_id.get(onto_id)
        urdf_props = uj["properties"]
        new_props = dict(urdf_props)  # URDF 权威字段

        # 保留 ontology 里的业务语义
        if existing:
            for keep_key in ("name_human", "j_label", "notes"):
                old_val = (existing.get("properties") or {}).get(keep_key)
                if old_val is not None:
                    new_props[keep_key] = old_val
            # 记录 diff
            old_limit = (existing.get("properties") or {}).get("position_limit") or {}
            new_limit = new_props.get("position_limit") or {}
            if (
                old_limit.get("min") != new_limit.get("min")
                or old_limit.get("max") != new_limit.get("max")
            ):
                diffs.append({
                    "joint": onto_id,
                    "kind": "position_limit",
                    "old": f"[{old_limit.get('min')}, {old_limit.get('max')}] rad",
                    "new": f"[{new_limit.get('min')}, {new_limit.get('max')}] rad",
                    "urdf_name": urdf_name,
                })
            old_torque = (existing.get("properties") or {}).get("torque_peak")
            new_effort = (new_props.get("effort_limit") or {}).get("value")
            if old_torque is not None and new_effort is not None and abs(old_torque - new_effort) > 1:
                diffs.append({
                    "joint": onto_id,
                    "kind": "effort",
                    "old": f"torque_peak={old_torque} Nm (ontology)",
                    "new": f"effort_limit={new_effort} Nm (URDF)",
                    "urdf_name": urdf_name,
                })
            # 删掉 ontology 的 torque_peak(被 effort_limit 取代)
            new_props.pop("torque_peak", None)
            new_props.pop("torque_peak_unit", None)

        patched.append({
            "type": "Joint",
            "id": onto_id,
            "properties": new_props,
            "source": {
                "type": "urdf+document",
                "locator": uj["source"]["locator"],
                "business_semantics_from": "aimdk.docx#§1.7",
            },
        })

    return patched, diffs


# ============================================================
# Sensor mount patcher — fixed joints 建立 Sensor ↔ Link 挂载
# ============================================================

_FIXED_JOINT_TO_SENSOR = {
    "imu_in_pelvis_joint":  "agibot_x2.hw.sensor.imu_torso",   # URDF 里叫 pelvis,但 ontology 按文档建的叫 imu_torso
    "imu_in_torso_joint":   None,    # ontology 目前无此传感器,要新增
    "imu_in_head_joint":    None,
    "lidar_chest_front":    "agibot_x2.hw.sensor.lidar_chest_front",
    "rgbd_head_front":      "agibot_x2.hw.sensor.rgbd_head_front",
    "stereo_head_front":    None,    # ontology 里分了左右,URDF 只有一个 "stereo_head_front" link
    "rgb_head_rear":        "agibot_x2.hw.sensor.rgb_head_rear",
    "rgb_head_center":      "agibot_x2.hw.sensor.rgb_head_front_interaction",
}


def mount_relations(urdf_result: URDFImportResult) -> tuple[list[dict], list[dict]]:
    """Produce sensor-mount links + suggestions for new sensors/frames."""
    mount_links = []
    suggestions = []
    for fm in urdf_result.fixed_mounts:
        jname = fm["properties"]["joint_name_urdf"]
        sensor_id = _FIXED_JOINT_TO_SENSOR.get(jname)
        if sensor_id:
            mount_links.append({
                "type": "mounted_via_fixed",
                "source": sensor_id,
                "target": fm["properties"]["parent_link"],
                "via_joint": jname,
                "origin_xyz": fm["properties"].get("origin_xyz"),
                "origin_rpy": fm["properties"].get("origin_rpy"),
            })
        elif jname == "base_link_joint":
            # 结构性 fixed joint,不挂传感器,但保留为 parent_of
            pass
        elif jname in _FIXED_JOINT_TO_SENSOR:
            suggestions.append({
                "kind": "missing_sensor",
                "urdf_joint": jname,
                "parent": fm["properties"]["parent_link"],
                "child": fm["properties"]["child_link"],
                "note": "URDF declares this sensor link but no ontology Sensor object matches",
            })
    return mount_links, suggestions


# ============================================================
# Diff report writer
# ============================================================

def write_diff_report(
    diffs_joints: list[dict],
    mount_suggestions: list[dict],
    warnings: list[str],
    urdf_name: str,
    out_path: Path,
):
    lines = []
    lines.append(f"# URDF ↔ Ontology Diff Report")
    lines.append(f"")
    lines.append(f"- URDF:      `x2_ultra.urdf` (robot name: `{urdf_name}`)")
    lines.append(f"- Ontology:  `robots/agibot_x2/hardware.yaml` (pre-patch)")
    lines.append(f"- Total diffs: **{len(diffs_joints)}** joint conflicts, "
                 f"**{len(mount_suggestions)}** sensor suggestions")
    lines.append(f"")
    lines.append(f"In every conflict the **URDF wins** — URDF is the kinematics/dynamics")
    lines.append(f"source of truth. The AimDK document often gives documentation-level")
    lines.append(f"approximations (typos, direction conventions, ''peak 120 Nm'' headline spec).")
    lines.append(f"")

    # Group by kind
    by_kind: dict[str, list[dict]] = {}
    for d in diffs_joints:
        by_kind.setdefault(d["kind"], []).append(d)

    def render_table(title, rows, cols):
        lines.append(f"## {title}")
        lines.append(f"")
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for r in rows:
            lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
        lines.append("")

    if "position_limit" in by_kind:
        render_table("Position limit conflicts", by_kind["position_limit"],
                     ["joint", "old", "new", "urdf_name"])
    if "effort" in by_kind:
        render_table("Effort / torque conflicts (⚠ ontology had one-size-fits-all 120 Nm)",
                     by_kind["effort"], ["joint", "old", "new", "urdf_name"])
    if "no_mapping" in by_kind:
        render_table("Unmapped URDF joints (ontology needs new object ids)",
                     by_kind["no_mapping"], ["joint", "note"])

    if mount_suggestions:
        lines.append(f"## Suggested new ontology objects")
        lines.append("")
        for s in mount_suggestions:
            lines.append(f"- **{s['kind']}**: URDF `{s['urdf_joint']}` — {s['note']}")
            lines.append(f"  - parent: `{s['parent']}`")
            lines.append(f"  - child:  `{s['child']}`")
        lines.append("")

    if warnings:
        lines.append(f"## Importer warnings")
        lines.append("")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


# ============================================================
# CLI entry
# ============================================================

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("urdf_path", type=Path)
    ap.add_argument("--robot-dir", type=Path, required=True,
                    help="robots/<id>/ directory (reads hardware.yaml, writes patch)")
    ap.add_argument("--write-patch", action="store_true")
    args = ap.parse_args()

    # 1. import URDF
    imp = URDFImporter(robot_id="agibot_x2")
    result = imp.run(args.urdf_path)
    print(f"[urdf] links={len(result.links)} revolute={len(result.joints)} fixed={len(result.fixed_mounts)}")

    # 2. load existing ontology
    hw_path = args.robot_dir / "hardware.yaml"
    hw = yaml.safe_load(hw_path.read_text())
    existing_joints = [o for o in hw["objects"] if o.get("type") == "Joint"]

    # 3. patch joints
    patched_joints, joint_diffs = patch_joints(result, existing_joints)
    print(f"[patch] joints={len(patched_joints)} diffs={len(joint_diffs)}")

    # 4. sensor mounts
    mount_links, mount_suggestions = mount_relations(result)
    print(f"[mount] mount_links={len(mount_links)} suggestions={len(mount_suggestions)}")

    # 5. emit kinematics.yaml (new file)
    kinematics_doc = {
        "# __header__": "Generated by roboonto.importers.urdf from x2_ultra.urdf",
        "objects": result.links,
        "links": result.parent_of_links + mount_links,
    }
    # drop the comment header key before dumping (YAML doesn't preserve)
    kinematics_doc.pop("# __header__")
    kin_path = args.robot_dir / "kinematics.yaml"
    kin_path.write_text(
        "# Generated by roboonto.importers.urdf from x2_ultra.urdf\n"
        "# Contains Link objects + parent_of tree + sensor mount relations\n\n" +
        yaml.safe_dump(kinematics_doc, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"[write] {kin_path}")

    # 6. emit joints_patch.yaml (replaces the joint portion of hardware.yaml on apply)
    patch_doc = {
        "# __header__": "URDF-authoritative joint data + ontology business semantics",
        "objects": patched_joints,
    }
    patch_doc.pop("# __header__")
    patch_path = args.robot_dir / "joints_patch.yaml"
    patch_path.write_text(
        "# Generated by roboonto.importers.urdf — URDF-authoritative joint data.\n"
        "# To apply: replace the Joint objects in hardware.yaml with these.\n\n" +
        yaml.safe_dump(patch_doc, allow_unicode=True, sort_keys=False, width=120),
        encoding="utf-8",
    )
    print(f"[write] {patch_path}")

    # 7. diff report
    report_path = args.robot_dir / "DIFF_REPORT.md"
    write_diff_report(
        joint_diffs, mount_suggestions, result.warnings,
        result.urdf_name, report_path,
    )
    print(f"[write] {report_path}")

    # 8. (optional) apply patch to hardware.yaml
    if args.write_patch:
        # Replace joints in hardware.yaml
        new_objects = [o for o in hw["objects"] if o.get("type") != "Joint"] + patched_joints
        hw["objects"] = new_objects
        hw_path.write_text(
            "# AgiBot X2 — Hardware Ontology (URDF-patched by roboonto/importers/urdf.py)\n\n" +
            yaml.safe_dump(hw, allow_unicode=True, sort_keys=False, width=120),
            encoding="utf-8",
        )
        print(f"[apply] patched {hw_path}")


if __name__ == "__main__":
    main()
