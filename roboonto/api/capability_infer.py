"""Capability draft inference from existing actions and interfaces.

This is intentionally conservative: it creates reviewable drafts instead of
pretending to know the final domain semantics.
"""

from __future__ import annotations

from .loader import Ontology


def infer_capability_drafts(ontology: Ontology) -> dict:
    """Infer a small capabilities.yaml draft from action groups.

    The output is a valid shard shape: {"objects": [...], "links": [...]}.
    Callers can dump it to YAML or review it in JSON.
    """
    groups: dict[str, dict] = {}
    for action_id, action in ontology.actions_by_id.items():
        kind = _kind_for_action(action_id, action)
        group = groups.setdefault(kind["id"], {
            "capability": {
                "type": "Capability",
                "id": f"{ontology.robot_id}.cap.{kind['id']}",
                "properties": {
                    "name_human": kind["name"],
                    "capability_kind": kind["capability_kind"],
                    "description": kind["description"],
                    "produces": kind["produces"],
                    "boundaries": ["review_required: inferred from actions.yaml"],
                    "standard_mappings": [
                        {"standard": "RoSO", "term": "Function"},
                    ],
                },
                "source": {"type": "inferred", "locator": "actions.yaml"},
            },
            "actions": [],
        })
        group["actions"].append(action_id)

    objects = [g["capability"] for g in groups.values()]
    links = []
    for group in groups.values():
        cap_id = group["capability"]["id"]
        for action_id in sorted(group["actions"]):
            links.append({"type": "exposed_via", "source": cap_id, "target": action_id})
            for iface_id in _interfaces_for_action(ontology, action_id):
                links.append({"type": "exposed_via", "source": cap_id, "target": iface_id})

    return {"objects": objects, "links": links}


def _kind_for_action(action_id: str, action: dict) -> dict:
    text = f"{action_id} {action.get('description', '')}".lower()
    safety = action.get("safety_class")
    if "velocity" in text or "locomotion" in text:
        return _kind("locomotion_control", "Locomotion control", "navigation",
                     "Command base walking velocity.", ["base_motion"])
    if "joint" in text:
        return _kind("joint_control", "Joint control", "actuation",
                     "Command or observe robot joint state.", ["joint_motion", "joint_state"])
    if "hand" in text or "gripper" in text:
        return _kind("hand_manipulation", "Hand manipulation", "manipulation",
                     "Command or observe end effector state.", ["hand_motion", "grasp_state"])
    if "tts" in text or "media" in text or "volume" in text or "mute" in text:
        return _kind("speech_output", "Speech and media output", "interaction",
                     "Play audio and configure speech/media output.", ["speech_audio"])
    if "input_source" in text or "source" in text:
        return _kind("input_source_arbitration", "Input source arbitration", "communication",
                     "Manage control input sources and priority.", ["input_source_state"])
    if "mode" in text or "mc_action" in text:
        return _kind("mode_management", "Mode management", "planning",
                     "Query and switch robot operating mode.", ["current_mode"])
    if safety in {"MOTION", "POWER", "IRREVERSIBLE"}:
        return _kind("motion_execution", "Motion execution", "actuation",
                     "Execute motion-class actions.", ["motion"])
    return _kind("information_or_configuration", "Information and configuration", "diagnosis",
                 "Read or configure robot state.", ["state"])


def _kind(id_: str, name: str, capability_kind: str, description: str, produces: list[str]) -> dict:
    return {
        "id": id_,
        "name": name,
        "capability_kind": capability_kind,
        "description": description,
        "produces": produces,
    }


def _interfaces_for_action(ontology: Ontology, action_id: str) -> list[str]:
    out = []
    for link in ontology.links_by_type.get("invokes_via", []):
        if link.get("source") == action_id and link.get("target"):
            out.append(link["target"])
    return out
