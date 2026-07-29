"""PackModule 0.9 的规范模型、迁移、前端与 3.0 链接验收。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from roboonto.compat import LegacyPackMigrator
from roboonto.importers.sdk_code import SdkCodeImporter
from roboonto.importers.urdf import URDFImporter
from roboonto.pack import (
    PackLinkError,
    PackRequirements,
    dump_pack,
    link_pack,
    load_pack,
)


def test_x2_one_time_migration_is_closed_and_deterministic(
    x2_dir: Path, tmp_path: Path
):
    first = LegacyPackMigrator().migrate(x2_dir)
    second = LegacyPackMigrator().migrate(x2_dir)

    assert first.source_counts == {
        "objects": 256,
        "relations": 403,
        "actions": 22,
    }
    assert first.pack.to_data(include_digest=False) == second.pack.to_data(
        include_digest=False
    )
    assert len(first.pack.entities) == 242
    assert len(first.pack.capabilities) == 11
    assert len(first.pack.relations) == 403
    assert len(first.pack.target_actions) == 22
    assert all(
        "*" not in member
        for resource_set in first.pack.resource_sets
        for member in resource_set.members
    )
    assert all(action.world_effect is None for action in first.pack.target_actions)
    assert all(action.visibility == "executor" for action in first.pack.target_actions)

    output = tmp_path / "x2.pack.yaml"
    finalized = dump_pack(first.pack, output)
    reloaded = load_pack(output)
    assert reloaded.module.content_digest == finalized.module.content_digest
    assert reloaded.count() == finalized.count()


def test_migration_fails_closed_on_missing_legacy_resources(x2_dir: Path):
    pack = LegacyPackMigrator().migrate(x2_dir).pack
    actions = {item.legacy_id: item for item in pack.target_actions}

    assert not actions["set_hand_command"].executable
    assert not actions["play_tts"].executable
    assert actions["set_joint_position"].executable
    assert actions["set_joint_position"].guards[-1].formula.node["namespace"] == (
        "pack_query"
    )


def test_digest_tampering_is_rejected(x2_dir: Path, tmp_path: Path):
    output = tmp_path / "x2.pack.json"
    dump_pack(LegacyPackMigrator().migrate(x2_dir).pack, output)
    document = json.loads(output.read_text(encoding="utf-8"))
    document["module"]["model"] = "tampered"
    output.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(ValueError, match="digest mismatch"):
        load_pack(output)


def test_roboonto3_link_uses_exact_pack_version_and_digest(
    x2_dir: Path, tmp_path: Path
):
    output = tmp_path / "x2.pack.yaml"
    dump_pack(LegacyPackMigrator().migrate(x2_dir).pack, output)
    pack = load_pack(output)
    requirements = PackRequirements(
        pack_id="agibot_x2",
        pack_version="0.9.0",
        content_digest=pack.module.content_digest,
        capabilities=("agibot_x2.cap.tactile_head_events",),
        target_actions=("agibot_x2.action.delete_input_source",),
    )

    linked = link_pack(pack, requirements).to_data()
    assert linked["link_kind"] == "roboonto3_pack_link"
    assert linked["pack"]["content_digest"] == pack.module.content_digest
    assert linked["target_actions"][0]["visibility"] == "executor"
    assert linked["target_actions"][0]["binding"]["protocol"]

    with pytest.raises(PackLinkError, match="requested version"):
        link_pack(
            pack,
            PackRequirements(pack_id="agibot_x2", pack_version="1.0.0"),
        )


def test_roboonto3_link_rejects_unqualified_observation(
    x2_dir: Path, tmp_path: Path
):
    output = tmp_path / "x2.pack.yaml"
    dump_pack(LegacyPackMigrator().migrate(x2_dir).pack, output)
    pack = load_pack(output)

    with pytest.raises(PackLinkError, match="freshness/evidence contract"):
        link_pack(
            pack,
            PackRequirements(
                pack_id="agibot_x2",
                pack_version="0.9.0",
                observations=("agibot_x2.observation.battery_state",),
            ),
        )


def test_urdf_importer_directly_returns_packmodule(tmp_path: Path):
    urdf = tmp_path / "minibot.urdf"
    urdf.write_text(
        """<robot name="minibot">
  <link name="base"/>
  <link name="arm"/>
  <joint name="arm_joint" type="revolute">
    <parent link="base"/><child link="arm"/>
    <axis xyz="0 0 1"/>
    <limit lower="-1" upper="1" velocity="2" effort="3"/>
  </joint>
</robot>
""",
        encoding="utf-8",
    )
    pack = URDFImporter("minibot").run(urdf)

    assert pack.module.id == "minibot"
    assert {item.type for item in pack.entities} == {"Link", "Joint"}
    assert len(pack.relations) == 1
    assert not (tmp_path / "kinematics.yaml").exists()


def test_sdk_importer_directly_returns_packmodule(tmp_path: Path):
    interface = tmp_path / "aimdk_msgs" / "interface" / "msg"
    interface.mkdir(parents=True)
    (interface / "Battery.msg").write_text("float64 voltage\n", encoding="utf-8")
    examples = tmp_path / "py_examples"
    examples.mkdir()
    (examples / "battery.py").write_text(
        "node.create_subscription(Battery, '/battery', callback, 10)\n",
        encoding="utf-8",
    )

    pack = SdkCodeImporter("minibot").run(tmp_path)

    assert pack.module.id == "minibot"
    assert any(item.type == "MsgSchema" for item in pack.entities)
    assert len(pack.bindings) == 1
    assert len(pack.observation_sources) == 1
    assert not (tmp_path / "interfaces.yaml").exists()


def test_pack_cli_migrate_validate_and_inspect(x2_dir: Path, tmp_path: Path):
    output = tmp_path / "x2.pack.yaml"
    migrate = _run_cli(
        "pack", "migrate", str(x2_dir), "-o", str(output)
    )
    assert migrate.returncode == 0, migrate.stderr
    assert "TargetAction=22" in migrate.stdout

    validate = _run_cli("pack", "validate", str(output))
    assert validate.returncode == 0, validate.stderr
    assert "有效 PackModule" in validate.stdout

    inspect = _run_cli("pack", "inspect", str(output), "--json")
    assert inspect.returncode == 0, inspect.stderr
    payload = json.loads(inspect.stdout)
    assert payload["counts"]["target_actions"] == 22
    assert payload["migration"]["blocking"] == 5


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "roboonto.cli", *args],
        capture_output=True,
        text=True,
    )
