"""Strict acquisition-manifest JSON codec (reference acquisition design §6.1)."""

from __future__ import annotations

import json
import types
from dataclasses import fields, is_dataclass
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from genomeos.validation.reference_acquisition_types import (
    AcquisitionManifest,
    AcquisitionReviewBundle,
    ReviewReceipt,
)

_MAPPING_FIELDS = frozenset(
    {
        "policy",
        "implementation_sha256",
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


def encode_acquisition(value: AcquisitionManifest) -> bytes:
    """Encode a validated acquisition manifest as canonical, timestamp-free JSON."""
    _require(type(value) is AcquisitionManifest, "value must be AcquisitionManifest")
    return (json.dumps(_wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def _encode_record(value: object, expected: type, field_name: str) -> bytes:
    _require(type(value) is expected, f"value must be {expected.__name__}")
    return (json.dumps(_wire(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode("utf-8")


def decode_acquisition(raw: bytes) -> AcquisitionManifest:
    """Decode canonical JSON with exact keys and reconstruct every nested record."""
    _require(type(raw) is bytes and bool(raw), "acquisition manifest must be nonempty bytes")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=lambda value: (_ for _ in ()).throw(ValueError(f"float is forbidden: {value}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid acquisition JSON") from error
    value = _typed(document, AcquisitionManifest, field_name="acquisition")
    _require(type(value) is AcquisitionManifest, "invalid acquisition manifest")
    _require(encode_acquisition(value) == raw, "acquisition JSON bytes are not canonical")
    return value


def encode_review(value: ReviewReceipt) -> bytes:
    """Encode an independently supplied preflight review receipt."""
    return _encode_record(value, ReviewReceipt, "review")


def decode_review(raw: bytes) -> ReviewReceipt:
    """Decode a canonical independently supplied preflight review receipt."""
    _require(type(raw) is bytes and bool(raw), "review must be nonempty bytes")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=lambda value: (_ for _ in ()).throw(ValueError(f"float is forbidden: {value}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid review JSON") from error
    value = _typed(document, ReviewReceipt, field_name="review")
    _require(type(value) is ReviewReceipt and encode_review(value) == raw,
             "review JSON bytes are not canonical")
    return value


def encode_acquisition_review(value: AcquisitionReviewBundle) -> bytes:
    """Encode the accepted preflight and current acquisition implementation reviews."""
    return _encode_record(value, AcquisitionReviewBundle, "acquisition review")


def decode_acquisition_review(raw: bytes) -> AcquisitionReviewBundle:
    """Decode one canonical review bundle that binds both required review decisions."""
    _require(type(raw) is bytes and bool(raw), "acquisition review must be nonempty bytes")
    try:
        document = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_constant,
            parse_float=lambda value: (_ for _ in ()).throw(ValueError(f"float is forbidden: {value}")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("invalid acquisition review JSON") from error
    value = _typed(document, AcquisitionReviewBundle, field_name="acquisition review")
    _require(
        type(value) is AcquisitionReviewBundle and encode_acquisition_review(value) == raw,
        "acquisition review JSON bytes are not canonical",
    )
    return value
