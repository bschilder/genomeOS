#!/usr/bin/env python3
"""Reconcile every committed search manifest against the raw payload it was derived from.

A committed manifest is a claim about what a search returned, and the payload is the only thing that
can contradict it. That is why `docs/literature-evidence-curation.md` requires the raw response be
committed next to the manifest it produced: "A manifest whose payload was not kept cannot be
replayed, re-screened, or audited by anyone who was not present when it was run."

`fetch_pubmed_manifest.py` already refuses a payload whose `count` disagrees with its returned
`idlist` at fetch time, for the reason the doc gives: "a truncated or paginated response otherwise
becomes a short, confident-looking manifest." This is that refusal applied to the artifacts as
*committed*, so the defect fails where it is authored rather than at the next reviewer's
re-execution (#272). The lct-enattah-2007 slice merged with a Q3 recording 25 candidates for a query
matching 58, and nothing about the file looked wrong.

The rule, for every corpus whose PROVENANCE.json declares a discovery block (design §5.1, §5.3):

1. each declared payload parses as an ESearch response, its PMIDs are numeric and unique, and its
   own `count` equals the length of its `idlist`;
2. the manifest rows carrying that payload's `(search_id, manifest_version)` reproduce the payload
   exactly — one candidate per identifier, same set, same count.

Two details are load-bearing, and both are shapes that exist on `main` today:

- A manifest is identified by its **header**, never by its filename. A corpus directory also holds
  `evidence.tsv` and `field_evidence.tsv`; reading those as manifests reports them as truncated.
- Rows are selected by `(search_id, manifest_version)`, **not** `search_id` alone. Screening
  republishes a discovery snapshot under a new version while keeping the same identifier, and the
  committed hbb corpus carries the same three identifiers in both files. Matching on the identifier
  alone compares a payload against the union of a discovery and a screening manifest.

Identifiers are re-derived with `make_search_id` rather than read from the file, so a manifest cannot
pass by agreeing with itself. Deterministic, offline, and secret-free by construction: it reads
committed data and executes nothing from the contribution.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from genomeos.observations.evidence import make_search_id  # noqa: E402  (path set above)

# The core of the documented manifest header. Checked as a subset so a new column does not have to be
# added here, while a file that is not a search manifest is still refused.
MANIFEST_COLUMNS = frozenset({"search_id", "candidate_id", "manifest_version"})
DEFAULT_FIXTURES = Path("tests/fixtures/literature")


class Corpus(NamedTuple):
    """One corpus directory's verdict."""

    problems: list[str]
    lines: list[str]
    examined: bool


def read_manifest(path: Path) -> list[dict[str, str]] | None:
    """Rows of a search manifest, or None when the file is not one."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or not MANIFEST_COLUMNS.issubset(reader.fieldnames):
            return None
        return list(reader)


def payload_identifiers(path: Path) -> tuple[list[str], list[str]]:
    """`(idlist, problems)` for a committed ESearch payload, validating rather than trusting it."""
    try:
        result = json.loads(path.read_text(encoding="utf-8"))["esearchresult"]
        count, idlist = int(result["count"]), list(result["idlist"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        return [], [f"{path.name}: not a readable ESearch payload ({error})"]

    problems = []
    if count != len(idlist):
        problems.append(f"{path.name}: payload count {count} does not equal its idlist length {len(idlist)}")
    if wrong := [pmid for pmid in idlist if not pmid.isdigit()]:
        problems.append(f"{path.name}: non-numeric PMIDs {wrong[:3]}")
    if repeated := sorted(pmid for pmid, occurrences in Counter(idlist).items() if occurrences > 1):
        problems.append(f"{path.name}: duplicate PMIDs {repeated[:3]}")
    return idlist, problems


def inspect(corpus: Path) -> Corpus:
    """Reconcile one corpus directory. Empty `problems` means it reconciles."""
    provenance_path = corpus / "PROVENANCE.json"
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Corpus(
            [f"{corpus.name}: PROVENANCE.json is not readable JSON ({error})"],
            [f"{corpus.name}: malformed provenance"],
            True,
        )
    if not isinstance(provenance, dict):
        return Corpus(
            [f"{corpus.name}: PROVENANCE.json must contain a JSON object"],
            [f"{corpus.name}: malformed provenance"],
            True,
        )
    discovery = provenance.get("discovery")
    if not discovery:
        return Corpus([], [f"{corpus.name}: no discovery block with payloads"], False)
    if not isinstance(discovery, dict):
        return Corpus(
            [f"{corpus.name}: discovery must contain a JSON object"],
            [f"{corpus.name}: malformed discovery block"],
            True,
        )
    queries, version = discovery.get("queries"), discovery.get("manifest_version")
    if not isinstance(version, str) or not version.strip():
        return Corpus(
            [f"{corpus.name}: discovery is missing required field manifest_version"],
            [f"{corpus.name}: malformed discovery block"],
            True,
        )
    if not isinstance(queries, list) or not queries:
        return Corpus(
            [f"{corpus.name}: discovery is missing a nonempty queries array"],
            [f"{corpus.name}: malformed discovery block"],
            True,
        )

    manifests = {
        path.name: rows
        for path in sorted(corpus.glob("*.tsv"))
        if (rows := read_manifest(path)) is not None
    }

    problems: list[str] = []
    lines = [f"{corpus.name}  ({version}, {len(manifests)} manifest file(s))"]
    for index, query in enumerate(queries):
        if not isinstance(query, dict):
            problems.append(f"{corpus.name}/query[{index}]: query declaration must be an object")
            continue
        name_value = query.get("name")
        name = name_value if isinstance(name_value, str) and name_value.strip() else f"query[{index}]"
        missing = [
            field
            for field in ("query", "executed_at", "payload")
            if not isinstance(query.get(field), str) or not query[field].strip()
        ]
        if missing:
            label = "field" if len(missing) == 1 else "fields"
            problems.append(f"{corpus.name}/{name}: missing required {label} {', '.join(missing)}")
            continue
        payload = corpus / query["payload"]
        if not payload.exists():
            problems.append(f"{corpus.name}/{name}: declared payload {payload.name} is absent")
            continue

        idlist, found = payload_identifiers(payload)
        problems += [f"{corpus.name}/{name}: {item}" for item in found]

        search_id = make_search_id("pubmed", query["query"], query["executed_at"])
        recorded = [
            row["candidate_id"].removeprefix("pmid:")
            for rows in manifests.values()
            for row in rows
            if row.get("search_id") == search_id and row.get("manifest_version") == version
        ]
        same_set = set(recorded) == set(idlist)
        if len(recorded) != len(idlist):
            problems.append(
                f"{corpus.name}/{name}: manifest records {len(recorded)} candidate(s) under {version} "
                f"for a payload matching {len(idlist)}"
            )
        elif not same_set:
            unexpected = sorted(set(recorded) - set(idlist))
            absent = sorted(set(idlist) - set(recorded))
            problems.append(
                f"{corpus.name}/{name}: manifest candidate set differs from the declared payload: "
                f"{len(unexpected)} candidate(s) not in the declared payload "
                f"({unexpected[:3]}), and {len(absent)} payload identifier(s) absent from the "
                f"manifest ({absent[:3]})"
            )
        lines.append(f"  {name}: payload {len(idlist)} identifier(s), manifest {len(recorded)} row(s), "
                     f"set match {same_set}")
    return Corpus(problems, lines, True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fixtures-root",
        default=str(DEFAULT_FIXTURES),
        help="directory holding corpus fixtures (default: %(default)s, relative to the repo root)",
    )
    parser.add_argument("--corpus", default=None, help="check only this corpus directory name")
    arguments = parser.parse_args(argv)

    root = Path(arguments.fixtures_root)
    root = root if root.is_absolute() else ROOT / root
    if not root.is_dir():
        print(f"fixtures root not found: {root}")
        return 1

    corpora = [p for p in sorted(root.iterdir()) if (p / "PROVENANCE.json").is_file()]
    if arguments.corpus:
        corpora = [p for p in corpora if p.name == arguments.corpus]

    problems: list[str] = []
    examined = 0
    for corpus in corpora:
        result = inspect(corpus)
        problems += result.problems
        examined += result.examined
        print("\n".join(result.lines))

    if problems:
        print("\nManifest/payload reconciliation failed:")
        print("\n".join(f"- {problem}" for problem in problems))
        count_mismatch = any(
            "manifest records" in problem or "payload count" in problem for problem in problems
        )
        set_mismatch = any("candidate set differs" in problem for problem in problems)
        if count_mismatch:
            print(
                "\nA manifest recording fewer candidates than the payload matched is a truncated or\n"
                "paginated capture, not a screened one, and it is indistinguishable from a complete one\n"
                "once committed. Re-fetch with scripts/fetch_pubmed_manifest.py (retmax=100000 refuses\n"
                "this disagreement) and publish the result as a new manifest_version over the corrected\n"
                "snapshot, stating which version it supersedes. Never edit a published manifest in place."
            )
        if set_mismatch:
            print(
                "\nA same-size candidate-set disagreement is a provenance gap, not pagination. Restore\n"
                "the identifiers returned by the declared payload, or declare and retain the actual\n"
                "source that introduced the substituted candidate. Never edit a published manifest in\n"
                "place."
            )
        return 1
    print(f"\nmanifest/payload reconciliation passed ({examined} corpora)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
