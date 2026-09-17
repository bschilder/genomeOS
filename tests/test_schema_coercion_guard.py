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
