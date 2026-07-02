"""Tests for the build session audit log."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from roboonto.build.session import BuildSession, RECOMMENDED_STEPS


# ── helpers ──────────────────────────────────────────────────────────

@pytest.fixture
def workdir(tmp_path: Path, minimal_valid_dir: Path) -> Path:
    """Copy the minimal_valid fixture into a tmp dir we can mutate."""
    dest = tmp_path / "minibot"
    shutil.copytree(minimal_valid_dir, dest)
    return dest


# ── lifecycle ────────────────────────────────────────────────────────

def test_init_creates_manifest_and_log(workdir: Path):
    sess = BuildSession(workdir)
    assert not sess.exists()
    sess.init(operator="alice")
    assert sess.exists()
    assert sess.manifest_path.exists()
    assert sess.log_path.exists()

    manifest = json.loads(sess.manifest_path.read_text())
    assert manifest["operator"] == "alice"
    assert manifest["recommended_steps"] == RECOMMENDED_STEPS
    assert manifest["completed_steps"] == []


def test_init_records_first_event(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    events = sess.tail(10)
    assert len(events) == 1
    assert events[0]["step"] == "init"
    assert events[0]["operator"] == "alice"
    assert events[0]["inputs_hash"]


def test_init_missing_dir_raises(tmp_path: Path):
    sess = BuildSession(tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        sess.init()


# ── audit recording ──────────────────────────────────────────────────

def test_run_step_with_no_command(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    rc = sess.run_step("hand_edit", note="manually edited actions.yaml")
    assert rc == 0
    events = sess.tail(10)
    assert events[-1]["step"] == "hand_edit"
    assert events[-1]["note"] == "manually edited actions.yaml"


def test_run_step_with_command(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    rc = sess.run_step("validate",
                       cmd=["python3", "-c", "print('hi')"])
    assert rc == 0
    events = sess.tail(10)
    last = events[-1]
    assert last["step"] == "validate"
    assert last["exit_code"] == 0
    assert "python3" in last["command"]
    assert last["duration_s"] is not None


def test_run_step_failing_command(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    rc = sess.run_step("validate",
                       cmd=["python3", "-c", "import sys; sys.exit(2)"])
    assert rc == 2
    events = sess.tail(10)
    assert events[-1]["exit_code"] == 2
    # Failed steps not added to completed_steps
    manifest = json.loads(sess.manifest_path.read_text())
    assert "validate" not in manifest["completed_steps"]


def test_completed_steps_are_recorded(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    sess.run_step("hand_edit", note="ok")
    sess.run_step("validate", cmd=["python3", "-c", "pass"])
    manifest = json.loads(sess.manifest_path.read_text())
    assert "hand_edit" in manifest["completed_steps"]
    assert "validate" in manifest["completed_steps"]


# ── change detection ─────────────────────────────────────────────────

def test_file_changes_recorded(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")

    target = workdir / "actions.yaml"
    target.write_text(target.read_text() + "\n# touched\n", encoding="utf-8")

    rc = sess.run_step("hand_edit", note="appended comment")
    assert rc == 0
    events = sess.tail(10)
    last = events[-1]
    changed = [c["file"] for c in last["files_changed"]]
    assert "actions.yaml" in changed
    assert last["inputs_hash"] != last["outputs_hash"]


def test_status_reports_session_state(workdir: Path):
    sess = BuildSession(workdir)
    sess.init(operator="alice")
    sess.run_step("hand_edit", note="x")
    status = sess.status()
    assert status["operator"] == "alice"
    assert "hand_edit" in status["steps_seen"]
    assert status["events"] >= 2
    assert status["last_event"]["step"] == "hand_edit"
