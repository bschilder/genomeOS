"""Validate Atlas catalog discovery metadata for design §11."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _require_fields(value: Mapping[str, Any], fields: set[str], context: str) -> None:
    missing = fields - set(value)
    if missing:
        raise ValueError(f"{context}: missing required fields {sorted(missing)}")


def _references(value: Any, context: str) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{context}: references must be a non-empty list")
    references: list[dict[str, str]] = []
    for index, reference in enumerate(value):
        if not isinstance(reference, Mapping):
            raise ValueError(f"{context}: reference {index} must be an object")
        _require_fields(reference, {"label", "url"}, f"{context} reference {index}")
        label = str(reference["label"]).strip()
        url = str(reference["url"]).strip()
        if not label or not url.startswith("https://"):
            raise ValueError(f"{context}: references require a label and HTTPS URL")
        references.append({"label": label, "url": url})
    return references


def validate_discovery_groups(value: Any) -> list[dict[str, Any]]:
    """Return normalized, ordered catalog groups or refuse malformed metadata."""
    if not isinstance(value, list) or not value:
        raise ValueError("catalog discovery_groups must be a non-empty list")
    groups: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, group in enumerate(value):
        context = f"catalog discovery group {index}"
        if not isinstance(group, Mapping):
            raise ValueError(f"{context}: must be an object")
        _require_fields(group, {"id", "label", "summary", "biology", "references"}, context)
        normalized = {key: str(group[key]).strip() for key in ("id", "label", "summary", "biology")}
        if not all(normalized.values()) or normalized["id"] in seen:
            raise ValueError(f"{context}: text fields must be non-empty and ids unique")
        seen.add(normalized["id"])
        groups.append({**normalized, "references": _references(group["references"], context)})
    return groups


def validate_artifact_discovery(
    value: Any,
    *,
    context: str,
    group_ids: set[str],
) -> dict[str, Any]:
    """Return normalized picker metadata or refuse unknown/missing claims."""
    if not isinstance(value, Mapping):
        raise ValueError(f"{context}: discovery must be an object")
    _require_fields(
        value,
        {"group_id", "map_measures", "symbol_expansion", "relevance", "aliases", "references"},
        f"{context} discovery",
    )
    group_id = str(value["group_id"]).strip()
    aliases = value["aliases"]
    if group_id not in group_ids:
        raise ValueError(f"{context} discovery: group_id must name a known discovery group")
    if not isinstance(aliases, list) or not aliases or not all(str(alias).strip() for alias in aliases):
        raise ValueError(f"{context} discovery: aliases must be a non-empty list")
    discovery = {
        "aliases": [str(alias).strip() for alias in aliases],
        "group_id": group_id,
        "map_measures": str(value["map_measures"]).strip(),
        "references": _references(value["references"], f"{context} discovery"),
        "relevance": str(value["relevance"]).strip(),
        "symbol_expansion": str(value["symbol_expansion"]).strip(),
    }
    if not discovery["map_measures"] or not discovery["relevance"] or not discovery["symbol_expansion"]:
        raise ValueError(f"{context} discovery: explanatory text must be non-empty")
    return discovery
