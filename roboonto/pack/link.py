"""RoboOnto 3.0 Duty/Execution Compiler 的 PackModule 链接契约。

Duty IR 只声明稳定的语义需求；本模块把这些需求解析到一个精确
PackModule 版本。结果是可序列化的静态 Link Manifest，不包含实时
Context、Lease、Observation 或执行状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .model import PackModule


class PackLinkError(ValueError):
    def __init__(self, diagnostics: Iterable[str]):
        self.diagnostics = tuple(diagnostics)
        super().__init__("PackModule link failed:\n- " + "\n- ".join(self.diagnostics))


@dataclass(frozen=True)
class PackRequirements:
    """Duty Compiler 写入部署描述的 Code-as-Object 依赖。"""

    pack_id: str
    pack_version: str
    content_digest: str = ""
    capabilities: tuple[str, ...] = ()
    observations: tuple[str, ...] = ()
    target_actions: tuple[str, ...] = ()

    def to_data(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_version": self.pack_version,
            "content_digest": self.content_digest or None,
            "capabilities": list(self.capabilities),
            "observations": list(self.observations),
            "target_actions": list(self.target_actions),
        }


@dataclass(frozen=True)
class PackLinkManifest:
    """Execution Compiler 可消费的、已解析且带摘要的静态链接结果。"""

    document: Mapping[str, Any]

    def to_data(self) -> dict[str, Any]:
        return _copy_data(self.document)


def link_pack(
    pack: PackModule,
    requirements: PackRequirements,
    *,
    allow_unqualified: bool = False,
) -> PackLinkManifest:
    """Resolve a Duty's pack requirements, rejecting unsafe migration gaps."""

    pack.validate()
    diagnostics: list[str] = []
    if requirements.pack_id != pack.module.id:
        diagnostics.append(
            f"requested pack {requirements.pack_id!r}, got {pack.module.id!r}"
        )
    if requirements.pack_version != pack.module.version:
        diagnostics.append(
            f"requested version {requirements.pack_version!r}, "
            f"got {pack.module.version!r}"
        )
    if not pack.module.content_digest:
        diagnostics.append("PackModule must be finalized with content_digest")
    elif (
        requirements.content_digest
        and requirements.content_digest != pack.module.content_digest
    ):
        diagnostics.append(
            f"requested digest {requirements.content_digest!r}, "
            f"got {pack.module.content_digest!r}"
        )

    capability_index = {item.id: item for item in pack.capabilities}
    observation_index = {item.id: item for item in pack.observations}
    source_index = {item.id: item for item in pack.observation_sources}
    action_index = {item.id: item for item in pack.target_actions}
    binding_index = {item.id: item for item in pack.bindings}
    resource_index = {item.id: item for item in pack.resource_sets}

    requested = {
        "capabilities": requirements.capabilities,
        "observations": requirements.observations,
        "target_actions": requirements.target_actions,
    }
    indexes = {
        "capabilities": capability_index,
        "observations": observation_index,
        "target_actions": action_index,
    }
    for category, symbols in requested.items():
        duplicate = _duplicates(symbols)
        if duplicate:
            diagnostics.append(
                f"{category} contains duplicate requirements {duplicate!r}"
            )
        missing = sorted(set(symbols) - set(indexes[category]))
        if missing:
            diagnostics.append(f"unknown {category} {missing!r}")
        exported = set(pack.exports.get(category, ()))
        private = sorted(set(symbols) - exported)
        if private:
            diagnostics.append(f"non-exported {category} {private!r}")

    resolved_capabilities = []
    for symbol in requirements.capabilities:
        capability = capability_index.get(symbol)
        if capability is None:
            continue
        if capability.qualification != "qualified" and not allow_unqualified:
            diagnostics.append(
                f"capability {symbol!r} is {capability.qualification!r}, not qualified"
            )
        resolved_capabilities.append(
            {
                "id": capability.id,
                "kind": capability.kind,
                "qualification": capability.qualification,
                "providers": list(capability.providers),
                "target_actions": list(capability.target_actions),
                "interfaces": list(capability.interfaces),
                "requirements": list(capability.requirements),
            }
        )

    resolved_observations = []
    for symbol in requirements.observations:
        observation = observation_index.get(symbol)
        if observation is None:
            continue
        if observation.qualification != "qualified" and not allow_unqualified:
            diagnostics.append(
                f"observation {symbol!r} is {observation.qualification!r}; "
                "freshness/evidence contract is not deployable"
            )
        resolved_sources = []
        for source_id in observation.sources:
            source = source_index[source_id]
            binding = binding_index[source.binding]
            resolved_sources.append(
                {
                    "id": source.id,
                    "value_type": source.value_type.to_data(),
                    "frame": source.frame or None,
                    "nominal_rate_hz": source.nominal_rate_hz,
                    "realtime_available": source.realtime_available,
                    "durable_replay_available": source.durable_replay_available,
                    "binding": binding.to_data(),
                }
            )
        resolved_observations.append(
            {
                "id": observation.id,
                "value_type": observation.value_type.to_data(),
                "qualification": observation.qualification,
                "sources": resolved_sources,
            }
        )

    resolved_actions = []
    for symbol in requirements.target_actions:
        action = action_index.get(symbol)
        if action is None:
            continue
        if not action.executable:
            diagnostics.append(
                f"target action {symbol!r} is blocked by "
                f"{list(action.blocked_reasons)!r}"
            )
        binding = binding_index[action.binding]
        resolved_actions.append(
            {
                "id": action.id,
                "legacy_id": action.legacy_id or None,
                "visibility": action.visibility,
                "parameters": [item.to_data() for item in action.parameters],
                "guards": [item.to_data() for item in action.guards],
                "binding": binding.to_data(),
                "resource_sets": [
                    resource_index[resource_id].to_data()
                    for resource_id in action.resource_sets
                ],
            }
        )

    if diagnostics:
        raise PackLinkError(diagnostics)

    return PackLinkManifest(
        {
            "link_kind": "roboonto3_pack_link",
            "link_version": "0.9",
            "pack": {
                "id": pack.module.id,
                "version": pack.module.version,
                "content_digest": pack.module.content_digest,
            },
            "capabilities": resolved_capabilities,
            "observations": resolved_observations,
            "target_actions": resolved_actions,
        }
    )


def _duplicates(values: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return sorted(duplicates)


def _copy_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _copy_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_copy_data(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"link manifest contains unsupported value {value!r}")
