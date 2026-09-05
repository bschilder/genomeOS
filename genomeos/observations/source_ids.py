"""Stable source-record identities for P1 observations (literature design §5.4)."""

from __future__ import annotations

import hashlib
import json
import re

_NAMESPACE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def stable_source_record_id(namespace: str, *source_keys: object) -> str:
    """Hash a canonical source-native compound key without delimiter ambiguity."""
    if _NAMESPACE.fullmatch(namespace) is None:
        raise ValueError(f"invalid source-record namespace: {namespace!r}")
    parts = [str(value) for value in source_keys]
    if not parts or any(not value or any(char in value for char in "\t\r\n") for value in parts):
        raise ValueError("source-record keys must be non-empty scalar source values")
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    return f"{namespace}:{hashlib.sha256(payload.encode()).hexdigest()}"
