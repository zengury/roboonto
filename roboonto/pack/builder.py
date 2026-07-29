"""Shared PackModule construction helpers for all frontends."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping

from .model import Attribute, TypeRef, TypedValue


_UNIT_DIMENSIONS = {
    "m": "length",
    "cm": "length",
    "kg": "mass",
    "rad": "angle",
    "deg": "angle",
    "rad/s": "angular_velocity",
    "m/s": "velocity",
    "m/s²": "acceleration",
    "m/s^2": "acceleration",
    "Nm": "torque",
    "Hz": "frequency",
    "ms": "duration",
    "s": "duration",
    "V": "voltage",
    "A": "current",
    "Wh": "energy",
    "GB": "storage",
}


def type_ref_from_legacy(spec: Mapping[str, Any] | str | None) -> TypeRef:
    """Translate a legacy property/parameter declaration without guessing effects."""

    if spec is None:
        return TypeRef("opaque", name="unspecified")
    if isinstance(spec, str):
        kind = spec
        data: Mapping[str, Any] = {}
    else:
        kind = str(spec.get("kind") or spec.get("type") or "opaque")
        data = spec
    unit = str(data.get("unit", ""))
    if kind in {"float", "int"} and unit:
        return TypeRef(
            "quantity",
            name=str(data.get("dimension") or _UNIT_DIMENSIONS.get(unit, "physical")),
            unit=unit,
            frame=str(data.get("frame", "")),
        )
    if kind in {"string", "int", "float", "bool"}:
        return TypeRef(kind)
    if kind == "enum":
        return TypeRef("enum", values=tuple(str(item) for item in data.get("values", ())))
    if kind in {"ref", "entity"}:
        return TypeRef("entity", name=str(data.get("target") or data.get("name") or "Entity"))
    if kind in {"ref_list"}:
        return TypeRef(
            "list",
            item=TypeRef("entity", name=str(data.get("target") or "Entity")),
        )
    if kind in {"list", "array"}:
        item = data.get("item")
        return TypeRef(
            "list",
            item=type_ref_from_legacy(item) if item is not None else TypeRef("opaque", name="item"),
        )
    if kind in {"range", "quantity"}:
        return TypeRef(
            "range" if kind == "range" else "quantity",
            name=str(data.get("dimension") or _UNIT_DIMENSIONS.get(unit, "physical")),
            unit=unit or str(data.get("default_unit", "")),
            frame=str(data.get("frame", "")),
        )
    if kind in {"map", "record", "frame_spec", "matrix3x3", "vector3", "quaternion"}:
        return TypeRef("record", name=kind)
    if kind == "any":
        return TypeRef("opaque", name="any")
    return TypeRef("opaque", name=kind)


def typed_value(
    value: Any,
    hint: Mapping[str, Any] | TypeRef | None = None,
) -> TypedValue:
    """Convert arbitrary frontend data into the closed recursive value model."""

    type_ref = (
        hint
        if isinstance(hint, TypeRef)
        else type_ref_from_legacy(hint) if hint is not None else None
    )
    if value is None:
        return TypedValue("null")
    if isinstance(value, bool):
        return TypedValue("bool", value)
    if isinstance(value, int) and not isinstance(value, bool):
        if type_ref and type_ref.kind == "quantity":
            return TypedValue(
                "quantity", value, unit=type_ref.unit, frame=type_ref.frame
            )
        return TypedValue("int", value)
    if isinstance(value, float):
        if type_ref and type_ref.kind == "quantity":
            return TypedValue(
                "quantity", value, unit=type_ref.unit, frame=type_ref.frame
            )
        return TypedValue("float", value)
    if isinstance(value, (date, datetime)):
        return TypedValue("string", value.isoformat())
    if isinstance(value, str):
        if type_ref and type_ref.kind == "entity":
            return TypedValue("ref", value, target_type=type_ref.name)
        return TypedValue("string", value)
    if isinstance(value, (list, tuple)):
        item_hint = type_ref.item if type_ref and type_ref.kind == "list" else None
        return TypedValue(
            "list",
            items=tuple(typed_value(item, item_hint) for item in value),
        )
    if isinstance(value, Mapping):
        if {"min", "max"}.issubset(value):
            return TypedValue(
                "range",
                (value.get("min"), value.get("max")),
                unit=str(value.get("unit") or (type_ref.unit if type_ref else "")),
                frame=str(value.get("frame") or (type_ref.frame if type_ref else "")),
            )
        if "value" in value and set(value).issubset({"value", "unit", "frame"}):
            return TypedValue(
                "quantity" if value.get("unit") else _scalar_kind(value["value"]),
                value["value"],
                unit=str(value.get("unit", "")),
                frame=str(value.get("frame", "")),
            )
        return TypedValue(
            "record",
            fields=tuple(
                Attribute(str(key), typed_value(item))
                for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            ),
        )
    return TypedValue("string", str(value))


def attributes_from_mapping(
    values: Mapping[str, Any] | None,
    definitions: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    exclude: set[str] | None = None,
) -> tuple[Attribute, ...]:
    definitions = definitions or {}
    excluded = exclude or set()
    return tuple(
        Attribute(
            str(name),
            typed_value(value, definitions.get(str(name))),
        )
        for name, value in sorted((values or {}).items(), key=lambda pair: str(pair[0]))
        if str(name) not in excluded
    )


def _scalar_kind(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    return "string"
