#!/usr/bin/env python3
"""Inventory and gate the commercial-use marking on every published external resource.

NON-COMMERCIAL: genomeOS may publish data under a non-commercial licence. The condition is that
every restricted field is *declared* where a human reviews it, so that if a commercial component
of this project ever exists, one command lists everything that has to come out:

    python scripts/check_commercial_use.py --list

Run with no arguments it is a CI gate: it refuses a declaration that is missing, malformed, or
inconsistent between the allowlist a human edits and the catalog that actually shipped. It does
*not* refuse `not_checked`. An unperformed check is an honest state, and refusing it would push a
contributor to invent a licence finding to make the build pass — the exact fabrication the
publication-evidence safeguards in AGENTS.md forbid. Unchecked sources are reported as unresolved
instead, because for an extraction "unknown terms" is as actionable as "known restricted".

The register of what is restricted and why is docs/non-commercial-data.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.publication.commercial_use import (  # noqa: E402  (path set above)
    COMMERCIAL_USE_EVIDENCE_FIELDS,
    COMMERCIAL_USE_FINDINGS,
    KNOWN_NON_COMMERCIAL_FIELDS,
)

ALLOWLIST = ROOT / "website/src/atlas/public-artifacts.json"
CATALOG = ROOT / "website/public/data/atlas/catalog.json"


def _resources(path: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every external resource in a catalog-shaped file, tagged with its artifact id."""
    if not path.exists():
        return []
    document = json.loads(path.read_text(encoding="utf-8"))
    return [
        (str(entry.get("id", "?")), resource)
        for entry in document.get("artifacts", [])
        for resource in entry.get("external_resources", [])
    ]


def _problems(where: str, artifact_id: str, resource: dict[str, Any]) -> list[str]:
    source = str(resource.get("source", "?"))
    label = f"{where}: {artifact_id}/{source}"
    declared = resource.get("commercial_use")
    if not isinstance(declared, dict):
        return [f"{label}: no commercial_use declaration"]

    found: list[str] = []
    finding = declared.get("finding")
    if finding not in COMMERCIAL_USE_FINDINGS:
        found.append(f"{label}: finding {finding!r} is outside the closed vocabulary")
    fields = declared.get("restricted_fields")
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        found.append(f"{label}: restricted_fields must be a list of strings")
        fields = []
    if finding == "restricted" and not fields:
        found.append(f"{label}: a restricted finding must name the fields it restricts")
    if finding != "restricted" and fields:
        found.append(f"{label}: only a restricted finding may name fields, got {finding!r}")
    if finding in COMMERCIAL_USE_FINDINGS and finding != "not_checked":
        missing = [f for f in COMMERCIAL_USE_EVIDENCE_FIELDS if not declared.get(f)]
        if missing:
            found.append(f"{label}: a performed check must record {missing}")
    if finding == "not_checked" and any(declared.get(f) for f in COMMERCIAL_USE_EVIDENCE_FIELDS):
        found.append(f"{label}: not_checked must not carry evidence fields")
    return found


def _drift() -> list[str]:
    """The allowlist is what a human edits; the catalog is what shipped. They must agree."""
    shipped = {
        (artifact_id, str(r.get("source"))): r.get("commercial_use")
        for artifact_id, r in _resources(CATALOG)
    }
    found: list[str] = []
    for artifact_id, resource in _resources(ALLOWLIST):
        key = (artifact_id, str(resource.get("source")))
        if key not in shipped:
            continue  # declared but not yet exported; the exporter is the gate for that
        if shipped[key] != _publishable(resource.get("commercial_use")):
            found.append(
                f"catalog drift: {key[0]}/{key[1]} shipped a different commercial_use than the "
                "allowlist declares; re-run scripts/export_atlas_web.py"
            )
    return found


def _publishable(declared: Any) -> Any:
    """The subset of a declaration the exporter publishes, for comparing the two files."""
    if not isinstance(declared, dict):
        return declared
    out: dict[str, Any] = {
        "finding": declared.get("finding"),
        "restricted_fields": sorted(declared.get("restricted_fields", [])),
    }
    if declared.get("finding") != "not_checked":
        for field in COMMERCIAL_USE_EVIDENCE_FIELDS:
            out[field] = str(declared.get(field, ""))
    return out


def inventory() -> tuple[list[str], list[str]]:
    """(restricted, unresolved) — the two halves of what a commercial build must deal with."""
    restricted: list[str] = []
    unresolved: list[str] = []
    for artifact_id, resource in _resources(ALLOWLIST):
        declared = resource.get("commercial_use")
        if not isinstance(declared, dict):
            continue
        source = str(resource.get("source"))
        cache = str(resource.get("cache_file", "?"))
        if declared.get("finding") == "restricted":
            for field in sorted(declared.get("restricted_fields", [])):
                restricted.append(
                    f"{artifact_id}\t{source}\t{cache}\trecord.{field}\t"
                    f"{declared.get('terms_url', '')}\t{declared.get('recorded_in', '')}"
                )
        elif declared.get("finding") == "not_checked":
            unresolved.append(f"{artifact_id}\t{source}\t{cache}\tterms never read")
    return restricted, unresolved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--list",
        action="store_true",
        help="print the extraction inventory instead of running the gate",
    )
    args = parser.parse_args(argv)

    if args.list:
        restricted, unresolved = inventory()
        print("# Non-commercial data that a commercial component must remove")
        print("# artifact\tsource\tcache_file\tfield\tterms_url\trecorded_in")
        print("\n".join(restricted) if restricted else "# (none)")
        print()
        print("# Sources whose commercial terms have never been checked")
        print("# artifact\tsource\tcache_file\tstatus")
        print("\n".join(unresolved) if unresolved else "# (none)")
        print()
        print("# Known field-level restrictions the exporter refuses to publish undeclared:")
        for source, fields in sorted(KNOWN_NON_COMMERCIAL_FIELDS.items()):
            print(f"#   {source}: {', '.join(fields)}")
        return 0

    problems = _drift()
    checked = 0
    for where, path in (("allowlist", ALLOWLIST), ("catalog", CATALOG)):
        for artifact_id, resource in _resources(path):
            checked += 1
            problems.extend(_problems(where, artifact_id, resource))

    if problems:
        print("Commercial-use marking problems:")
        print("\n".join(f"- {problem}" for problem in problems))
        print("\nSee docs/non-commercial-data.md for what each finding means.")
        return 1
    restricted, unresolved = inventory()
    print(
        f"commercial-use check passed ({checked} declarations; "
        f"{len(restricted)} restricted field(s), {len(unresolved)} unchecked source(s))"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
