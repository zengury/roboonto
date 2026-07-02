"""
roboonto.core.type_registry — Single source of truth for ontology type → category/color mapping.

Every module that needs type classification imports from here.
Adding a new object type requires only ONE edit.
"""
from __future__ import annotations

# (category, color) per ontology object type
TYPE_CATEGORY: dict[str, tuple[str, str]] = {
    "ComputeUnit": ("hardware", "#ff6b6b"),
    "PowerSubsystem": ("hardware", "#ff6b6b"),
    "Sensor": ("hardware", "#ff6b6b"),
    "RobotBody": ("hardware", "#ff6b6b"),
    "ProtectionThreshold": ("hardware", "#ff6b6b"),
    "Joint": ("hardware", "#ff6b6b"),
    "Link": ("hardware", "#ff6b6b"),
    "Topic": ("interface", "#4dd0e1"),
    "Service": ("interface", "#4dd0e1"),
    "MsgSchema": ("interface", "#4dd0e1"),
    "Mode": ("behavior", "#ffd54f"),
    "PresetMotion": ("behavior", "#ffd54f"),
    "InputSource": ("meta", "#90a4ae"),
    "PriorityLevel": ("meta", "#90a4ae"),
    "ControlLoop": ("behavior", "#ffd54f"),
    "StatusBit": ("event", "#ff9800"),
    "FaultCode": ("event", "#ff9800"),
    "TouchEvent": ("event", "#ff9800"),
}

CATEGORY_COLORS: dict[str, str] = {
    "hardware": "#ff6b6b",
    "interface": "#4dd0e1",
    "behavior": "#ffd54f",
    "event": "#ff9800",
    "meta": "#90a4ae",
    "action": "#ec407a",
}

def get_category(otype: str) -> str:
    return TYPE_CATEGORY.get(otype, ("hardware", "#888"))[0]

def get_color(otype: str) -> str:
    return TYPE_CATEGORY.get(otype, ("hardware", "#888"))[1]
