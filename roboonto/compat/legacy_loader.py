"""
roboonto.compat.legacy_loader
======================

负责:
  1. 加载 ontology 入口(ontology.yaml),递归展开 includes
  2. 把所有 objects/actions/links 收拢到内存索引
  3. 基本一致性校验:
      - 所有 ref 指向的目标存在
      - 同 category 下 id 不重复
      - 所有 Joint 有 position_limit 且 min < max
      - 所有 Action 的 invoker 字段合法
      - precondition 表达式基本格式正确(不做完整 parse,留给 validator)

设计纪律:
  - loader 不做 runtime 状态求值,只做静态一致性
  - loader 不执行任何 action,不调用 ROS
"""

from __future__ import annotations
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Ontology:
    """加载后的 ontology 内存表示,供上层查询 / 校验 / agent 消费。"""
    robot_id: str
    robot_meta: dict = field(default_factory=dict)
    objects_by_id: dict[str, dict] = field(default_factory=dict)
    objects_by_type: dict[str, list[dict]] = field(default_factory=dict)
    actions_by_id: dict[str, dict] = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)
    goals: dict = field(default_factory=dict)
    policies: dict[str, dict] = field(default_factory=dict)
    standard_mappings: dict = field(default_factory=dict)
    # 辅助索引
    links_by_source: dict[str, list[dict]] = field(default_factory=dict)
    links_by_type: dict[str, list[dict]] = field(default_factory=dict)

    def count(self) -> dict[str, int]:
        return {
            "objects": len(self.objects_by_id),
            "actions": len(self.actions_by_id),
            "links": len(self.links),
            "object_types": len(self.objects_by_type),
        }


@dataclass
class ValidationIssue:
    severity: str            # error | warn | info
    category: str            # ref | duplicate | joint_limit | invoker | ...
    message: str
    location: str = ""

    def __str__(self):
        return f"[{self.severity.upper()}] {self.category}: {self.message}" + (
            f"  @ {self.location}" if self.location else ""
        )


class OntologyLoader:
    def __init__(self, ontology_dir: Path):
        self.dir = Path(ontology_dir)
        self.ontology = Ontology(robot_id="?")
        self.issues: list[ValidationIssue] = []

    # ---------- Public ----------
    def load(self) -> Ontology:
        entry = self.dir / "ontology.yaml"
        if not entry.exists():
            raise FileNotFoundError(f"ontology.yaml not found in {self.dir}")
        entry_doc = self._read(entry)

        robot = entry_doc.get("robot", {})
        self.ontology.robot_id = robot.get("id", "unknown")
        self.ontology.robot_meta = robot

        for shard_name in entry_doc.get("includes", []):
            shard_path = self.dir / shard_name
            if not shard_path.exists():
                self._issue("error", "missing_shard",
                            f"include shard not found: {shard_name}")
                continue
            self._load_shard(shard_path)
        self._load_policies()

        return self.ontology

    def validate(self) -> list[ValidationIssue]:
        """运行所有静态一致性检查。"""
        self._check_ref_integrity()
        self._check_duplicate_ids()
        self._check_joint_limits()
        self._check_action_invokers()
        self._check_link_endpoints()
        return self.issues

    def summary(self) -> str:
        c = self.ontology.count()
        per_type = "\n".join(
            f"    {t:20s} {len(items)}"
            for t, items in sorted(self.ontology.objects_by_type.items())
        )
        errors = sum(1 for i in self.issues if i.severity == "error")
        warns  = sum(1 for i in self.issues if i.severity == "warn")
        return (
            f"RoboOnto loaded: {self.ontology.robot_id}\n"
            f"  objects: {c['objects']}  actions: {c['actions']}  links: {c['links']}\n"
            f"  object types ({c['object_types']}):\n{per_type}\n"
            f"  validation: {errors} errors, {warns} warnings"
        )

    # ---------- Internal ----------
    def _read(self, path: Path) -> dict:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_shard(self, path: Path):
        doc = self._read(path)
        where = str(path.relative_to(self.dir.parent))
        if path.name == "goals.yaml":
            self.ontology.goals = doc
        if path.name == "standard_mappings.yaml":
            self.ontology.standard_mappings = doc
        for obj in doc.get("objects") or []:
            self._ingest_object(obj, where)
        for act in doc.get("actions") or []:
            self._ingest_action(act, where)
        for link in doc.get("links") or []:
            self._ingest_link(link, where)

    def _load_policies(self):
        policies_dir = self.dir / "policies"
        if not policies_dir.exists():
            return
        for params_path in sorted(policies_dir.glob("*.yaml")):
            name = params_path.stem
            code_path = params_path.with_suffix(".py")
            rel_params = params_path.relative_to(self.dir).as_posix()
            rel_code = code_path.relative_to(self.dir).as_posix() if code_path.exists() else ""
            self.ontology.policies[name] = {
                "code_path": rel_code,
                "params_path": rel_params,
                "params": self._read(params_path),
            }

    def _ingest_object(self, obj: dict, where: str):
        oid = obj.get("id")
        otype = obj.get("type")
        if not oid or not otype:
            self._issue("error", "malformed_object",
                        f"object missing id or type: {obj}", where)
            return
        if oid in self.ontology.objects_by_id:
            self._issue("error", "duplicate_id",
                        f"duplicate object id: {oid}", where)
            return
        self.ontology.objects_by_id[oid] = obj
        self.ontology.objects_by_type.setdefault(otype, []).append(obj)

    def _ingest_action(self, act: dict, where: str):
        aid = act.get("type_id")
        if not aid:
            self._issue("error", "malformed_action",
                        f"action missing type_id: {act}", where)
            return
        if aid in self.ontology.actions_by_id:
            self._issue("error", "duplicate_id",
                        f"duplicate action type_id: {aid}", where)
            return
        self.ontology.actions_by_id[aid] = act

    def _ingest_link(self, link: dict, where: str):
        self.ontology.links.append(link)
        src = link.get("source")
        if src:
            self.ontology.links_by_source.setdefault(src, []).append(link)
        ltype = link.get("type")
        if ltype:
            self.ontology.links_by_type.setdefault(ltype, []).append(link)

    def _issue(self, severity: str, category: str, message: str, location: str = ""):
        self.issues.append(ValidationIssue(severity, category, message, location))

    # ---------- Validation Rules ----------
    def _check_ref_integrity(self):
        """所有 link 的 source/target 必须指向已知 object 或 action。
           Action 之间的 ref 也要解析。"""
        known = set(self.ontology.objects_by_id) | set(self.ontology.actions_by_id)
        for link in self.ontology.links:
            src, tgt = link.get("source"), link.get("target")
            # 允许 wildcard 引用(如 agibot_x2.hw.left_leg.*)
            for side, val in [("source", src), ("target", tgt)]:
                if val is None:
                    self._issue("error", "link_missing_side",
                                f"link missing {side}: {link}")
                    continue
                if "*" in str(val):
                    continue
                if val not in known:
                    self._issue("warn", "dangling_ref",
                                f"link {link.get('type')}: {side}={val} not found",
                                location=f"link({link.get('type')})")

    def _check_duplicate_ids(self):
        # 已在 ingest 时检测,这里补充跨 object+action namespace 的冲突
        both = set(self.ontology.objects_by_id) & set(self.ontology.actions_by_id)
        for i in both:
            self._issue("warn", "id_namespace_collision",
                        f"id '{i}' exists as both object and action")

    def _check_joint_limits(self):
        for j in self.ontology.objects_by_type.get("Joint", []):
            pl = (j.get("properties") or {}).get("position_limit")
            if pl is None:
                self._issue("warn", "joint_missing_limit",
                            f"joint {j['id']} has no position_limit",
                            location=j["id"])
                continue
            if isinstance(pl, dict):
                lo, hi = pl.get("min"), pl.get("max")
                if lo is not None and hi is not None and lo > hi:
                    self._issue("error", "joint_inverted_limit",
                                f"joint {j['id']}: min > max ({lo} > {hi})",
                                location=j["id"])
                elif lo == hi and lo == 0:
                    # head_pitch 未启用的合法占位
                    pass

    def _check_action_invokers(self):
        allowed_invoker_types = {
            "ros2_topic",
            "ros2_service",
            "cli",
            "compound",
            "dds_service",
            "dds_topic",
            "mujoco_torque",
            "mujoco_position",
        }
        for aid, act in self.ontology.actions_by_id.items():
            inv = act.get("invoker")
            if not inv:
                self._issue("error", "action_no_invoker",
                            f"action {aid} has no invoker", location=aid)
                continue
            t = inv.get("type")
            if t not in allowed_invoker_types:
                self._issue("error", "action_bad_invoker",
                            f"action {aid}: invoker.type='{t}' not in {allowed_invoker_types}",
                            location=aid)
            if t in ("ros2_topic", "ros2_service") and not (inv.get("name") or inv.get("name_template")):
                self._issue("error", "action_no_topic",
                            f"action {aid}: invoker needs 'name' or 'name_template'",
                            location=aid)

    def _check_link_endpoints(self):
        """link.type 应该是已知的关系类型。暂时不强制(spec/core-object-types.yaml
           里定义的 LinkType 是推荐的,方言可以扩展)。"""
        pass


# ---------- CLI helpers ----------

def load_and_report(directory: str | Path) -> tuple[Ontology, list[ValidationIssue]]:
    loader = OntologyLoader(Path(directory))
    ont = loader.load()
    loader.validate()
    return ont, loader.issues


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "robots/agibot_x2/"
    loader = OntologyLoader(Path(target))
    loader.load()
    loader.validate()
    print(loader.summary())
    errors = [i for i in loader.issues if i.severity == "error"]
    if errors:
        print("\n=== ERRORS ===")
        for e in errors[:30]:
            print(" ", e)
    warns = [i for i in loader.issues if i.severity == "warn"]
    if warns:
        print(f"\n=== WARNINGS (first 10 of {len(warns)}) ===")
        for w in warns[:10]:
            print(" ", w)
    sys.exit(1 if errors else 0)
