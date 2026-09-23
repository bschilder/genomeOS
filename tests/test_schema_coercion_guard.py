"""No coercing schema may silently truncate a fraction into a count.

Pandera coerces *before* it checks, so a column declared as a plain numpy integer turns 200.5 into
200 and then validates the 200. The measured value and the invented one are indistinguishable once
stored, which is what §12 forbids: a bad value fails the build, it is not quietly repaired.

Worse, the truncation happens before cross-field checks run, so it can manufacture conformance to
the very invariant a check exists to enforce — an allele count of 200.9 against a denominator of 200
passed `ac_le_an` on `main` because it was cut down to 200 first (#192, fixed in #323).

The guard below is deliberately **behavioural rather than nominal**. It does not ask what a column's
dtype is called; it hands the dtype a fraction and asks what happens. A future column that truncates
is caught however it is spelled, and a safe one is never flagged for being unfamiliar.
"""

from __future__ import annotations

import importlib
import pkgutil

import pandas as pd
import pandera.pandas as pa
import pytest

import genomeos
from genomeos.schema_checks import FAKE_MISSING, REVIEWABLE_TEXT

FRACTION = pd.Series([1.5])


def _schemas() -> list[tuple[str, str, pa.DataFrameSchema]]:
    """Every DataFrameSchema reachable by importing the package, deduplicated by identity."""
    found: dict[int, tuple[str, str, pa.DataFrameSchema]] = {}
    for module_info in pkgutil.walk_packages(genomeos.__path__, "genomeos."):
        try:
            module = importlib.import_module(module_info.name)
        except Exception:  # noqa: BLE001 — an optional extra that is not installed is not our concern
            continue
        for attribute in dir(module):
            value = getattr(module, attribute, None)
            if isinstance(value, pa.DataFrameSchema):
                found.setdefault(id(value), (module_info.name, attribute, value))
    return sorted(found.values(), key=lambda item: (item[0], item[1]))


def _truncates(column: pa.Column) -> bool:
    """True when this column's dtype turns 1.5 into the integer 1 instead of refusing it.

    Narrow on purpose. A string column coerces 1.5 to "1.5", which is a representation change and
    not a truncation, so only a result that is genuinely an integer counts as an offence.
    """
    try:
        coerced = column.dtype.try_coerce(FRACTION)
    except Exception:  # noqa: BLE001 — any refusal is the behaviour we want
        return False
    if not pd.api.types.is_integer_dtype(coerced):
        return False
    return bool(coerced.iloc[0] != FRACTION.iloc[0])


def test_the_walk_finds_the_schemas_it_is_supposed_to_guard():
    """A guard that silently walks nothing would pass forever.

    This is the assertion that makes the rest of the file mean something: if the discovery breaks,
    or a schema moves, this fails rather than the guard quietly covering an empty set.
    """
    names = {schema.name for _, _, schema in _schemas()}
    assert {"observations", "carrier_observations", "cpic_coverage"} <= names
    assert len(names) >= 8


@pytest.mark.parametrize("module, attribute, schema", _schemas(), ids=lambda v: getattr(v, "name", ""))
def test_no_coercing_schema_truncates_a_fraction(module: str, attribute: str, schema):
    """Every integer-like column in a coercing schema must refuse 1.5, not store 1."""
    if not schema.coerce:
        pytest.skip(f"{attribute} does not coerce, so its checks see the value as supplied")
    offenders = sorted(name for name, column in schema.columns.items() if _truncates(column))
    assert offenders == [], (
        f"{module}.{attribute} ({schema.name}) coerces, and these columns truncate a fraction "
        f"into a whole number instead of refusing it: {offenders}. Declare them as pandas' "
        f'nullable "Int64" rather than a plain numpy integer — it raises on a non-integral value '
        "while still accepting an integral float like 3.0. See #192, #323 and #338."
    )


# ---------------------------------------------------------------------------
# A required field can be empty in more ways than being empty (#340)
# ---------------------------------------------------------------------------

BLANKS = [" ", "\t", "   "]


def _accepts(column: pa.Column, value: str) -> bool:
    """True when every blocking check on this column passes for `value`."""
    series = pd.Series([value], dtype=object)
    try:
        coerced = column.dtype.try_coerce(series)
    except Exception:  # noqa: BLE001 — a dtype refusal is an acceptance failure, which is what we want
        return False
    for check in column.checks or []:
        result = check(coerced)
        passed = getattr(result, "check_passed", result)
        if hasattr(passed, "all"):
            passed = passed.all()
        if not bool(passed) and not check.raise_warning:
            return False
    return True


def _required_text_columns() -> list[tuple[str, str, pa.Column]]:
    """Required string columns that assert they carry a value.

    Not every non-nullable string column does. Some are required to be *present* while legitimately
    permitted to be empty — a refusal reason when nothing was refused, a reviewer when nothing has
    been reviewed, a note when there is no note. Those are listed below rather than left implicit,
    so that the decision is visible and a new one has to be argued for rather than absorbed.
    """
    return [
        (schema.name or attribute, name, column)
        for _, attribute, schema in _schemas()
        for name, column in schema.columns.items()
        if not column.nullable
        and "str" in str(column.dtype).lower()
        and {getattr(check, "name", None) for check in column.checks or []}
        >= {"non_blank_text", "meaningful_text"}
    ]


#: Non-nullable string columns whose contract is to preserve a source's literal value. They refuse
#: an empty cell and judge nothing else. `population_aliases.label` is here because HGDP loading
#: deliberately keeps whatever the source called a population — including one named "NA", which
#: tests/test_hgdp_source.py asserts — and a column that records what a source said must not also
#: rule on whether it looks like a value.
VERBATIM = {"population_aliases.label"}


def _verbatim_columns() -> list[tuple[str, pa.Column]]:
    found = [
        (f"{schema.name or attribute}.{name}", column)
        for _, attribute, schema in _schemas()
        for name, column in schema.columns.items()
        if f"{schema.name or attribute}.{name}" in VERBATIM
    ]
    assert len(found) == len(VERBATIM), "a name in VERBATIM no longer matches a real column"
    return found

#: Non-nullable string columns that may legitimately hold an empty string, because absence is a
#: real state for them. Each is a deliberate exemption from REVIEWABLE_TEXT, not an oversight.
MAY_BE_EMPTY = {
    "cpic_coverage.refusal_reason",
    "cpic_pair_targets.guideline_id",
    "cpic_pair_targets.guideline_name",
    "curated_variants.canonical_identifier",
    "curated_variants.founder_context",
    "curated_variants.reviewed_by",
    "curated_variants.reviewed_at",
    "curated_variants.refusal_reason",
    "variant_normalization.strand_evidence",
    "variant_normalization.reference_resource",
    "variant_normalization.naming_citation",
    "variant_normalization.refusal_reason",
    "variant_normalization.notes",
}


def test_every_required_text_column_either_requires_content_or_is_a_listed_exemption():
    """No column gets to be silently unchecked.

    A non-nullable string column with no check at all accepts a lone space and the word for missing.
    That is fine for a field where absence is a real state, and not fine for an identity. This forces
    the distinction to be made in the open: adopt REVIEWABLE_TEXT, or appear in MAY_BE_EMPTY.
    """
    unguarded = sorted(
        f"{schema.name or attribute}.{name}"
        for _, attribute, schema in _schemas()
        for name, column in schema.columns.items()
        if not column.nullable
        and "str" in str(column.dtype).lower()
        and not column.checks
        and f"{schema.name or attribute}.{name}" not in MAY_BE_EMPTY | VERBATIM
    )
    assert unguarded == [], (
        f"these required text columns assert nothing about their contents: {unguarded}. Either give "
        "them REVIEWABLE_TEXT from genomeos.schema_checks, or add them to MAY_BE_EMPTY with a reason "
        "if absence is genuinely a valid state for them."
    )


def test_the_sweep_finds_required_text_columns_to_guard():
    """Same reason as the walk assertion above: an empty sweep would pass forever."""
    assert len(_required_text_columns()) >= 25


@pytest.mark.parametrize("value", BLANKS)
def test_no_required_text_column_accepts_blank_text(value: str):
    """A required field must not accept whitespace pretending to be content.

    A genuine null is already refused by `nullable=False`; this covers strings whose only characters
    are whitespace. Unlike a printed placeholder, blank text carries no source evidence to preserve.
    """
    offenders = sorted(
        f"{schema}.{name}" for schema, name, column in _required_text_columns() if _accepts(column, value)
    )
    assert offenders == [], (
        f"{len(offenders)} required text column(s) accept {value!r}: {offenders[:8]}. Use "
        "REVIEWABLE_TEXT from genomeos.schema_checks rather than a bare str_length(min_value=1), "
        "which accepts a space."
    )


@pytest.mark.parametrize("value", sorted(FAKE_MISSING))
def test_required_text_preserves_a_suspect_literal_and_marks_it_for_review(value: str):
    """A printed placeholder survives, while every guarded column classifies it as suspicious."""
    offenders = []
    for schema, name, column in _required_text_columns():
        suspect = next(
            check for check in column.checks if getattr(check, "name", None) == "meaningful_text"
        )
        if suspect.raise_warning is not True or not _accepts(column, value):
            offenders.append(f"{schema}.{name}")
    assert offenders == [], (
        f"{len(offenders)} required text column(s) reject {value!r} or fail to mark it as a warning: "
        f"{offenders[:8]}. Suspect source text must survive for human review."
    )


@pytest.mark.parametrize("value", sorted(FAKE_MISSING))
def test_reviewable_text_warns_end_to_end_without_changing_the_value(value: str):
    """Exercise the behavior a caller sees, rather than only inspecting check metadata."""
    import warnings

    schema = pa.DataFrameSchema({"value": pa.Column(str, REVIEWABLE_TEXT, nullable=False)})
    frame = pd.DataFrame({"value": [value]})
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        validated = schema.validate(frame)
    assert validated["value"].tolist() == [value]
    assert any("human review" in str(item.message) for item in raised), (
        f"{value!r} survived but did not warn the reviewer"
    )


def test_reviewable_text_does_not_warn_on_ordinary_source_text():
    """Review warnings stay useful only when ordinary values pass quietly."""
    import warnings

    schema = pa.DataFrameSchema({"value": pa.Column(str, REVIEWABLE_TEXT, nullable=False)})
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        validated = schema.validate(pd.DataFrame({"value": ["Yoruba"]}))
    assert validated["value"].tolist() == ["Yoruba"]
    assert raised == [], f"ordinary source text produced warnings: {[str(r.message) for r in raised]}"


def test_no_schema_still_uses_a_bare_minimum_length_check():
    """The check this replaced is the one that looks sufficient and is not.

    `str_length(min_value=1)` reads like "must not be empty" and accepts a space. Leaving one behind
    would be a column that looks guarded and is not, which is worse than an obviously bare one.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "genomeos"
    # schema_checks.py documents the check it replaces, so it necessarily contains the shape it
    # forbids — the same self-exemption scripts/check_private_files.py needs for the same reason.
    survivors = [
        str(path.relative_to(root.parent))
        for path in sorted(root.rglob("*.py"))
        if path.name != "schema_checks.py"
        and "str_length(min_value=1)" in path.read_text(encoding="utf-8")
    ]
    assert survivors == [], (
        f"{survivors} still use str_length(min_value=1). Use REVIEWABLE_TEXT from "
        "genomeos.schema_checks, which refuses whitespace and warns on a word for missing."
    )


def test_a_real_value_that_merely_contains_a_null_word_is_still_accepted():
    """The check must match the whole value, never a substring, or it rejects real data.

    NAT2 is a gene. Nancy is a place and a person. Both start with a spelling of absence and both
    have to survive, which is why the set is compared against the whole stripped cell.
    """
    survivors = ["NAT2", "Nancy", "none-of-the-above", "not_reported", "0", "NA12878"]
    guarded = _required_text_columns()
    assert guarded, "nothing carries REVIEWABLE_TEXT, so this proves nothing"
    schema, name, column = guarded[0]
    check = next(c for c in column.checks if getattr(c, "name", None) == "meaningful_text")
    for value in survivors:
        result = check(column.dtype.try_coerce(pd.Series([value], dtype=object)))
        passed = getattr(result, "check_passed", result)
        if hasattr(passed, "all"):
            passed = passed.all()
        assert bool(passed), f"{schema}.{name} rejected the real value {value!r}"


def test_a_verbatim_column_still_refuses_an_empty_value():
    """Exempt from judging its contents is not exempt from having contents.

    A verbatim column keeps whatever a source said. It must still reject an empty cell, or the
    exemption becomes a hole rather than a category.
    """
    for label, column in _verbatim_columns():
        assert not _accepts(column, ""), f"{label} accepts an empty value"


def test_a_verbatim_column_keeps_a_suspect_value_and_warns_about_it():
    """The middle answer, and the whole point of the category.

    Refusing "NA" would reject something a source legitimately published. Accepting it in silence
    would let a missing label enter the registry looking like a recorded one. So the row is kept and
    a warning names the value, putting a submitter or reviewer in the loop rather than a machine.
    """
    import warnings

    for label, column in _verbatim_columns():
        suspect = next(
            check for check in column.checks if getattr(check, "name", None) == "meaningful_text"
        )
        assert suspect.raise_warning is True, (
            f"{label}'s suspect-value check must warn, not refuse — refusing would reject data a "
            "source legitimately published"
        )
        with warnings.catch_warnings(record=True) as raised:
            warnings.simplefilter("always")
            result = suspect(pd.Series(["NA"], dtype=object))
            passed = getattr(result, "check_passed", result)
            if hasattr(passed, "all"):
                passed = passed.all()
        assert not bool(passed), f"{label} should flag 'NA' as suspect"

    # and the end-to-end behaviour a submitter actually meets
    from genomeos.registry.schema import ALIASES_SCHEMA

    frame = pd.DataFrame([{"population_id": "hgdp-na", "source": "hgdp", "label": "NA"}])
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        validated = ALIASES_SCHEMA.validate(frame)
    assert validated["label"].tolist() == ["NA"], "the source's literal value must survive"
    assert any("spelling of absence" in str(item.message) for item in raised), (
        "a suspect verbatim value must produce a warning naming what to look at"
    )


def test_a_verbatim_column_does_not_warn_about_a_real_name():
    """A warning that fires on ordinary data is a warning everyone learns to ignore."""
    import warnings

    from genomeos.registry.schema import ALIASES_SCHEMA

    frame = pd.DataFrame([{"population_id": "hgdp-yoruba", "source": "hgdp", "label": "Yoruba"}])
    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        ALIASES_SCHEMA.validate(frame)
    assert raised == [], f"unexpected warning on an ordinary label: {[str(r.message) for r in raised]}"
