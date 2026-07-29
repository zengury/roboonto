"""Typed semantic model for RoboOnto Target PackModule 0.9.

The model deliberately rejects the legacy pack's open ``properties`` maps,
wildcard resource references, string predicates, and implicit bindings.
Canonical YAML and JSON are merely serializations of these nodes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


PACK_SCHEMA = "https://roboonto.dev/schema/packmodule-0.9.json"
PACK_VERSION = "0.9"


class PackValidationError(ValueError):
    """Raised when a PackModule violates canonical static semantics."""

    def __init__(self, issues: Iterable[str]):
        self.issues = tuple(issues)
        super().__init__("invalid PackModule:\n- " + "\n- ".join(self.issues))


@dataclass(frozen=True)
class TypeRef:
    """A type used by entity attributes, parameters, and observations."""

    kind: str
    name: str = ""
    unit: str = ""
    frame: str = ""
    values: tuple[str, ...] = ()
    item: "TypeRef | None" = None

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.name:
            out["dimension" if self.kind in {"quantity", "range"} else "name"] = self.name
        if self.unit:
            out["unit"] = self.unit
        if self.frame:
            out["frame"] = self.frame
        if self.values:
            out["values"] = list(self.values)
        if self.item is not None:
            out["item"] = self.item.to_data()
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "TypeRef":
        item = data.get("item")
        return cls(
            kind=str(data["kind"]),
            name=str(data.get("dimension") or data.get("name", "")),
            unit=str(data.get("unit", "")),
            frame=str(data.get("frame", "")),
            values=tuple(str(value) for value in data.get("values", ())),
            item=cls.from_data(item) if isinstance(item, Mapping) else None,
        )


@dataclass(frozen=True)
class TypedValue:
    """A recursively typed value; no free-form mapping is permitted."""

    kind: str
    value: Any = None
    unit: str = ""
    frame: str = ""
    target_type: str = ""
    items: tuple["TypedValue", ...] = ()
    fields: tuple["Attribute", ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind in {"null"}:
            return out
        if self.kind in {"list"}:
            out["items"] = [item.to_data() for item in self.items]
            return out
        if self.kind == "record":
            out["fields"] = [item.to_data() for item in self.fields]
            return out
        if self.kind == "range":
            out["min"] = self.value[0]
            out["max"] = self.value[1]
        else:
            out["value"] = self.value
        if self.unit:
            out["unit"] = self.unit
        if self.frame:
            out["frame"] = self.frame
        if self.target_type:
            out["target_type"] = self.target_type
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "TypedValue":
        kind = str(data["kind"])
        if kind == "list":
            return cls(
                kind=kind,
                items=tuple(cls.from_data(item) for item in data.get("items", ())),
            )
        if kind == "record":
            return cls(
                kind=kind,
                fields=tuple(Attribute.from_data(item) for item in data.get("fields", ())),
            )
        value: Any
        if kind == "range":
            value = (data.get("min"), data.get("max"))
        else:
            value = data.get("value")
        return cls(
            kind=kind,
            value=value,
            unit=str(data.get("unit", "")),
            frame=str(data.get("frame", "")),
            target_type=str(data.get("target_type", "")),
        )


@dataclass(frozen=True)
class Attribute:
    name: str
    value: TypedValue

    def to_data(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value.to_data()}

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Attribute":
        return cls(str(data["name"]), TypedValue.from_data(data["value"]))


@dataclass(frozen=True)
class Provenance:
    id: str
    kind: str
    locator: str
    extractor: str = ""
    extracted_at: str = ""
    confidence: float | None = None
    notes: str = ""
    attributes: tuple[Attribute, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "locator": self.locator,
        }
        if self.extractor:
            out["extractor"] = self.extractor
        if self.extracted_at:
            out["extracted_at"] = self.extracted_at
        if self.confidence is not None:
            out["confidence"] = self.confidence
        if self.notes:
            out["notes"] = self.notes
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Provenance":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            locator=str(data["locator"]),
            extractor=str(data.get("extractor", "")),
            extracted_at=str(data.get("extracted_at", "")),
            confidence=(
                float(data["confidence"]) if isinstance(data.get("confidence"), (int, float)) else None
            ),
            notes=str(data.get("notes", "")),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
        )


@dataclass(frozen=True)
class EntityType:
    id: str
    category: str
    extends: str = ""
    description: str = ""
    attributes: tuple[tuple[str, TypeRef, bool], ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "category": self.category}
        if self.extends:
            out["extends"] = self.extends
        if self.description:
            out["description"] = self.description
        if self.attributes:
            out["attributes"] = [
                {"name": name, "type": type_ref.to_data(), "required": required}
                for name, type_ref, required in self.attributes
            ]
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "EntityType":
        return cls(
            id=str(data["id"]),
            category=str(data["category"]),
            extends=str(data.get("extends", "")),
            description=str(data.get("description", "")),
            attributes=tuple(
                (
                    str(item["name"]),
                    TypeRef.from_data(item["type"]),
                    bool(item.get("required", False)),
                )
                for item in data.get("attributes", ())
            ),
        )


@dataclass(frozen=True)
class Entity:
    id: str
    type: str
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "type": self.type}
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Entity":
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class Relation:
    id: str
    predicate: str
    source: str
    target: str
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "predicate": self.predicate,
            "source": self.source,
            "target": self.target,
        }
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Relation":
        return cls(
            id=str(data["id"]),
            predicate=str(data["predicate"]),
            source=str(data["source"]),
            target=str(data["target"]),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class RelationType:
    id: str
    source_types: tuple[str, ...]
    target_types: tuple[str, ...]

    def to_data(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_types": list(self.source_types),
            "target_types": list(self.target_types),
        }

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "RelationType":
        return cls(
            id=str(data["id"]),
            source_types=tuple(str(item) for item in data.get("source_types", ())),
            target_types=tuple(str(item) for item in data.get("target_types", ())),
        )


@dataclass(frozen=True)
class Formula:
    """A structured, non-executable formula tree."""

    node: Mapping[str, Any]

    def to_data(self) -> dict[str, Any]:
        return _copy_formula(self.node)

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Formula":
        return cls(_copy_formula(data))


@dataclass(frozen=True)
class Guard:
    formula: Formula
    code: str
    message: str
    severity: str = "error"

    def to_data(self) -> dict[str, Any]:
        return {
            "formula": self.formula.to_data(),
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Guard":
        return cls(
            formula=Formula.from_data(data["formula"]),
            code=str(data["code"]),
            message=str(data["message"]),
            severity=str(data.get("severity", "error")),
        )


@dataclass(frozen=True)
class Parameter:
    name: str
    type: TypeRef
    required: bool = True
    default: TypedValue | None = None
    constraints: tuple[TypedValue, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "name": self.name,
            "type": self.type.to_data(),
            "required": self.required,
        }
        if self.default is not None:
            out["default"] = self.default.to_data()
        if self.constraints:
            out["constraints"] = [item.to_data() for item in self.constraints]
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Parameter":
        default = data.get("default")
        return cls(
            name=str(data["name"]),
            type=TypeRef.from_data(data["type"]),
            required=bool(data.get("required", True)),
            default=TypedValue.from_data(default) if isinstance(default, Mapping) else None,
            constraints=tuple(
                TypedValue.from_data(item) for item in data.get("constraints", ())
            ),
        )


@dataclass(frozen=True)
class Binding:
    id: str
    provider: str
    protocol: str
    endpoint: str
    message_type: str = ""
    request_type: str = ""
    response_type: str = ""
    delivery_semantics: str = "request_response"
    acceptance_source: str = ""
    argument_mapping: tuple[tuple[str, str], ...] = ()
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "provider": self.provider,
            "protocol": self.protocol,
            "endpoint": self.endpoint,
            "delivery_semantics": self.delivery_semantics,
        }
        if self.message_type:
            out["message_type"] = self.message_type
        if self.request_type:
            out["request_type"] = self.request_type
        if self.response_type:
            out["response_type"] = self.response_type
        if self.acceptance_source:
            out["acceptance_source"] = self.acceptance_source
        if self.argument_mapping:
            out["argument_mapping"] = [
                {"argument": argument, "target": target}
                for argument, target in self.argument_mapping
            ]
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Binding":
        return cls(
            id=str(data["id"]),
            provider=str(data["provider"]),
            protocol=str(data["protocol"]),
            endpoint=str(data["endpoint"]),
            message_type=str(data.get("message_type", "")),
            request_type=str(data.get("request_type", "")),
            response_type=str(data.get("response_type", "")),
            delivery_semantics=str(data.get("delivery_semantics", "request_response")),
            acceptance_source=str(data.get("acceptance_source", "")),
            argument_mapping=tuple(
                (str(item["argument"]), str(item["target"]))
                for item in data.get("argument_mapping", ())
            ),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class ResourceSet:
    id: str
    members: tuple[str, ...]
    purpose: str = ""

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {"id": self.id, "members": list(self.members)}
        if self.purpose:
            out["purpose"] = self.purpose
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "ResourceSet":
        return cls(
            id=str(data["id"]),
            members=tuple(str(item) for item in data.get("members", ())),
            purpose=str(data.get("purpose", "")),
        )


@dataclass(frozen=True)
class TargetAction:
    id: str
    binding: str
    legacy_id: str = ""
    description: str = ""
    parameters: tuple[Parameter, ...] = ()
    guards: tuple[Guard, ...] = ()
    resource_sets: tuple[str, ...] = ()
    safety_class: str = "INFO"
    visibility: str = "executor"
    world_effect: None = None
    executable: bool = True
    blocked_reasons: tuple[str, ...] = ()
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "binding": self.binding,
            "parameters": [item.to_data() for item in self.parameters],
            "guards": [item.to_data() for item in self.guards],
            "resource_sets": list(self.resource_sets),
            "safety_class": self.safety_class,
            "visibility": self.visibility,
            "world_effect": None,
            "executable": self.executable,
        }
        if self.legacy_id:
            out["legacy_id"] = self.legacy_id
        if self.description:
            out["description"] = self.description
        if self.blocked_reasons:
            out["blocked_reasons"] = list(self.blocked_reasons)
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "TargetAction":
        return cls(
            id=str(data["id"]),
            binding=str(data["binding"]),
            legacy_id=str(data.get("legacy_id", "")),
            description=str(data.get("description", "")),
            parameters=tuple(Parameter.from_data(item) for item in data.get("parameters", ())),
            guards=tuple(Guard.from_data(item) for item in data.get("guards", ())),
            resource_sets=tuple(str(item) for item in data.get("resource_sets", ())),
            safety_class=str(data.get("safety_class", "INFO")),
            visibility=str(data.get("visibility", "executor")),
            executable=bool(data.get("executable", True)),
            blocked_reasons=tuple(str(item) for item in data.get("blocked_reasons", ())),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class Capability:
    id: str
    kind: str
    description: str = ""
    providers: tuple[str, ...] = ()
    target_actions: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    detects: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    qualification: str = "qualified"
    constraint_refs: tuple[str, ...] = ()
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "providers": list(self.providers),
            "target_actions": list(self.target_actions),
            "interfaces": list(self.interfaces),
            "consumes": list(self.consumes),
            "produces": list(self.produces),
            "detects": list(self.detects),
            "requirements": list(self.requirements),
            "qualification": self.qualification,
        }
        if self.description:
            out["description"] = self.description
        if self.constraint_refs:
            out["constraint_refs"] = list(self.constraint_refs)
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Capability":
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            description=str(data.get("description", "")),
            providers=tuple(str(item) for item in data.get("providers", ())),
            target_actions=tuple(str(item) for item in data.get("target_actions", ())),
            interfaces=tuple(str(item) for item in data.get("interfaces", ())),
            consumes=tuple(str(item) for item in data.get("consumes", ())),
            produces=tuple(str(item) for item in data.get("produces", ())),
            detects=tuple(str(item) for item in data.get("detects", ())),
            requirements=tuple(str(item) for item in data.get("requirements", ())),
            qualification=str(data.get("qualification", "qualified")),
            constraint_refs=tuple(str(item) for item in data.get("constraint_refs", ())),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class ServiceRequirement:
    id: str
    capability_kinds: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "capability_kinds": list(self.capability_kinds),
            "outputs": list(self.outputs),
        }
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "ServiceRequirement":
        return cls(
            id=str(data["id"]),
            capability_kinds=tuple(str(item) for item in data.get("capability_kinds", ())),
            outputs=tuple(str(item) for item in data.get("outputs", ())),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class Observation:
    id: str
    value_type: TypeRef
    sources: tuple[str, ...]
    qualification: str
    attributes: tuple[Attribute, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "value_type": self.value_type.to_data(),
            "sources": list(self.sources),
            "qualification": self.qualification,
        }
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "Observation":
        return cls(
            id=str(data["id"]),
            value_type=TypeRef.from_data(data["value_type"]),
            sources=tuple(str(item) for item in data.get("sources", ())),
            qualification=str(data["qualification"]),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
        )


@dataclass(frozen=True)
class ObservationSource:
    id: str
    binding: str
    value_type: TypeRef
    frame: str = ""
    nominal_rate_hz: float | None = None
    realtime_available: bool | None = None
    durable_replay_available: bool | None = None
    qualification: str = "source_only"
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "binding": self.binding,
            "value_type": self.value_type.to_data(),
            "qualification": self.qualification,
        }
        if self.frame:
            out["frame"] = self.frame
        if self.nominal_rate_hz is not None:
            out["nominal_rate_hz"] = self.nominal_rate_hz
        if self.realtime_available is not None:
            out["realtime_available"] = self.realtime_available
        if self.durable_replay_available is not None:
            out["durable_replay_available"] = self.durable_replay_available
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "ObservationSource":
        return cls(
            id=str(data["id"]),
            binding=str(data["binding"]),
            value_type=TypeRef.from_data(data["value_type"]),
            frame=str(data.get("frame", "")),
            nominal_rate_hz=(
                float(data["nominal_rate_hz"])
                if isinstance(data.get("nominal_rate_hz"), (int, float))
                else None
            ),
            realtime_available=(
                bool(data["realtime_available"])
                if "realtime_available" in data
                else None
            ),
            durable_replay_available=(
                bool(data["durable_replay_available"])
                if "durable_replay_available" in data
                else None
            ),
            qualification=str(data.get("qualification", "source_only")),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class EvidenceBoundary:
    id: str
    subject: str
    status: str
    kind: str = "observability"
    provider_receipt_is_effect_evidence: bool | None = None
    required_verification_sources: tuple[str, ...] = ()
    realtime_available: bool | None = None
    durable_replay_available: bool | None = None
    attributes: tuple[Attribute, ...] = ()
    provenance: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "subject": self.subject,
            "status": self.status,
            "kind": self.kind,
        }
        if self.provider_receipt_is_effect_evidence is not None:
            out["provider_receipt_is_effect_evidence"] = (
                self.provider_receipt_is_effect_evidence
            )
        if self.required_verification_sources:
            out["required_verification_sources"] = list(
                self.required_verification_sources
            )
        if self.realtime_available is not None:
            out["realtime_available"] = self.realtime_available
        if self.durable_replay_available is not None:
            out["durable_replay_available"] = self.durable_replay_available
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "EvidenceBoundary":
        return cls(
            id=str(data["id"]),
            subject=str(data["subject"]),
            status=str(data["status"]),
            kind=str(data.get("kind", "observability")),
            provider_receipt_is_effect_evidence=(
                bool(data["provider_receipt_is_effect_evidence"])
                if "provider_receipt_is_effect_evidence" in data
                else None
            ),
            required_verification_sources=tuple(
                str(item) for item in data.get("required_verification_sources", ())
            ),
            realtime_available=(
                bool(data["realtime_available"])
                if "realtime_available" in data
                else None
            ),
            durable_replay_available=(
                bool(data["durable_replay_available"])
                if "durable_replay_available" in data
                else None
            ),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
            provenance=tuple(str(item) for item in data.get("provenance", ())),
        )


@dataclass(frozen=True)
class MigrationIssue:
    id: str
    path: str
    kind: str
    severity: str
    message: str
    blocks_execution: bool = False
    legacy_text: str = ""

    def to_data(self) -> dict[str, Any]:
        out = {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "blocks_execution": self.blocks_execution,
        }
        if self.legacy_text:
            out["legacy_text"] = self.legacy_text
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "MigrationIssue":
        return cls(
            id=str(data["id"]),
            path=str(data["path"]),
            kind=str(data["kind"]),
            severity=str(data["severity"]),
            message=str(data["message"]),
            blocks_execution=bool(data.get("blocks_execution", False)),
            legacy_text=str(data.get("legacy_text", "")),
        )


@dataclass(frozen=True)
class ModuleHeader:
    id: str
    version: str
    target: str
    firmware: str = ""
    vendor: str = ""
    model: str = ""
    description: str = ""
    content_digest: str = ""
    attributes: tuple[Attribute, ...] = ()

    def to_data(self, *, include_digest: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "kind": "target_pack",
            "id": self.id,
            "version": self.version,
            "target": self.target,
        }
        if self.firmware:
            out["firmware"] = self.firmware
        if self.vendor:
            out["vendor"] = self.vendor
        if self.model:
            out["model"] = self.model
        if self.description:
            out["description"] = self.description
        if include_digest and self.content_digest:
            out["content_digest"] = self.content_digest
        if self.attributes:
            out["attributes"] = [item.to_data() for item in self.attributes]
        return out

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "ModuleHeader":
        if data.get("kind") != "target_pack":
            raise PackValidationError(["module.kind must be 'target_pack'"])
        return cls(
            id=str(data["id"]),
            version=str(data["version"]),
            target=str(data["target"]),
            firmware=str(data.get("firmware", "")),
            vendor=str(data.get("vendor", "")),
            model=str(data.get("model", "")),
            description=str(data.get("description", "")),
            content_digest=str(data.get("content_digest", "")),
            attributes=tuple(Attribute.from_data(item) for item in data.get("attributes", ())),
        )


@dataclass(frozen=True)
class PackModule:
    module: ModuleHeader
    types: tuple[EntityType, ...] = ()
    relation_types: tuple[RelationType, ...] = ()
    entities: tuple[Entity, ...] = ()
    relations: tuple[Relation, ...] = ()
    capabilities: tuple[Capability, ...] = ()
    requirements: tuple[ServiceRequirement, ...] = ()
    observations: tuple[Observation, ...] = ()
    observation_sources: tuple[ObservationSource, ...] = ()
    target_actions: tuple[TargetAction, ...] = ()
    resource_sets: tuple[ResourceSet, ...] = ()
    bindings: tuple[Binding, ...] = ()
    evidence_boundaries: tuple[EvidenceBoundary, ...] = ()
    provenance: tuple[Provenance, ...] = ()
    exports: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    migration_issues: tuple[MigrationIssue, ...] = ()

    def to_data(self, *, include_digest: bool = True) -> dict[str, Any]:
        return {
            "$schema": PACK_SCHEMA,
            "pack_version": PACK_VERSION,
            "module": self.module.to_data(include_digest=include_digest),
            "types": [item.to_data() for item in self.types],
            "relation_types": [item.to_data() for item in self.relation_types],
            "entities": [item.to_data() for item in self.entities],
            "relations": [item.to_data() for item in self.relations],
            "capabilities": [item.to_data() for item in self.capabilities],
            "requirements": [item.to_data() for item in self.requirements],
            "observations": [item.to_data() for item in self.observations],
            "observation_sources": [
                item.to_data() for item in self.observation_sources
            ],
            "target_actions": [item.to_data() for item in self.target_actions],
            "resource_sets": [item.to_data() for item in self.resource_sets],
            "bindings": [item.to_data() for item in self.bindings],
            "evidence_boundaries": [
                item.to_data() for item in self.evidence_boundaries
            ],
            "provenance": [item.to_data() for item in self.provenance],
            "exports": {
                key: list(values) for key, values in sorted(self.exports.items())
            },
            "migration": {
                "issues": [item.to_data() for item in self.migration_issues]
            },
        }

    @classmethod
    def from_data(cls, data: Mapping[str, Any]) -> "PackModule":
        if data.get("$schema") != PACK_SCHEMA:
            raise PackValidationError([f"$schema must be {PACK_SCHEMA!r}"])
        if str(data.get("pack_version")) != PACK_VERSION:
            raise PackValidationError([f"pack_version must be {PACK_VERSION!r}"])
        migration = data.get("migration") or {}
        pack = cls(
            module=ModuleHeader.from_data(data["module"]),
            types=tuple(EntityType.from_data(item) for item in data.get("types", ())),
            relation_types=tuple(
                RelationType.from_data(item) for item in data.get("relation_types", ())
            ),
            entities=tuple(Entity.from_data(item) for item in data.get("entities", ())),
            relations=tuple(Relation.from_data(item) for item in data.get("relations", ())),
            capabilities=tuple(
                Capability.from_data(item) for item in data.get("capabilities", ())
            ),
            requirements=tuple(
                ServiceRequirement.from_data(item)
                for item in data.get("requirements", ())
            ),
            observations=tuple(
                Observation.from_data(item) for item in data.get("observations", ())
            ),
            observation_sources=tuple(
                ObservationSource.from_data(item)
                for item in data.get("observation_sources", ())
            ),
            target_actions=tuple(
                TargetAction.from_data(item) for item in data.get("target_actions", ())
            ),
            resource_sets=tuple(
                ResourceSet.from_data(item) for item in data.get("resource_sets", ())
            ),
            bindings=tuple(Binding.from_data(item) for item in data.get("bindings", ())),
            evidence_boundaries=tuple(
                EvidenceBoundary.from_data(item)
                for item in data.get("evidence_boundaries", ())
            ),
            provenance=tuple(
                Provenance.from_data(item) for item in data.get("provenance", ())
            ),
            exports={
                str(key): tuple(str(value) for value in values)
                for key, values in (data.get("exports") or {}).items()
            },
            migration_issues=tuple(
                MigrationIssue.from_data(item)
                for item in migration.get("issues", ())
            ),
        )
        pack.validate()
        return pack

    def validate(self) -> None:
        issues: list[str] = []
        if not self.module.id:
            issues.append("module.id must not be empty")
        if not self.module.version:
            issues.append("module.version must not be empty")
        if not self.module.target:
            issues.append("module.target must not be empty")
        _check_unique("type", (item.id for item in self.types), issues)
        _check_unique(
            "relation type", (item.id for item in self.relation_types), issues
        )
        _check_unique("entity", (item.id for item in self.entities), issues)
        _check_unique("relation", (item.id for item in self.relations), issues)
        _check_unique("capability", (item.id for item in self.capabilities), issues)
        _check_unique("requirement", (item.id for item in self.requirements), issues)
        _check_unique("observation", (item.id for item in self.observations), issues)
        _check_unique("target action", (item.id for item in self.target_actions), issues)
        _check_unique("resource set", (item.id for item in self.resource_sets), issues)
        _check_unique("binding", (item.id for item in self.bindings), issues)
        _check_unique(
            "observation source", (item.id for item in self.observation_sources), issues
        )
        _check_unique(
            "evidence boundary", (item.id for item in self.evidence_boundaries), issues
        )
        _check_unique("provenance", (item.id for item in self.provenance), issues)

        type_ids = {item.id for item in self.types}
        parents = {item.id: item.extends for item in self.types}
        for item in self.types:
            if item.extends and item.extends not in type_ids:
                issues.append(
                    f"type {item.id!r} extends unknown type {item.extends!r}"
                )
            _check_unique(
                f"type {item.id!r} attribute",
                (name for name, _, _ in item.attributes),
                issues,
            )
            for name, type_ref, _ in item.attributes:
                _validate_type_ref(
                    type_ref, f"type {item.id!r} attribute {name!r}", issues
                )
        for type_id in type_ids:
            visited: set[str] = set()
            current = type_id
            while current:
                if current in visited:
                    issues.append(f"type inheritance cycle contains {current!r}")
                    break
                visited.add(current)
                current = parents.get(current, "")
        for item in self.entities:
            if item.type not in type_ids:
                issues.append(f"entity {item.id!r} uses unknown type {item.type!r}")
            _check_attribute_names(f"entity {item.id!r}", item.attributes, issues)

        binding_ids = {item.id for item in self.bindings}
        resource_set_ids = {item.id for item in self.resource_sets}
        entity_ids = {item.id for item in self.entities}
        capability_ids = {item.id for item in self.capabilities}
        requirement_ids = {item.id for item in self.requirements}
        action_ids = {item.id for item in self.target_actions}
        observation_ids = {item.id for item in self.observations}
        observation_source_ids = {item.id for item in self.observation_sources}
        provenance_ids = {item.id for item in self.provenance}
        symbol_ids = (
            entity_ids
            | capability_ids
            | requirement_ids
            | action_ids
            | binding_ids
        )
        for item in self.target_actions:
            if not item.id.startswith(f"{self.module.id}.action."):
                issues.append(
                    f"target action {item.id!r} is outside canonical action namespace"
                )
            if item.binding not in binding_ids:
                issues.append(
                    f"target action {item.id!r} uses unknown binding {item.binding!r}"
                )
            if item.visibility != "executor":
                issues.append(
                    f"target action {item.id!r} must remain executor-visible"
                )
            if item.executable and item.blocked_reasons:
                issues.append(
                    f"target action {item.id!r} is executable but retains blocked reasons"
                )
            if not item.executable and not item.blocked_reasons:
                issues.append(
                    f"target action {item.id!r} is non-executable without a typed reason"
                )
            parameter_names = [parameter.name for parameter in item.parameters]
            _check_unique(
                f"target action {item.id!r} parameter", parameter_names, issues
            )
            for parameter in item.parameters:
                _validate_type_ref(
                    parameter.type,
                    f"target action {item.id!r} parameter {parameter.name!r}",
                    issues,
                )
                if (
                    parameter.type.kind in {"quantity", "range"}
                    and parameter.type.name
                    in {"linear_velocity", "angular_velocity"}
                    and not parameter.type.frame
                ):
                    issues.append(
                        f"target action {item.id!r} parameter "
                        f"{parameter.name!r} velocity requires a coordinate frame"
                    )
            for index, guard in enumerate(item.guards):
                if guard.severity not in {"info", "warning", "error"}:
                    issues.append(
                        f"target action {item.id!r} guard {index} has invalid "
                        f"severity {guard.severity!r}"
                    )
                _validate_formula(
                    guard.formula.node,
                    f"target action {item.id!r} guard {index}",
                    issues,
                )
            missing = [
                resource_set
                for resource_set in item.resource_sets
                if resource_set not in resource_set_ids
            ]
            if missing:
                issues.append(
                    f"target action {item.id!r} references unknown resource sets {missing!r}"
                )
        for item in self.resource_sets:
            wildcards = [member for member in item.members if "*" in member]
            if wildcards:
                issues.append(
                    f"resource set {item.id!r} retains wildcards {wildcards!r}"
                )
            missing = [member for member in item.members if member not in entity_ids]
            if missing:
                issues.append(
                    f"resource set {item.id!r} references unknown entities {missing!r}"
                )
        for item in self.bindings:
            if not item.protocol or not item.endpoint:
                issues.append(
                    f"binding {item.id!r} requires protocol and endpoint"
                )
            if item.provider != self.module.id and item.provider not in entity_ids:
                issues.append(
                    f"binding {item.id!r} uses unknown provider {item.provider!r}"
                )
            _check_attribute_names(f"binding {item.id!r}", item.attributes, issues)
            _check_unique(
                f"binding {item.id!r} argument",
                (argument for argument, _ in item.argument_mapping),
                issues,
            )
        for item in self.capabilities:
            if not item.providers:
                issues.append(f"capability {item.id!r} has no provider")
            missing_providers = sorted(set(item.providers) - entity_ids)
            if missing_providers:
                issues.append(
                    f"capability {item.id!r} references unknown providers "
                    f"{missing_providers!r}"
                )
            missing_actions = sorted(set(item.target_actions) - action_ids)
            if missing_actions:
                issues.append(
                    f"capability {item.id!r} references unknown target actions "
                    f"{missing_actions!r}"
                )
            missing_interfaces = sorted(set(item.interfaces) - entity_ids)
            if missing_interfaces:
                issues.append(
                    f"capability {item.id!r} references unknown interfaces "
                    f"{missing_interfaces!r}"
                )
            missing_requirements = sorted(set(item.requirements) - requirement_ids)
            if missing_requirements:
                issues.append(
                    f"capability {item.id!r} references unknown requirements "
                    f"{missing_requirements!r}"
                )
        relation_types = {item.id: item for item in self.relation_types}
        symbol_types = {item.id: item.type for item in self.entities}
        symbol_types.update({item.id: "Capability" for item in self.capabilities})
        symbol_types.update(
            {item.id: "ServiceRequirement" for item in self.requirements}
        )
        symbol_types.update({item.id: "TargetAction" for item in self.target_actions})
        symbol_types.update({item.id: "AdapterBinding" for item in self.bindings})
        for item in self.relations:
            if item.source not in symbol_ids:
                issues.append(
                    f"relation {item.id!r} has unknown source {item.source!r}"
                )
            if item.target not in symbol_ids:
                issues.append(
                    f"relation {item.id!r} has unknown target {item.target!r}"
                )
            relation_type = relation_types.get(item.predicate)
            if relation_type is None:
                issues.append(
                    f"relation {item.id!r} uses undeclared predicate {item.predicate!r}"
                )
                continue
            source_type = symbol_types.get(item.source)
            target_type = symbol_types.get(item.target)
            if source_type and source_type not in relation_type.source_types:
                issues.append(
                    f"relation {item.id!r} source type {source_type!r} is not "
                    f"allowed by {item.predicate!r}"
                )
            if target_type and target_type not in relation_type.target_types:
                issues.append(
                    f"relation {item.id!r} target type {target_type!r} is not "
                    f"allowed by {item.predicate!r}"
                )
        for item in self.observation_sources:
            if item.binding not in binding_ids:
                issues.append(
                    f"observation source {item.id!r} uses unknown binding {item.binding!r}"
                )
            _validate_type_ref(
                item.value_type, f"observation source {item.id!r}", issues
            )
        for item in self.observations:
            _validate_type_ref(item.value_type, f"observation {item.id!r}", issues)
            missing_sources = sorted(set(item.sources) - observation_source_ids)
            if missing_sources:
                issues.append(
                    f"observation {item.id!r} references unknown sources "
                    f"{missing_sources!r}"
                )
        for item in self.evidence_boundaries:
            missing_verifiers = sorted(
                set(item.required_verification_sources) - action_ids
            )
            if missing_verifiers:
                issues.append(
                    f"evidence boundary {item.id!r} references unknown verification "
                    f"actions {missing_verifiers!r}"
                )
        for label, refs in _iter_provenance_refs(self):
            missing = sorted(set(refs) - provenance_ids)
            if missing:
                issues.append(f"{label} references unknown provenance {missing!r}")
        for kind, exported in self.exports.items():
            known = {
                "capabilities": capability_ids,
                "target_actions": action_ids,
                "observations": observation_ids,
                "types": type_ids,
            }.get(kind)
            if known is None:
                issues.append(f"unknown export category {kind!r}")
                continue
            missing = sorted(set(exported) - known)
            if missing:
                issues.append(f"exports.{kind} references unknown symbols {missing!r}")
        if issues:
            raise PackValidationError(issues)

    def with_digest(self, digest: str) -> "PackModule":
        header = ModuleHeader(
            id=self.module.id,
            version=self.module.version,
            target=self.module.target,
            firmware=self.module.firmware,
            vendor=self.module.vendor,
            model=self.module.model,
            description=self.module.description,
            content_digest=digest,
            attributes=self.module.attributes,
        )
        return PackModule(
            module=header,
            types=self.types,
            relation_types=self.relation_types,
            entities=self.entities,
            relations=self.relations,
            capabilities=self.capabilities,
            requirements=self.requirements,
            observations=self.observations,
            observation_sources=self.observation_sources,
            target_actions=self.target_actions,
            resource_sets=self.resource_sets,
            bindings=self.bindings,
            evidence_boundaries=self.evidence_boundaries,
            provenance=self.provenance,
            exports=self.exports,
            migration_issues=self.migration_issues,
        )

    def count(self) -> dict[str, int]:
        return {
            "types": len(self.types),
            "relation_types": len(self.relation_types),
            "entities": len(self.entities),
            "relations": len(self.relations),
            "capabilities": len(self.capabilities),
            "requirements": len(self.requirements),
            "observations": len(self.observations),
            "observation_sources": len(self.observation_sources),
            "target_actions": len(self.target_actions),
            "resource_sets": len(self.resource_sets),
            "bindings": len(self.bindings),
            "evidence_boundaries": len(self.evidence_boundaries),
            "migration_issues": len(self.migration_issues),
        }


def _copy_formula(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _copy_formula(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_formula(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"formula contains unsupported value {value!r}")


def _check_unique(label: str, values: Iterable[str], issues: list[str]) -> None:
    seen: set[str] = set()
    for value in values:
        if not value:
            issues.append(f"{label} id must not be empty")
        elif value in seen:
            issues.append(f"duplicate {label} id {value!r}")
        seen.add(value)


def _check_attribute_names(
    label: str, attributes: tuple[Attribute, ...], issues: list[str]
) -> None:
    _check_unique(f"{label} attribute", (item.name for item in attributes), issues)


def _validate_type_ref(type_ref: TypeRef, label: str, issues: list[str]) -> None:
    allowed = {
        "opaque",
        "bool",
        "int",
        "float",
        "string",
        "enum",
        "entity",
        "quantity",
        "range",
        "list",
        "record",
    }
    if type_ref.kind not in allowed:
        issues.append(f"{label} has unsupported type kind {type_ref.kind!r}")
    if type_ref.kind == "enum" and not type_ref.values:
        issues.append(f"{label} enum type must declare values")
    if type_ref.kind == "list" and type_ref.item is None:
        issues.append(f"{label} list type must declare an item type")
    if type_ref.item is not None:
        _validate_type_ref(type_ref.item, f"{label} item", issues)
    if type_ref.kind in {"quantity", "range"}:
        if not type_ref.name or not type_ref.unit:
            issues.append(f"{label} physical type requires dimension and unit")


def _validate_formula(
    node: Mapping[str, Any], label: str, issues: list[str]
) -> None:
    kind = node.get("kind")
    if kind == "literal":
        if "value" not in node:
            issues.append(f"{label} literal has no value")
        return
    if kind == "list":
        children = node.get("items")
        child_key = "items"
    elif kind == "symbol":
        if not node.get("path"):
            issues.append(f"{label} symbol has no path")
        return
    elif kind == "ref":
        if node.get("scope") not in {"parameter", "observation"} or not node.get("path"):
            issues.append(f"{label} ref requires parameter/observation scope and path")
        return
    elif kind == "boolean":
        if node.get("operator") not in {"and", "or"}:
            issues.append(f"{label} boolean has invalid operator")
        children = node.get("terms")
        child_key = "terms"
    elif kind == "not":
        child = node.get("term")
        if not isinstance(child, Mapping):
            issues.append(f"{label} not node requires term")
        else:
            _validate_formula(child, f"{label}.term", issues)
        return
    elif kind == "compare":
        if node.get("operator") not in {
            "eq", "ne", "lt", "le", "gt", "ge", "in", "not_in",
            "contains", "not_contains",
        }:
            issues.append(f"{label} comparison has invalid operator")
        for side in ("left", "right"):
            child = node.get(side)
            if not isinstance(child, Mapping):
                issues.append(f"{label} comparison requires {side}")
            else:
                _validate_formula(child, f"{label}.{side}", issues)
        return
    elif kind == "call":
        if node.get("namespace") not in {
            "intrinsic", "ontology_query", "observation_query", "pack_query",
        } or not node.get("name"):
            issues.append(f"{label} call requires a known namespace and name")
        children = node.get("arguments")
        child_key = "arguments"
    else:
        issues.append(f"{label} has unsupported formula kind {kind!r}")
        return
    if not isinstance(children, list):
        issues.append(f"{label} {kind} requires {child_key}")
        return
    for index, child in enumerate(children):
        if not isinstance(child, Mapping):
            issues.append(f"{label}.{child_key}[{index}] must be a formula")
        else:
            _validate_formula(child, f"{label}.{child_key}[{index}]", issues)


def _iter_provenance_refs(
    pack: PackModule,
) -> Iterable[tuple[str, tuple[str, ...]]]:
    groups = (
        ("entity", pack.entities),
        ("relation", pack.relations),
        ("capability", pack.capabilities),
        ("requirement", pack.requirements),
        ("observation source", pack.observation_sources),
        ("target action", pack.target_actions),
        ("binding", pack.bindings),
        ("evidence boundary", pack.evidence_boundaries),
    )
    for kind, values in groups:
        for item in values:
            yield f"{kind} {item.id!r}", item.provenance
