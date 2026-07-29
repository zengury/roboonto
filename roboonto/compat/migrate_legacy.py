"""One-time compiler from legacy RoboOnto directories to PackModule 0.9."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml

from ..pack.builder import attributes_from_mapping, type_ref_from_legacy, typed_value
from ..pack.formula import LegacyFormulaError, parse_legacy_formula
from ..pack.io import pack_digest
from ..pack.model import (
    Attribute,
    Binding,
    Capability,
    Entity,
    EntityType,
    EvidenceBoundary,
    Guard,
    MigrationIssue,
    ModuleHeader,
    Observation,
    ObservationSource,
    PackModule,
    Parameter,
    Provenance,
    Relation,
    RelationType,
    ResourceSet,
    ServiceRequirement,
    TargetAction,
    TypeRef,
)


class LegacyMigrationError(ValueError):
    pass


@dataclass(frozen=True)
class MigrationResult:
    pack: PackModule
    source_counts: Mapping[str, int]


_CATEGORY_BY_TYPE = {
    "Capability": "capability",
    "CapabilityParameter": "capability",
    "ServiceRequirement": "capability",
    "ComputeUnit": "hardware",
    "ControlLoop": "behavior",
    "CoordinateFrame": "frame",
    "FaultCode": "event",
    "InputSource": "meta",
    "Joint": "hardware",
    "Link": "hardware",
    "Mode": "behavior",
    "MsgSchema": "interface",
    "PowerSubsystem": "hardware",
    "PresetMotion": "behavior",
    "PriorityLevel": "meta",
    "ProtectionThreshold": "hardware",
    "RobotBody": "hardware",
    "Sensor": "hardware",
    "Service": "interface",
    "SoftwareComponent": "software",
    "StatusBit": "event",
    "Topic": "interface",
    "TouchEvent": "event",
}

_NATURAL_CONSTRAINT_FIELDS = {
    "arbitration_rules",
    "boundaries",
    "does_not_cover",
    "environment",
    "environment_requirements",
    "forbidden_contexts",
    "requires_environment",
    "required_preconditions",
    "safety_constraints",
    "safety_note",
}


class LegacyPackMigrator:
    """Compile one legacy pack directory into a closed Target PackModule."""

    def __init__(self, *, output_version: str = "0.9.0"):
        self.output_version = output_version

    def migrate(self, path: str | Path) -> MigrationResult:
        root = Path(path)
        entry = _read_yaml(root / "ontology.yaml")
        robot = entry.get("robot") or {}
        robot_id = str(robot.get("id") or root.name)
        documents: list[tuple[str, dict[str, Any]]] = [("ontology.yaml", entry)]
        for include in entry.get("includes", ()):
            include_path = root / str(include)
            documents.append((str(include), _read_yaml(include_path)))

        raw_objects: list[tuple[str, dict[str, Any]]] = []
        raw_actions: list[tuple[str, dict[str, Any]]] = []
        raw_links: list[tuple[str, dict[str, Any]]] = []
        for filename, document in documents:
            raw_objects.extend((filename, item) for item in document.get("objects") or ())
            raw_actions.extend((filename, item) for item in document.get("actions") or ())
            raw_links.extend((filename, item) for item in document.get("links") or ())

        provenance: dict[str, Provenance] = {}
        migration_issues: list[MigrationIssue] = []
        core_types = self._load_types(documents, raw_objects)
        type_definitions = {
            item["id"]: item.get("properties") or {} for item in core_types
        }
        types = tuple(self._migrate_type(item) for item in core_types)

        raw_action_ids = {
            str(item.get("type_id") or item.get("id"))
            for _, item in raw_actions
            if item.get("type_id") or item.get("id")
        }
        action_ids = {
            legacy: f"{robot_id}.action.{legacy}" for legacy in raw_action_ids
        }

        entities: list[Entity] = []
        capabilities: list[Capability] = []
        requirements: list[ServiceRequirement] = []
        raw_by_id = {
            str(item["id"]): item
            for _, item in raw_objects
            if item.get("id")
        }
        object_file = {
            str(item["id"]): filename
            for filename, item in raw_objects
            if item.get("id")
        }

        raw_relation_items = [item for _, item in raw_links]
        providers_by_capability: dict[str, set[str]] = defaultdict(set)
        exposed_by_capability: dict[str, set[str]] = defaultdict(set)
        requirements_by_capability: dict[str, set[str]] = defaultdict(set)
        for item in raw_relation_items:
            predicate = str(item.get("type", ""))
            source = str(item.get("source", ""))
            target = str(item.get("target", ""))
            if predicate == "provides_capability":
                providers_by_capability[target].add(source)
            elif predicate == "exposed_via":
                exposed_by_capability[source].add(target)
            elif predicate == "satisfies_requirement":
                requirements_by_capability[source].add(target)

        for filename, item in raw_objects:
            object_id = str(item.get("id", ""))
            object_type = str(item.get("type", ""))
            if not object_id or not object_type:
                raise LegacyMigrationError(f"{filename}: object missing id/type")
            provenance_ids = self._provenance_for(
                item.get("source"), filename, provenance
            )
            properties = item.get("properties") or {}
            if object_type == "Capability":
                constraint_refs = self._constraint_issues(
                    object_id,
                    properties,
                    migration_issues,
                    blocks_execution=False,
                )
                exposed = sorted(exposed_by_capability.get(object_id, ()))
                capabilities.append(
                    Capability(
                        id=object_id,
                        kind=str(properties.get("capability_kind", "unknown")),
                        description=str(properties.get("description", "")),
                        providers=tuple(
                            sorted(providers_by_capability.get(object_id, ()))
                        ),
                        target_actions=tuple(
                            sorted(action_ids[value] for value in exposed if value in action_ids)
                        ),
                        interfaces=tuple(
                            sorted(value for value in exposed if value not in action_ids)
                        ),
                        consumes=tuple(str(value) for value in properties.get("consumes", ())),
                        produces=tuple(str(value) for value in properties.get("produces", ())),
                        detects=tuple(str(value) for value in properties.get("detects", ())),
                        requirements=tuple(
                            sorted(requirements_by_capability.get(object_id, ()))
                        ),
                        qualification=(
                            "review_required" if constraint_refs else "qualified"
                        ),
                        constraint_refs=constraint_refs,
                        attributes=attributes_from_mapping(
                            properties,
                            type_definitions.get(object_type),
                            exclude={
                                "capability_kind",
                                "description",
                                "consumes",
                                "produces",
                                "detects",
                                *_NATURAL_CONSTRAINT_FIELDS,
                            },
                        ),
                        provenance=provenance_ids,
                    )
                )
                continue
            if object_type == "ServiceRequirement":
                self._constraint_issues(
                    object_id,
                    properties,
                    migration_issues,
                    blocks_execution=False,
                )
                requirements.append(
                    ServiceRequirement(
                        id=object_id,
                        capability_kinds=tuple(
                            str(value)
                            for value in properties.get("required_capabilities", ())
                        ),
                        outputs=tuple(
                            str(value) for value in properties.get("required_outputs", ())
                        ),
                        attributes=attributes_from_mapping(
                            properties,
                            type_definitions.get(object_type),
                            exclude={
                                "required_capabilities",
                                "required_outputs",
                                *_NATURAL_CONSTRAINT_FIELDS,
                            },
                        ),
                        provenance=provenance_ids,
                    )
                )
                continue

            self._constraint_issues(
                object_id,
                properties,
                migration_issues,
                blocks_execution=False,
            )
            entities.append(
                Entity(
                    id=object_id,
                    type=object_type,
                    attributes=attributes_from_mapping(
                        properties, type_definitions.get(object_type)
                    ),
                    provenance=provenance_ids,
                )
            )

        mode_values = _mode_value_map(raw_by_id)
        bindings: list[Binding] = []
        resource_sets: list[ResourceSet] = []
        target_actions: list[TargetAction] = []
        entity_ids = {item.id for item in entities}
        capability_for_action: dict[str, list[str]] = defaultdict(list)
        for capability_id, exposed in exposed_by_capability.items():
            for legacy_id in exposed:
                if legacy_id in action_ids:
                    capability_for_action[legacy_id].append(capability_id)

        for filename, item in raw_actions:
            legacy_id = str(item.get("type_id") or item.get("id") or "")
            if not legacy_id:
                raise LegacyMigrationError(f"{filename}: action missing type_id")
            action_id = action_ids[legacy_id]
            provenance_ids = self._provenance_for(
                item.get("source"), filename, provenance
            )
            parameters = tuple(
                self._parameter(value, robot_id, legacy_id)
                for value in item.get("parameters") or ()
            )
            guards: list[Guard] = []
            blocked_reasons: list[str] = []
            for index, raw_guard in enumerate(item.get("preconditions") or ()):
                expression = str(raw_guard.get("expr", ""))
                try:
                    formula = parse_legacy_formula(expression)
                    formula = type(formula)(
                        _canonicalize_formula(formula.node, mode_values)
                    )
                    guards.append(
                        Guard(
                            formula=formula,
                            code=f"PACK-GUARD-{legacy_id.upper()}-{index + 1}",
                            message=str(
                                raw_guard.get(
                                    "error", f"guard failed for {legacy_id}"
                                )
                            ),
                            severity=_normalize_severity(
                                str(raw_guard.get("severity", "error"))
                            ),
                        )
                    )
                except LegacyFormulaError as exc:
                    issue = self._issue(
                        migration_issues,
                        path=f"target_actions.{action_id}.guards[{index}]",
                        kind="untyped_guard",
                        severity="error",
                        message=str(exc),
                        blocks_execution=True,
                        legacy_text=expression,
                    )
                    blocked_reasons.append(issue.id)

            invoker = item.get("invoker") or {}
            binding_id = f"{robot_id}.binding.{legacy_id}"
            providers = sorted(
                {
                    provider
                    for capability in capability_for_action.get(legacy_id, ())
                    for provider in providers_by_capability.get(capability, ())
                }
            )
            binding = self._binding(
                binding_id,
                robot_id,
                invoker,
                parameters,
                providers[0] if providers else robot_id,
                item,
                provenance_ids,
            )
            bindings.append(binding)

            affected = list(item.get("affects") or ())
            for values in (item.get("affects_by_domain") or {}).values():
                affected.extend(values or ())
            resources = _expand_resources(affected, entity_ids)
            unresolved_resources = sorted(
                value
                for value in affected
                if not _resource_pattern_matches(str(value), entity_ids)
            )
            if unresolved_resources:
                issue = self._issue(
                    migration_issues,
                    path=f"target_actions.{action_id}.resources",
                    kind="unresolved_resource",
                    severity="error",
                    message=f"resource patterns did not resolve: {unresolved_resources}",
                    blocks_execution=True,
                )
                blocked_reasons.append(issue.id)
            action_resource_sets: tuple[str, ...] = ()
            if resources:
                resource_set_id = f"{robot_id}.resource.{legacy_id}"
                resource_sets.append(
                    ResourceSet(
                        id=resource_set_id,
                        members=tuple(resources),
                        purpose=f"resources affected by {action_id}",
                    )
                )
                action_resource_sets = (resource_set_id,)

            action_attributes = {
                key: value
                for key, value in item.items()
                if key
                not in {
                    "type_id",
                    "id",
                    "description",
                    "invoker",
                    "parameters",
                    "preconditions",
                    "affects",
                    "affects_by_domain",
                    "safety_class",
                    "source",
                }
            }
            target_actions.append(
                TargetAction(
                    id=action_id,
                    legacy_id=legacy_id,
                    binding=binding_id,
                    description=str(item.get("description", "")),
                    parameters=parameters,
                    guards=tuple(guards),
                    resource_sets=action_resource_sets,
                    safety_class=str(item.get("safety_class", "INFO")).lower(),
                    executable=not blocked_reasons,
                    blocked_reasons=tuple(blocked_reasons),
                    attributes=attributes_from_mapping(action_attributes),
                    provenance=provenance_ids,
                )
            )

        relations = self._relations(
            robot_id,
            raw_links,
            action_ids,
            provenance,
        )
        symbol_types = {item.id: item.type for item in entities}
        symbol_types.update({item.id: "Capability" for item in capabilities})
        symbol_types.update({item.id: "ServiceRequirement" for item in requirements})
        symbol_types.update({item.id: "TargetAction" for item in target_actions})
        symbol_types.update({item.id: "AdapterBinding" for item in bindings})
        relation_types = _infer_relation_types(relations, symbol_types)

        interface_bindings, observation_sources = self._observation_sources(
            robot_id,
            raw_objects,
            type_definitions,
            provenance,
            documents,
        )
        bindings.extend(interface_bindings)
        evidence_boundaries = self._evidence_boundaries(
            robot_id, documents, action_ids
        )
        observation_sources = _apply_observability(
            observation_sources, evidence_boundaries
        )
        observations = self._semantic_observations(
            robot_id,
            capabilities,
            observation_sources,
            migration_issues,
        )

        header_attributes = attributes_from_mapping(
            {
                key: value
                for key, value in robot.items()
                if key
                not in {
                    "id",
                    "vendor",
                    "model",
                    "firmware_version",
                    "description",
                    "roboonto_version",
                }
            }
        )
        header_attributes += (
            Attribute("legacy_roboonto_version", typed_value(robot.get("roboonto_version"))),
            Attribute("legacy_object_count", typed_value(len(raw_objects))),
            Attribute("legacy_relation_count", typed_value(len(raw_links))),
            Attribute("legacy_action_count", typed_value(len(raw_actions))),
        )
        standard_document = next(
            (
                document
                for filename, document in documents
                if filename == "standard_mappings.yaml"
            ),
            None,
        )
        if standard_document:
            header_attributes += (
                Attribute("standard_mappings", typed_value(standard_document)),
            )

        pack = PackModule(
            module=ModuleHeader(
                id=robot_id,
                version=self.output_version,
                target=robot_id,
                firmware=str(robot.get("firmware_version", "")),
                vendor=str(robot.get("vendor", "")),
                model=str(robot.get("model", "")),
                description=str(robot.get("description", "")).strip(),
                attributes=tuple(sorted(header_attributes, key=lambda item: item.name)),
            ),
            types=tuple(sorted(types, key=lambda item: item.id)),
            relation_types=tuple(sorted(relation_types, key=lambda item: item.id)),
            entities=tuple(sorted(entities, key=lambda item: item.id)),
            relations=tuple(sorted(relations, key=lambda item: item.id)),
            capabilities=tuple(sorted(capabilities, key=lambda item: item.id)),
            requirements=tuple(sorted(requirements, key=lambda item: item.id)),
            observations=tuple(sorted(observations, key=lambda item: item.id)),
            observation_sources=tuple(
                sorted(observation_sources, key=lambda item: item.id)
            ),
            target_actions=tuple(sorted(target_actions, key=lambda item: item.id)),
            resource_sets=tuple(sorted(resource_sets, key=lambda item: item.id)),
            bindings=tuple(sorted(bindings, key=lambda item: item.id)),
            evidence_boundaries=tuple(
                sorted(evidence_boundaries, key=lambda item: item.id)
            ),
            provenance=tuple(sorted(provenance.values(), key=lambda item: item.id)),
            exports={
                "capabilities": tuple(sorted(item.id for item in capabilities)),
                "observations": tuple(sorted(item.id for item in observations)),
                "target_actions": tuple(sorted(item.id for item in target_actions)),
                "types": tuple(sorted(item.id for item in types)),
            },
            migration_issues=tuple(
                sorted(migration_issues, key=lambda item: item.id)
            ),
        )
        pack.validate()
        pack = pack.with_digest(pack_digest(pack))
        return MigrationResult(
            pack=pack,
            source_counts={
                "objects": len(raw_objects),
                "relations": len(raw_links),
                "actions": len(raw_actions),
            },
        )

    def _load_types(
        self,
        documents: list[tuple[str, dict[str, Any]]],
        raw_objects: list[tuple[str, dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        core_path = Path(__file__).parents[1] / "core" / "core-object-types.yaml"
        core = _read_yaml(core_path)
        merged = {
            str(item["id"]): dict(item) for item in core.get("object_types") or ()
        }
        for _, document in documents:
            for item in document.get("object_types") or ():
                merged[str(item["id"])] = dict(item)
        for _, item in raw_objects:
            type_name = str(item.get("type", ""))
            if type_name and type_name not in merged:
                merged[type_name] = {
                    "id": type_name,
                    "category": _CATEGORY_BY_TYPE.get(type_name, "extension"),
                    "description": "Legacy extension type normalized by PackModule migration",
                    "properties": {},
                }
        return list(merged.values())

    @staticmethod
    def _migrate_type(item: Mapping[str, Any]) -> EntityType:
        return EntityType(
            id=str(item["id"]),
            category=str(
                item.get("category")
                or _CATEGORY_BY_TYPE.get(str(item["id"]), "extension")
            ),
            extends=str(item.get("extends", "")),
            description=str(item.get("description", "")),
            attributes=tuple(
                (
                    str(name),
                    type_ref_from_legacy(spec),
                    bool((spec or {}).get("required", False)),
                )
                for name, spec in sorted(
                    (item.get("properties") or {}).items(),
                    key=lambda pair: str(pair[0]),
                )
            ),
        )

    def _parameter(
        self,
        item: Mapping[str, Any],
        robot_id: str,
        action_id: str,
    ) -> Parameter:
        type_ref = type_ref_from_legacy(item)
        if (
            type_ref.kind == "quantity"
            and not type_ref.frame
            and item.get("name") in {"forward_velocity", "lateral_velocity", "angular_velocity"}
        ):
            type_ref = TypeRef(
                kind=type_ref.kind,
                name=(
                    "linear_velocity"
                    if item.get("name") != "angular_velocity"
                    else "angular_velocity"
                ),
                unit=type_ref.unit,
                frame=f"{robot_id}.frame.base_link",
            )
        constraints = tuple(
            typed_value(value) for value in item.get("constraints") or ()
        )
        default = (
            typed_value(item["default"], type_ref)
            if "default" in item
            else None
        )
        return Parameter(
            name=str(item["name"]),
            type=type_ref,
            required=bool(item.get("required", True)),
            default=default,
            constraints=constraints,
        )

    @staticmethod
    def _binding(
        binding_id: str,
        robot_id: str,
        invoker: Mapping[str, Any],
        parameters: tuple[Parameter, ...],
        provider: str,
        action: Mapping[str, Any],
        provenance: tuple[str, ...],
    ) -> Binding:
        protocol = str(invoker.get("type") or "unbound")
        endpoint = str(
            invoker.get("name")
            or invoker.get("name_template")
            or invoker.get("command")
            or f"{robot_id}.unbound"
        )
        message_type = str(invoker.get("msg_type", ""))
        request_type = str(invoker.get("srv_type", ""))
        mapped_field = str(invoker.get("field", ""))
        argument_mapping = tuple(
            (
                parameter.name,
                mapped_field
                if mapped_field and len(parameters) == 1
                else f"$arguments.{parameter.name}",
            )
            for parameter in parameters
        )
        excluded = {"type", "name", "name_template", "command", "msg_type", "srv_type", "field"}
        return Binding(
            id=binding_id,
            provider=provider,
            protocol=protocol,
            endpoint=endpoint,
            message_type=message_type,
            request_type=request_type,
            delivery_semantics=(
                "stream" if protocol in {"ros2_topic", "dds_topic"} else "request_response"
            ),
            acceptance_source=(
                f"{robot_id}.gate.mc_input_source_arbitration"
                if action.get("priority_integration") == "mc_arbitration"
                or action.get("required_input_source")
                else ""
            ),
            argument_mapping=argument_mapping,
            attributes=attributes_from_mapping(
                {key: value for key, value in invoker.items() if key not in excluded}
            ),
            provenance=provenance,
        )

    def _relations(
        self,
        robot_id: str,
        raw_links: list[tuple[str, dict[str, Any]]],
        action_ids: Mapping[str, str],
        provenance: dict[str, Provenance],
    ) -> list[Relation]:
        normalized: list[tuple[str, str, str, tuple[Attribute, ...], tuple[str, ...]]] = []
        for filename, item in raw_links:
            predicate = str(item.get("type", ""))
            source = action_ids.get(str(item.get("source", "")), str(item.get("source", "")))
            target = action_ids.get(str(item.get("target", "")), str(item.get("target", "")))
            if not predicate or not source or not target:
                raise LegacyMigrationError(f"{filename}: malformed relation {item!r}")
            attributes = attributes_from_mapping(
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"type", "source", "target", "source_info"}
                }
            )
            provenance_ids = self._provenance_for(
                item.get("source_info"), filename, provenance
            )
            normalized.append(
                (predicate, source, target, attributes, provenance_ids)
            )
        normalized.sort(
            key=lambda item: (
                item[0],
                item[1],
                item[2],
                json.dumps(
                    [value.to_data() for value in item[3]],
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )
        )
        return [
            Relation(
                id=f"{robot_id}.relation.{predicate}.{index:04d}",
                predicate=predicate,
                source=source,
                target=target,
                attributes=attributes,
                provenance=provenance_ids,
            )
            for index, (predicate, source, target, attributes, provenance_ids) in enumerate(
                normalized, start=1
            )
        ]

    def _observation_sources(
        self,
        robot_id: str,
        raw_objects: list[tuple[str, dict[str, Any]]],
        type_definitions: Mapping[str, Mapping[str, Any]],
        provenance: dict[str, Provenance],
        documents: list[tuple[str, dict[str, Any]]],
    ) -> tuple[list[Binding], list[ObservationSource]]:
        bindings: list[Binding] = []
        sources: list[ObservationSource] = []
        for filename, item in raw_objects:
            if item.get("type") != "Topic":
                continue
            properties = item.get("properties") or {}
            direction = str(properties.get("direction", ""))
            topic_id = str(item["id"])
            if direction == "subscribe_from_outside" or topic_id.endswith("_command"):
                continue
            endpoint = str(properties.get("name", ""))
            if not endpoint:
                continue
            slug = topic_id.split(".")[-1]
            binding_id = f"{robot_id}.binding.observe.{slug}"
            provenance_ids = self._provenance_for(
                item.get("source"), filename, provenance
            )
            message_type = str(properties.get("msg_type", "opaque"))
            bindings.append(
                Binding(
                    id=binding_id,
                    provider=str(properties.get("publisher") or robot_id),
                    protocol="ros2_topic",
                    endpoint=endpoint,
                    message_type=message_type,
                    delivery_semantics="observation_stream",
                    provenance=provenance_ids,
                )
            )
            frequency = properties.get("frequency_hz")
            sources.append(
                ObservationSource(
                    id=f"{robot_id}.observation_source.{slug}",
                    binding=binding_id,
                    value_type=TypeRef("record", name=message_type),
                    frame=_infer_frame(robot_id, topic_id),
                    nominal_rate_hz=(
                        float(frequency) if isinstance(frequency, (int, float)) else None
                    ),
                    realtime_available=True,
                    qualification="source_only",
                    provenance=provenance_ids,
                )
            )
        return bindings, sources

    def _evidence_boundaries(
        self,
        robot_id: str,
        documents: list[tuple[str, dict[str, Any]]],
        action_ids: Mapping[str, str],
    ) -> list[EvidenceBoundary]:
        boundary_doc = next(
            (
                document
                for filename, document in documents
                if filename == "capability_boundary.yaml"
            ),
            None,
        )
        if not boundary_doc:
            return []
        boundaries: list[EvidenceBoundary] = []
        for name, raw in sorted((boundary_doc.get("observability") or {}).items()):
            values = dict(raw or {})
            provider_receipt = None
            verification_sources: tuple[str, ...] = ()
            if values.get("known_false_positive"):
                provider_receipt = False
                if name == "mode_switch" and "get_mc_action" in action_ids:
                    verification_sources = (action_ids["get_mc_action"],)
            realtime = True if values.get("realtime_topic") else None
            durable = (
                bool(values["recorded_in_mcap"])
                if "recorded_in_mcap" in values
                else None
            )
            excluded = {
                "status",
                "known_false_positive",
                "realtime_topic",
                "recorded_in_mcap",
            }
            boundaries.append(
                EvidenceBoundary(
                    id=f"{robot_id}.evidence_boundary.{name}",
                    subject=name,
                    status=str(values.get("status", "unknown")),
                    provider_receipt_is_effect_evidence=provider_receipt,
                    required_verification_sources=verification_sources,
                    realtime_available=realtime,
                    durable_replay_available=durable,
                    attributes=attributes_from_mapping(
                        {key: value for key, value in values.items() if key not in excluded}
                    ),
                )
            )
        for raw in boundary_doc.get("log_sources") or ():
            name = str(raw.get("id", "unknown"))
            boundaries.append(
                EvidenceBoundary(
                    id=f"{robot_id}.evidence_boundary.log.{name}",
                    subject=name,
                    status="declared",
                    kind="log_source",
                    durable_replay_available=True,
                    attributes=attributes_from_mapping(
                        {key: value for key, value in raw.items() if key != "id"}
                    ),
                )
            )
        return boundaries

    def _semantic_observations(
        self,
        robot_id: str,
        capabilities: list[Capability],
        sources: list[ObservationSource],
        issues: list[MigrationIssue],
    ) -> list[Observation]:
        source_ids = tuple(item.id for item in sources)
        observations: list[Observation] = []
        names = sorted(
            {
                value
                for capability in capabilities
                for value in (*capability.produces, *capability.detects)
            }
        )
        for name in names:
            observation_id = f"{robot_id}.observation.{_slug(name)}"
            self._issue(
                issues,
                path=f"observations.{observation_id}",
                kind="observation_contract_incomplete",
                severity="warning",
                message=(
                    "legacy capability output has no reviewed value type, freshness, "
                    "sentinel, or evidence policy"
                ),
                blocks_execution=False,
            )
            observations.append(
                Observation(
                    id=observation_id,
                    value_type=TypeRef("opaque", name="legacy_capability_output"),
                    sources=source_ids,
                    qualification="contract_required",
                )
            )
        return observations

    def _constraint_issues(
        self,
        symbol_id: str,
        properties: Mapping[str, Any],
        issues: list[MigrationIssue],
        *,
        blocks_execution: bool,
    ) -> tuple[str, ...]:
        refs: list[str] = []
        for field in sorted(_NATURAL_CONSTRAINT_FIELDS & set(properties)):
            value = properties[field]
            if value in (None, "", [], {}):
                continue
            issue = self._issue(
                issues,
                path=f"{symbol_id}.{field}",
                kind="untyped_constraint",
                severity="warning",
                message="natural-language constraint requires a typed profile or formula",
                blocks_execution=blocks_execution,
                legacy_text=json.dumps(value, ensure_ascii=False, default=str),
            )
            refs.append(issue.id)
        return tuple(refs)

    @staticmethod
    def _provenance_for(
        raw: Any,
        filename: str,
        registry: dict[str, Provenance],
    ) -> tuple[str, ...]:
        source = dict(raw) if isinstance(raw, Mapping) else {}
        kind = str(source.pop("type", "legacy_file"))
        locator = str(source.pop("locator", filename))
        extractor = str(source.pop("extractor", ""))
        extracted_at = str(source.pop("extracted_at", ""))
        confidence_raw = source.pop("confidence", None)
        confidence = (
            float(confidence_raw)
            if isinstance(confidence_raw, (int, float))
            else None
        )
        notes = str(source.pop("notes", ""))
        identity = json.dumps(
            {
                "kind": kind,
                "locator": locator,
                "extractor": extractor,
                "extracted_at": extracted_at,
                "confidence": confidence,
                "notes": notes,
                "attributes": source,
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        source_id = "prov:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
        if source_id not in registry:
            registry[source_id] = Provenance(
                id=source_id,
                kind=kind,
                locator=locator,
                extractor=extractor,
                extracted_at=extracted_at,
                confidence=confidence,
                notes=notes,
                attributes=attributes_from_mapping(source),
            )
        return (source_id,)

    @staticmethod
    def _issue(
        issues: list[MigrationIssue],
        *,
        path: str,
        kind: str,
        severity: str,
        message: str,
        blocks_execution: bool,
        legacy_text: str = "",
    ) -> MigrationIssue:
        payload = f"{path}|{kind}|{message}|{legacy_text}"
        issue = MigrationIssue(
            id="migration:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
            path=path,
            kind=kind,
            severity=severity,
            message=message,
            blocks_execution=blocks_execution,
            legacy_text=legacy_text,
        )
        issues.append(issue)
        return issue


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise LegacyMigrationError(f"{path} must contain a mapping")
    return data


def _mode_value_map(raw_by_id: Mapping[str, Mapping[str, Any]]) -> dict[str, str]:
    return {
        str((item.get("properties") or {}).get("mode_value")): object_id
        for object_id, item in raw_by_id.items()
        if item.get("type") == "Mode"
        and (item.get("properties") or {}).get("mode_value") is not None
    }


def _canonicalize_formula(value: Any, modes: Mapping[str, str]) -> Any:
    if isinstance(value, dict):
        if value.get("kind") == "literal" and value.get("value") in modes:
            return {"kind": "symbol", "path": modes[str(value["value"])]}
        return {
            key: _canonicalize_formula(item, modes)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_canonicalize_formula(item, modes) for item in value]
    return value


def _expand_resources(values: list[Any], entity_ids: set[str]) -> list[str]:
    expanded: set[str] = set()
    for raw in values:
        value = str(raw)
        if "*" in value:
            prefix = value.split("*", 1)[0]
            expanded.update(item for item in entity_ids if item.startswith(prefix))
        elif value in entity_ids:
            expanded.add(value)
    return sorted(expanded)


def _resource_pattern_matches(value: str, entity_ids: set[str]) -> bool:
    if "*" in value:
        prefix = value.split("*", 1)[0]
        return any(item.startswith(prefix) for item in entity_ids)
    return value in entity_ids


def _infer_relation_types(
    relations: list[Relation],
    symbol_types: Mapping[str, str],
) -> list[RelationType]:
    signatures: dict[str, tuple[set[str], set[str]]] = {}
    for relation in relations:
        source_types, target_types = signatures.setdefault(
            relation.predicate, (set(), set())
        )
        source_types.add(symbol_types[relation.source])
        target_types.add(symbol_types[relation.target])
    return [
        RelationType(
            id=predicate,
            source_types=tuple(sorted(source_types)),
            target_types=tuple(sorted(target_types)),
        )
        for predicate, (source_types, target_types) in signatures.items()
    ]


def _infer_frame(robot_id: str, topic_id: str) -> str:
    slug = topic_id.split(".")[-1]
    known = {
        "imu_chest": "chest_imu",
        "imu_torso": "torso_imu",
        "mc_body_pose": "base_link",
        "rgbd_front_pointcloud": "rgbd_head_front",
        "lidar_pointcloud": "lidar_chest_front",
    }
    frame = known.get(slug)
    return f"{robot_id}.frame.{frame}" if frame else ""


def _apply_observability(
    sources: list[ObservationSource],
    boundaries: list[EvidenceBoundary],
) -> list[ObservationSource]:
    boundary_by_subject = {item.subject: item for item in boundaries}
    updated: list[ObservationSource] = []
    for source in sources:
        subject = ""
        if "joint" in source.id and "state" in source.id:
            subject = "joint_state"
        elif "imu_chest" in source.id:
            subject = "chest_imu"
        boundary = boundary_by_subject.get(subject)
        if boundary is None:
            updated.append(source)
            continue
        updated.append(
            ObservationSource(
                id=source.id,
                binding=source.binding,
                value_type=source.value_type,
                frame=source.frame,
                nominal_rate_hz=source.nominal_rate_hz,
                realtime_available=boundary.realtime_available,
                durable_replay_available=boundary.durable_replay_available,
                qualification=source.qualification,
                attributes=source.attributes,
                provenance=source.provenance,
            )
        )
    return updated


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_")


def _normalize_severity(value: str) -> str:
    return {
        "warn": "warning",
        "fatal": "error",
    }.get(value.lower(), value.lower())
