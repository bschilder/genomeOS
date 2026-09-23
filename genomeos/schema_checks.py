"""Shared column checks for required free-text fields (design §12).

A required field can be empty in more ways than being empty. `str_length(min_value=1)` accepts a
single space, while published tables also use literal words such as `NA`, `None`, `null`, and
`Unknown` where they have nothing to say. Those two cases need different treatment: blank text is
absent and must fail, while a printed placeholder is source evidence that must survive with a warning
for human review.

That matters here more than it would elsewhere. The contributor contract is explicit: never turn
uncertainty or missingness into plausible metadata, and it names sample and cohort identity, assay,
citation, source locator and reviewer among the things that must not be invented. The schema already
has designated ways to record absence — `not_reviewed`, `not_reported`, `ambiguous`, `not_checked` —
and the point of them is that a reader can tell a recorded absence from a recorded value. A stored
`"NA"` must therefore remain visible and attract review rather than being silently trusted or
silently discarded.

A genuine null is already refused by `nullable=False`, and our own writes cannot produce these: a
null written to TSV comes back as an empty string or a null, both refused. The path this closes is an
upstream source file that spells its missing values, which is ordinary in biological data and which
we read faithfully because `keep_default_na=False` is what protects numeric precision (#228).

**The vocabulary is not new.** `FAKE_MISSING` is the set the literature evidence layer has always
used, lifted here unchanged so there is one list rather than two drifting ones. That layer applies it
imperatively to particular fields; this module makes the same judgement available as a warning for
every schema. Matching is case-insensitive against the whole stripped value, never a substring, so
`NAT2` and `Nancy` are untouched.

Note what is *absent* from the set, deliberately: `.` is VCF's own missing marker but also appears
inside real identifiers, and rejecting valid data is worse than the gap this closes (#340).

The warning is deliberately advisory because a source can legitimately use one of these literals.
AFND, for example, prints `Unknown` in controlled-vocabulary fields. Human review decides whether a
literal is a real category or missing metadata; validation preserves the evidence needed to decide.
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa

#: Spellings that commonly mean "no value" and therefore require review. Compared
#: case-insensitively against the whole stripped cell. This is the literature layer's
#: long-standing list.
FAKE_MISSING: frozenset[str] = frozenset(
    {"na", "n/a", "unknown", "none", "null", "-", "tbd", "not reported"}
)


_BLANK_ERROR = "required text must contain at least one non-whitespace character"
_SUSPECT_WARNING = (
    "this value resembles a spelling of absence "
    f"({', '.join(sorted(FAKE_MISSING))}). It has been preserved for human review. Confirm whether "
    "the source intended a real literal value or missing metadata; missingness must use the "
    "field's explicit recorded state rather than looking like trusted metadata."
)


# Registered with pandera's extension API rather than built as a plain `pa.Check`, and the reason
# is not cosmetic. Pandera serialises only *registered* checks into schema statistics: an anonymous
# check is dropped with a warning, so `scripts/freeze_contract.py` would write a contract that did
# not mention it and `--check` would then report no drift. The frozen contract is this project's
# review surface for schema change, so a check invisible to it is worse than no check — the guard
# would be real in code and absent from the artifact people review.
@pa.extensions.register_check_method(statistics=[], supported_types=pd.Series)
def meaningful_text(series: pd.Series) -> pd.Series:
    """True where text does not resemble a conventional missing-value spelling."""
    stripped = series.astype("string").str.strip()
    return ~stripped.str.casefold().isin(FAKE_MISSING)


@pa.extensions.register_check_method(statistics=[], supported_types=pd.Series)
def non_blank_text(series: pd.Series) -> pd.Series:
    """True where required text contains at least one non-whitespace character."""
    return series.astype("string").str.strip().str.len().gt(0)


#: Required free text must be present, while suspicious literals are preserved with a warning.
#: Keeping these as separate registered checks makes the blocking and advisory behavior visible in
#: frozen schema contracts.
REVIEWABLE_TEXT = [
    pa.Check.non_blank_text(error=_BLANK_ERROR),
    pa.Check.meaningful_text(error=_SUSPECT_WARNING, raise_warning=True),
]


@pa.extensions.register_check_method(statistics=[], supported_types=pd.Series)
def non_empty_text(series: pd.Series) -> pd.Series:
    """True where the value is not the empty string. Judges nothing else about it."""
    return series.astype("string").str.len().gt(0)


#: For columns whose contract is to preserve a source's literal value. They refuse an empty cell
#: and judge nothing else.
#:
#: `population_aliases.label` is the case this category exists for. The alias table records what a
#: source called a population, so it cannot also rule on whether that looks like a value — a source
#: is entitled to use a code we would not have chosen, and silently refusing it would lose the
#: record of what was actually published.
VERBATIM_TEXT = pa.Check.non_empty_text(
    error="a verbatim source value may be anything except empty"
)

#: The other half of the verbatim bargain: keep the value, but say something.
#:
#: A verbatim column accepts `NA` because a source may mean it. It is also, far more often, a source
#: that had nothing to say — so validating in silence would let a missing population label enter the
#: registry looking like a recorded one. `raise_warning=True` makes this a remark rather than a
#: refusal: the row is admitted, and a submitter or reviewer is told which value to look at.
#:
#: This is the deliberate middle of the two wrong answers. Refusing would reject data a source
#: legitimately published; accepting quietly would turn missingness into metadata, which AGENTS.md
#: forbids by name. Neither is acceptable, so the record stays faithful and a human is put in the
#: loop (#340).
SUSPECT_VERBATIM_TEXT = pa.Check.meaningful_text(
    error=(
        "this reads like a spelling of absence rather than a name "
        f"({', '.join(sorted(FAKE_MISSING))}). It has been kept, because a verbatim column records "
        "what the source said. Check whether the source meant a real value or had none: if it had "
        "none, the row should not carry an invented identity."
    ),
    raise_warning=True,
)
