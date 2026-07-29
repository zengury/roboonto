"""Canonical YAML/JSON I/O and stable PackModule hashing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import yaml
from jsonschema import Draft202012Validator

from .model import PackModule

SCHEMA_PATH = Path(__file__).with_name("packmodule.schema.json")


def validate_schema(data: Mapping[str, Any]) -> None:
    """Validate serialized data independently from Python model construction."""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(data),
        key=lambda error: tuple(str(part) for part in error.absolute_path),
    )
    if errors:
        rendered = []
        for error in errors:
            path = ".".join(str(part) for part in error.absolute_path) or "<root>"
            rendered.append(f"{path}: {error.message}")
        raise ValueError("PackModule schema validation failed:\n- " + "\n- ".join(rendered))


def canonical_json_bytes(pack: PackModule) -> bytes:
    return json.dumps(
        pack.to_data(include_digest=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def pack_digest(pack: PackModule) -> str:
    return "sha256:" + hashlib.sha256(canonical_json_bytes(pack)).hexdigest()


def dump_pack(pack: PackModule, path: str | Path) -> PackModule:
    """Validate, hash, and write a deterministic canonical PackModule."""

    pack.validate()
    finalized = pack.with_digest(pack_digest(pack))
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    data = finalized.to_data()
    validate_schema(data)
    if target.suffix.lower() == ".json":
        text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    elif target.suffix.lower() in {".yaml", ".yml"}:
        text = yaml.safe_dump(
            data,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )
    else:
        raise ValueError("PackModule output must end in .json, .yaml, or .yml")
    target.write_text(text, encoding="utf-8")
    return finalized


def load_pack(path: str | Path, *, verify_digest: bool = True) -> PackModule:
    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data: Any = json.loads(text)
    elif source.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        raise ValueError("PackModule input must end in .json, .yaml, or .yml")
    if not isinstance(data, Mapping):
        raise ValueError(f"{source} must contain a mapping")
    validate_schema(data)
    pack = PackModule.from_data(data)
    if verify_digest:
        actual = pack_digest(pack)
        if not pack.module.content_digest:
            raise ValueError(f"{source} has no module.content_digest")
        if pack.module.content_digest != actual:
            raise ValueError(
                f"{source} digest mismatch: declared {pack.module.content_digest}, "
                f"computed {actual}"
            )
    return pack
