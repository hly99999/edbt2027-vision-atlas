"""Deterministic serialization for immutable scientific records."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from enum import Enum
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from .paths import contains_absolute_local_path

def freeze_json(value: Any) -> Any:
    """Recursively freeze a JSON-compatible scientific payload.

    Mappings become read-only mapping proxies and sequences become tuples.  Local
    absolute paths are disallowed so content hashes remain portable and cannot
    accidentally encode machine-specific cache locations.
    """

    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return MappingProxyType(
            {
                "$enum": MappingProxyType(
                    {
                        "type": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
                        "value": freeze_json(value.value),
                    }
                )
            }
        )
    if is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                "$dataclass": MappingProxyType(
                    {
                        "type": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
                        "fields": MappingProxyType(
                            {field.name: freeze_json(getattr(value, field.name)) for field in fields(value)}
                        ),
                    }
                )
            }
        )
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not scientific JSON values")
        return value
    if isinstance(value, str):
        if contains_absolute_local_path(value):
            raise ValueError("absolute local path is not allowed in scientific payloads")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("scientific JSON mapping keys must be strings")
            frozen[key] = freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (tuple, list)):
        return tuple(freeze_json(item) for item in value)
    raise TypeError(f"unsupported scientific JSON value: {type(value).__name__}")


def _canonical_value(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, Enum):
        return {
            "$enum": {
                "type": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
                "value": _canonical_value(value.value),
            }
        }
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical JSON values")
        return value
    if isinstance(value, str):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$dataclass": {
                "type": f"{value.__class__.__module__}.{value.__class__.__qualname__}",
                "fields": {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)},
            }
        }
    if isinstance(value, Mapping):
        converted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("canonical JSON mapping keys must be strings")
            converted[key] = _canonical_value(item)
        return converted
    if isinstance(value, tuple):
        return {"$tuple": [_canonical_value(item) for item in value]}
    if isinstance(value, list):
        return {"$list": [_canonical_value(item) for item in value]}
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Return deterministic JSON with explicit tags for non-JSON Python types."""

    return json.dumps(
        _canonical_value(value),
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def scientific_hash(value: Any) -> str:
    """Hash the schema-defined scientific payload, never a local cache path."""

    frozen = freeze_json(value)
    return hashlib.sha256(canonical_json(frozen).encode("utf-8")).hexdigest()
