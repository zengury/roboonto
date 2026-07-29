"""RoboOnto 0.9 canonical Target PackModule.

PackModule is the normative Code-as-Object program unit.  Legacy ontology
directories are accepted only by :mod:`roboonto.compat` migration tools.
"""

from .io import dump_pack, load_pack, pack_digest, validate_schema
from .link import (
    PackLinkError,
    PackLinkManifest,
    PackRequirements,
    link_pack,
)
from .model import (
    Attribute,
    Binding,
    Capability,
    Entity,
    EntityType,
    EvidenceBoundary,
    Formula,
    Guard,
    MigrationIssue,
    ModuleHeader,
    Observation,
    ObservationSource,
    PackModule,
    PackValidationError,
    Parameter,
    Provenance,
    Relation,
    RelationType,
    ResourceSet,
    ServiceRequirement,
    TargetAction,
    TypeRef,
    TypedValue,
)

__all__ = [
    "Attribute",
    "Binding",
    "Capability",
    "Entity",
    "EntityType",
    "EvidenceBoundary",
    "Formula",
    "Guard",
    "MigrationIssue",
    "ModuleHeader",
    "Observation",
    "ObservationSource",
    "PackModule",
    "PackLinkError",
    "PackLinkManifest",
    "PackRequirements",
    "PackValidationError",
    "Parameter",
    "Provenance",
    "Relation",
    "RelationType",
    "ResourceSet",
    "ServiceRequirement",
    "TargetAction",
    "TypeRef",
    "TypedValue",
    "dump_pack",
    "load_pack",
    "link_pack",
    "pack_digest",
    "validate_schema",
]
