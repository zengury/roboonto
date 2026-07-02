"""Tests for agent_runtime.learning.rollout — the simulator integration.

Mostly fast smoke tests (≤ 3 episodes each). Skipped if mujoco/gymnasium
not installed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

mujoco = pytest.importorskip("mujoco")
gym = pytest.importorskip("gymnasium")

from agent_runtime.learning.rollout import (  # noqa: E402
    RolloutConfig,
    RolloutRunner,
    load_policy,
)


HALFCHEETAH_DIR = Path(__file__).resolve().parent.parent / "robots" / "halfcheetah"


# ── policy loader ────────────────────────────────────────────────────

def test_load_policy_returns_callable():
    fn, params = load_policy(HALFCHEETAH_DIR, "gait")
    assert callable(fn)
    assert "trot" in params
    assert params["policy_kind"] == "programmatic"


def test_load_unknown_policy_raises():
    with pytest.raises(FileNotFoundError):
        load_policy(HALFCHEETAH_DIR, "no_such_policy")


# ── single-seed rollout (deterministic) ──────────────────────────────

def test_single_seed_rollout_produces_episode_result():
    cfg = RolloutConfig(seeds=[42], horizon_steps=200,
                        write_ledger=False, write_manas=False)
    summary = RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    assert summary.n == 1
    er = summary.episode_results[0]
    assert er.seed == 42
    assert er.steps > 0
    assert er.wall_time_s > 0
    assert er.body_pitch_max_abs >= 0


def test_three_seed_rollout_reward_distribution():
    cfg = RolloutConfig(seeds=[0, 1, 2], horizon_steps=500,
                        write_ledger=False, write_manas=False)
    summary = RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    assert summary.n == 3
    # The PD/sinusoidal baseline is positive on most seeds
    assert summary.reward_mean > 0
    # Termination breakdown is meaningful
    assert sum(summary.termination_breakdown.values()) == 3


# ── ledger writing ──────────────────────────────────────────────────

def test_rollout_writes_to_ledger(tmp_path):
    cfg = RolloutConfig(
        seeds=[42],
        horizon_steps=100,
        write_ledger=True,
        ledger_path=str(tmp_path / "ledger.db"),
        write_manas=False,
    )
    RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    import sqlite3
    conn = sqlite3.connect(tmp_path / "ledger.db")
    n = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert n > 0
    # Should be at most 100 events (one per step)
    assert n <= 100
    # Each event has non-empty data_json
    sample = conn.execute(
        "SELECT data_json FROM events LIMIT 1"
    ).fetchone()[0]
    assert "forward_velocity" in sample
    conn.close()


# ── manas writing ───────────────────────────────────────────────────

def test_rollout_writes_to_manas(tmp_path):
    cfg = RolloutConfig(
        seeds=[10, 20, 30],
        horizon_steps=200,
        write_ledger=False,
        write_manas=True,
        manas_root=str(tmp_path / "manas"),
    )
    RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    import sqlite3
    conn = sqlite3.connect(tmp_path / "manas" / "manas.db")
    n = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    assert n == 3
    # Each episode has a 'task' kind reflection
    rows = conn.execute("SELECT kind, what FROM episodes").fetchall()
    assert all(kind == "task" for kind, _ in rows)
    assert all("halfcheetah" in what for _, what in rows)
    conn.close()


# ── reproducibility ─────────────────────────────────────────────────

def test_same_seed_gives_same_reward():
    cfg = RolloutConfig(seeds=[7], horizon_steps=200,
                        write_ledger=False, write_manas=False)
    a = RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    b = RolloutRunner(HALFCHEETAH_DIR, "gait", cfg).run()
    assert abs(a.reward_mean - b.reward_mean) < 1e-6
