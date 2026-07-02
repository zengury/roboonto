"""End-to-end tests for the roboonto CLI.

Each test runs `python -m roboonto.cli <subcmd>` in a subprocess so we
exercise argparse, command routing, and stdout formatting just like a
real user would. Stays under a few seconds total.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "roboonto.cli", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True, text=True,
    )


# ── basic commands on X2 ─────────────────────────────────────────────

def test_validate_x2(x2_dir: Path):
    cp = run_cli("validate", str(x2_dir))
    assert cp.returncode == 0, cp.stderr
    assert "agibot_x2" in cp.stdout
    assert "0 errors" in cp.stdout


def test_query_objects(x2_dir: Path):
    cp = run_cli("query", str(x2_dir), "objects", "Mode")
    assert cp.returncode == 0, cp.stderr
    parsed = json.loads(cp.stdout)
    assert isinstance(parsed, list)
    assert any(o.get("type") == "Mode" for o in parsed)


def test_query_agent_affordances(x2_dir: Path):
    cp = run_cli("query", str(x2_dir), "agent-affordances", "navigation")
    assert cp.returncode == 0, cp.stderr
    parsed = json.loads(cp.stdout)
    assert parsed[0]["id"] == "agibot_x2.cap.locomotion_velocity_control"
    assert {a["id"] for a in parsed[0]["actions"]} >= {
        "set_forward_velocity",
        "set_lateral_velocity",
        "set_angular_velocity",
    }


def test_infer_capabilities_outputs_reviewable_draft(minimal_valid_dir: Path):
    cp = run_cli("infer-capabilities", str(minimal_valid_dir))
    assert cp.returncode == 0, cp.stderr
    parsed = json.loads(cp.stdout)
    assert "objects" in parsed and "links" in parsed
    assert any(o["type"] == "Capability" for o in parsed["objects"])


def test_check_action_ok(x2_dir: Path):
    state = json.dumps({
        "mc_action": "LOCOMOTION_DEFAULT",
        "is_moving": True,
        "registered_input_sources": ["agent"],
    })
    params = json.dumps({"forward_velocity": 0.5, "source": "agent"})
    cp = run_cli("check-action", str(x2_dir),
                 "set_forward_velocity", "--params", params, "--state", state)
    assert cp.returncode == 0, cp.stdout + cp.stderr


def test_check_action_blocked(x2_dir: Path):
    state = json.dumps({"mc_action": "PASSIVE_DEFAULT"})
    cp = run_cli("check-action", str(x2_dir),
                 "set_preset_motion",
                 "--params", '{"motion": 1002, "area": 2, "source": "agent"}',
                 "--state", state)
    assert cp.returncode != 0


# ── readiness ────────────────────────────────────────────────────────

def test_readiness_x2_human(x2_dir: Path):
    cp = run_cli("readiness", str(x2_dir))
    assert cp.returncode == 0
    assert "RoboOnto Readiness" in cp.stdout
    assert "agibot_x2" in cp.stdout
    assert "Grade:" in cp.stdout


def test_readiness_x2_json(x2_dir: Path):
    cp = run_cli("readiness", str(x2_dir), "--json")
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    assert payload["robot_id"] == "agibot_x2"
    assert payload["profile"] == "customer_v1"
    assert "results" in payload


def test_readiness_minimal_customer_ready(minimal_valid_dir: Path):
    cp = run_cli("readiness", str(minimal_valid_dir), "--json")
    assert cp.returncode == 0
    payload = json.loads(cp.stdout)
    assert payload["grade"] == "customer-ready"


def test_readiness_template_fails(template_dir: Path):
    cp = run_cli("readiness", str(template_dir), "--json")
    payload = json.loads(cp.stdout)
    assert payload["grade"] == "fail"


def test_readiness_require_gate(minimal_valid_dir: Path):
    cp = run_cli("readiness", str(minimal_valid_dir),
                 "--require", "customer-ready")
    assert cp.returncode == 0


def test_readiness_require_gate_blocks(template_dir: Path):
    cp = run_cli("readiness", str(template_dir),
                 "--require", "beta")
    assert cp.returncode != 0
    assert "FAIL" in cp.stderr or "FAIL" in cp.stdout


# ── build session ────────────────────────────────────────────────────

def test_build_init_and_status(tmp_path: Path, minimal_valid_dir: Path):
    workdir = tmp_path / "minibot"
    shutil.copytree(minimal_valid_dir, workdir)

    init = run_cli("build", "init", str(workdir), "--operator", "tester")
    assert init.returncode == 0
    assert (workdir / ".build" / "manifest.json").exists()

    status = run_cli("build", "status", str(workdir))
    assert status.returncode == 0
    payload = json.loads(status.stdout)
    assert payload["operator"] == "tester"
    assert payload["events"] >= 1


def test_build_status_without_init_fails(tmp_path: Path, minimal_valid_dir: Path):
    workdir = tmp_path / "minibot2"
    shutil.copytree(minimal_valid_dir, workdir)
    cp = run_cli("build", "status", str(workdir))
    assert cp.returncode != 0
    assert "no build session" in cp.stderr


def test_build_run_records_audit(tmp_path: Path, minimal_valid_dir: Path):
    workdir = tmp_path / "minibot3"
    shutil.copytree(minimal_valid_dir, workdir)

    run_cli("build", "init", str(workdir), "--operator", "tester")
    run_cli("build", "run", str(workdir), "validate",
            "--", sys.executable, "-m", "roboonto.cli", "validate", str(workdir))

    log = run_cli("build", "log", str(workdir), "--limit", "10")
    assert log.returncode == 0
    lines = [json.loads(l) for l in log.stdout.strip().splitlines() if l.strip()]
    assert any(e["step"] == "validate" for e in lines)
    validate_event = next(e for e in lines if e["step"] == "validate")
    assert validate_event["exit_code"] == 0
    assert "validate" in validate_event["command"]
