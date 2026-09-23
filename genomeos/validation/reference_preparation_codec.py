"""Strict preparation-manifest JSON codec (reference acquisition design §6.1)."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from genomeos.validation.reference_preparation_types import (
    DependencyEvidence,
    PreparationInputs,
    PreparationManifest,
)

_MAPPING_FIELDS = frozenset(
    {
        "policy",
        "imported_source_sha256",
        "tool_versions",
        "executable_sha256",
        "sdk_source_sha256",
    }
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        _require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON value: {value}")


def _wire(value: object, *, field_name: str | None = None) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _wire(getattr(value, field.name), field_name=field.name)
            for field in fields(value)
        }
    if isinstance(value, tuple):
        if field_name in _MAPPING_FIELDS:
            result: dict[str, object] = {}
            for item in value:
                _require(type(item) is tuple and len(item) == 2 and isinstance(item[0], str),
                         f"invalid {field_name} mapping")
                _require(item[0] not in result, f"duplicate {field_name} key")
                result[item[0]] = _wire(item[1])
            return result
        return [_wire(item) for item in value]
    _require(value is None or type(value) in (str, int, bool), "unsupported manifest value")
    return value


def _mapping_tuple(value: object, field_name: str) -> object:
    if field_name not in _MAPPING_FIELDS:
        return value
    _require(type(value) is dict, f"{field_name} must be an object")
    return tuple(sorted(value.items()))


def _typed(value: object, annotation: object, *, field_name: str) -> object:
    value = _mapping_tuple(value, field_name)
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        _require(any(type(value) is type(option) and value == option for option in arguments),
                 f"invalid {field_name} literal")
        return value
    if origin in (types.UnionType, Union):
        for candidate in arguments:
            try:
                return _typed(value, candidate, field_name=field_name)
            except (TypeError, ValueError):
                pass
        raise ValueError(f"invalid {field_name} union")
    if origin is tuple:
        _require(type(value) in (list, tuple), f"{field_name} must be an array")
        items = tuple(value)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_typed(item, arguments[0], field_name=f"{field_name} item") for item in items)
        _require(len(items) == len(arguments), f"invalid {field_name} array length")
        return tuple(
            _typed(item, expected, field_name=f"{field_name} item")
            for item, expected in zip(items, arguments, strict=True)
        )
    if annotation is type(None):
        _require(value is None, f"{field_name} must be null")
        return None
    if annotation in (str, int, bool):
        _require(type(value) is annotation, f"invalid {field_name} type")
        return value
    if isinstance(annotation, type) and is_dataclass(annotation):
        _require(type(value) is dict, f"{field_name} must be an object")
        declared = fields(annotation)
        _require(set(value) == {field.name for field in declared}, f"invalid {field_name} fields")
        hints = get_type_hints(annotation)
        return annotation(
            **{
                field.name: _typed(value[field.name], hints[field.name], field_name=field.name)
                for field in declared
            }
        )
    raise TypeError(f"unsupported annotation for {field_name}")


def encode_preparation(value: PreparationManifest) -> bytes:
    """Encode a validated preparation manifest as canonical, timestamp-free JSON."""
    _require(type(value) is PreparationManifest, "value must be PreparationManifest")
    return (json.dumps(_wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _encode_record(value: object, expected: type, field_name: str) -> bytes:
    _require(type(value) is expected, f"value must be {expected.__name__}")
    return (json.dumps(_wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def decode_preparation(raw: bytes) -> PreparationManifest:
    """Decode canonical JSON with exact keys and reconstruct every nested record."""
    _require(type(raw) is bytes and bool(raw), "preparation manifest must be nonempty bytes")
    document = _document(raw, "preparation")
    value = _typed(document, PreparationManifest, field_name="preparation")
    _require(type(value) is PreparationManifest, "invalid preparation manifest")
    _require(encode_preparation(value) == raw, "preparation JSON bytes are not canonical")
    return value


def _document(raw: bytes, field_name: str) -> object:
    _require(type(raw) is bytes and bool(raw), f"{field_name} must be nonempty bytes")
    try:
        return json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=lambda value: (_ for _ in ()).throw(ValueError(f"float is forbidden: {value}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid {field_name} JSON") from error


def encode_dependency(value: DependencyEvidence) -> bytes:
    """Encode one strict population-dependency sidecar."""
    return _encode_record(value, DependencyEvidence, "dependency")


def decode_dependency(raw: bytes) -> DependencyEvidence:
    """Decode and require canonical population-dependency evidence."""
    value = _typed(_document(raw, "dependency"), DependencyEvidence, field_name="dependency")
    _require(type(value) is DependencyEvidence and encode_dependency(value) == raw,
             "dependency JSON bytes are not canonical")
    return value


def encode_preparation_inputs(value: PreparationInputs) -> bytes:
    """Encode the exact preparation-input binding sidecar."""
    return _encode_record(value, PreparationInputs, "preparation inputs")


def decode_preparation_inputs(raw: bytes) -> PreparationInputs:
    """Decode and require a canonical preparation-input binding."""
    value = _typed(_document(raw, "preparation inputs"), PreparationInputs, field_name="inputs")
    _require(type(value) is PreparationInputs and encode_preparation_inputs(value) == raw,
             "preparation inputs JSON bytes are not canonical")
    return value
