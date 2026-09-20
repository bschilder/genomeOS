"""Commercial-use marking for published external resources (design §11).

NON-COMMERCIAL: genomeOS may publish data under a non-commercial licence. The condition is that
every restricted field is declared where a human reviews it, so that if a commercial component of
this project ever exists, one command lists everything that has to come out. The inventory is
`python scripts/check_commercial_use.py --list`; the register and the rules are in
docs/non-commercial-data.md.

This lives beside the exporter rather than inside it because two consumers need the same
vocabulary: the exporter, which refuses to publish an undeclared restriction, and the check script,
which turns the declarations into an extraction plan. A policy both of them enforce should not be
reachable only by importing a command-line script.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# NON-COMMERCIAL: commercial-use marking. genomeOS may publish data under a non-commercial licence,
# but every restricted field must be declared in the publish allowlist so a future commercial
# component can find and remove all of it at once. The inventory is
# `python scripts/check_commercial_use.py --list`; the register is docs/non-commercial-data.md.
#
# The vocabulary is the one the literature reuse checks already use (genomeos/observations/
# evidence.py), so a source's terms read the same wherever they are recorded. `not_checked` stays
# publishable on purpose: refusing it would push a contributor to invent a licence finding to make
# an export run, which the publication-evidence safeguards forbid. The check script lists those as
# unresolved instead, so an extraction still sees them.
COMMERCIAL_USE_FINDINGS = (
    "explicitly_open",
    "permission_granted",
    "no_restriction_found",
    "restricted",
    "not_checked",
)
COMMERCIAL_USE_EVIDENCE_FIELDS = ("checked_at", "terms_url", "recorded_in")

# NON-COMMERCIAL: fields known to carry a non-commercial restriction inside a source that is
# otherwise permissive. The restriction is field-level, not source-level: DeepMind carves the AVI
# Score out for commercial use while leaving the AVI Score Feature Breakdown non-commercial, and
# gnomAD is CC0 while the SpliceAI annotations it bundles are CC BY-NC (AGENTS.md, "Data and
# access terms"). A source-level tag would wrongly condemn the permissive half.
#
# Presence in a published record without a matching `restricted_fields` entry is a hard error, so
# restricted data can ship marked but never unmarked. Add to this list when a new restriction is
# found; never remove an entry to make an export pass.
KNOWN_NON_COMMERCIAL_FIELDS: dict[str, tuple[str, ...]] = {
    "alphagenome": ("top_attributions",),
    "gnomad": ("spliceai",),
}


def require_fields(value: Mapping[str, Any], fields: set[str], context: str) -> None:
    missing = fields - set(value)
    if missing:
        raise ValueError(f"{context}: missing required fields {sorted(missing)}")


def validate(
    resource: Mapping[str, Any],
    record: Mapping[str, Any],
    source: str,
    context: str,
) -> dict[str, Any]:
    """Validate the commercial-use declaration and return what gets published with the resource.

    NON-COMMERCIAL: this is the single gate that decides whether restricted data may ship. It
    permits publication and refuses concealment, which is the whole point: an unmarked restricted
    field is invisible to an extraction, while a marked one is one grep away.
    """
    declared = resource.get("commercial_use")
    if not isinstance(declared, Mapping):
        raise ValueError(
            f"{context}: commercial_use is required and must be an object; see "
            "docs/non-commercial-data.md"
        )
    require_fields(declared, {"finding", "restricted_fields"}, f"{context} commercial_use")
    finding = declared["finding"]
    if finding not in COMMERCIAL_USE_FINDINGS:
        raise ValueError(
            f"{context}: commercial_use finding must be one of {list(COMMERCIAL_USE_FINDINGS)}, "
            f"got {finding!r}"
        )
    fields = declared["restricted_fields"]
    if not isinstance(fields, list) or not all(isinstance(field, str) for field in fields):
        raise ValueError(f"{context}: commercial_use restricted_fields must be a list of strings")
    if len(set(fields)) != len(fields):
        raise ValueError(f"{context}: commercial_use restricted_fields must be unique")

    if finding == "restricted":
        if not fields:
            raise ValueError(
                f"{context}: a restricted commercial_use finding must name at least one restricted "
                "field, otherwise an extraction cannot tell what to remove"
            )
        absent = sorted(field for field in fields if field not in record)
        if absent:
            raise ValueError(
                f"{context}: commercial_use names a field absent from the record: "
                f"{absent}. A declaration that does not match the payload hides a rename."
            )
    elif fields:
        raise ValueError(
            f"{context}: only a restricted finding may name fields, got {finding!r} with {fields}"
        )

    published: dict[str, Any] = {"finding": finding, "restricted_fields": sorted(fields)}
    if finding != "not_checked":
        require_fields(
            declared,
            set(COMMERCIAL_USE_EVIDENCE_FIELDS),
            f"{context} commercial_use requires checked_at, terms_url and recorded_in for a "
            "performed check",
        )
        terms_url = str(declared["terms_url"])
        if not terms_url.startswith("https://"):
            raise ValueError(f"{context}: commercial_use terms_url must be https")
        for field in COMMERCIAL_USE_EVIDENCE_FIELDS:
            published[field] = str(declared[field])

    # NON-COMMERCIAL: the tripwire. A field we already know is restricted may not reach the
    # published payload unless the declaration names it.
    undeclared = sorted(
        field
        for field in KNOWN_NON_COMMERCIAL_FIELDS.get(source, ())
        if field in record and field not in fields
    )
    if undeclared:
        raise ValueError(
            f"{context}: undeclared non-commercial field {undeclared}. {source} publishes this "
            "under a non-commercial licence; declare it in commercial_use.restricted_fields with "
            'finding "restricted", or drop it from the payload.'
        )
    return published
