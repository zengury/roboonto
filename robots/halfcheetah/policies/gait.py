"""Half-Cheetah Trot Gait — Phase 1 baseline (sinusoidal feedforward + optional PD).

Pure function: (observation, params, t) → action ∈ [-1, 1]^6
No hidden state; all parameters live in gait.yaml.

The 17-dim observation layout (gymnasium HalfCheetah-v5):
  obs[0]   z position of root
  obs[1]   pitch of root (rooty)
  obs[2:8] joint positions: bthigh, bshin, bfoot, fthigh, fshin, ffoot
  obs[8]   x velocity of root
  obs[9]   z velocity of root
  obs[10]  pitch velocity of root
  obs[11:17] joint velocities

Action: 6-dim torque vector clamped to [-1, 1] per actuator.

LLM in Phase 2 may freely edit:
  - gait.yaml (any value, including the joint_phase_offsets table)
  - this file's structure (add modes, change feedback laws, add gaits)
But the public function signature `trot_controller(obs, params, t) → ndarray(6)`
must remain stable so the rollout runner can call it.
"""

from __future__ import annotations

import math
import numpy as np


# Observation layout — kept as named constants so LLM patches stay readable
OBS_Z, OBS_PITCH = 0, 1
OBS_JOINT_Q_START, OBS_JOINT_Q_END = 2, 8                # 6 joint positions
OBS_X_VEL, OBS_Z_VEL, OBS_PITCH_VEL = 8, 9, 10
OBS_JOINT_QDOT_START, OBS_JOINT_QDOT_END = 11, 17        # 6 joint velocities

# Joint order matches MuJoCo actuator order
JOINTS = ["bthigh", "bshin", "bfoot", "fthigh", "fshin", "ffoot"]


def trot_controller(obs: np.ndarray, params: dict, t: float) -> np.ndarray:
    """Compute 6-dim normalized torque vector.

    Args:
        obs:    17-dim observation from gymnasium HalfCheetah-v5
        params: dict loaded from gait.yaml
        t:      simulator time in seconds (cumulative across an episode)

    Returns:
        ndarray of shape (6,), values in [-1, 1].
    """
    trot = params["trot"]
    omega = 2.0 * math.pi * trot["frequency_hz"] * t
    amp = trot["amplitude"]

    # Sinusoidal feedforward
    offsets = params["joint_phase_offsets"]
    feedforward = np.array([
        amp * math.sin(omega + offsets[j]) for j in JOINTS
    ])

    action = feedforward

    # Optional PD correction layer (off by default)
    pd = params.get("pd_correction", {})
    if pd.get("enabled"):
        q = obs[OBS_JOINT_Q_START:OBS_JOINT_Q_END]
        qdot = obs[OBS_JOINT_QDOT_START:OBS_JOINT_QDOT_END]
        targets = np.array([
            pd["joint_targets_q"][j] for j in JOINTS
        ])
        correction = pd["kp"] * (targets - q) - pd["kd"] * qdot
        action = action + correction

    scale = params.get("output_scale", 1.0)
    return np.clip(action * scale, -1.0, 1.0)


def info(params: dict) -> dict:
    """Return a small summary the proposer/evaluator can read for context."""
    return {
        "policy_kind": "programmatic_sinusoidal_feedforward",
        "modes": [params.get("mode_default", "TROT")],
        "tunable_keys": list(_walk_keys(params)),
    }


def _walk_keys(d, prefix=""):
    out = []
    for k, v in (d or {}).items():
        full = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.extend(_walk_keys(v, full))
        else:
            out.append(full)
    return out
