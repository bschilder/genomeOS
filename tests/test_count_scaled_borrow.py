"""Supplemental converter borrow-branch check (design §7, §8)."""

from __future__ import annotations

from decimal import Decimal, localcontext
from fractions import Fraction

import numpy as np

from genomeos.validation import count_scaled as cs


def test_integral_high_negative_low_uses_subnormal_borrow_branch(record_property):
    value = cs.ScaledPair(
        np.asarray(float.fromhex("0x1.0000000000000p-1")),
        np.asarray(float.fromhex("-0x1.0000000000000p-60")),
        np.asarray(-1021, dtype=np.int64),
    )
    exact = (Fraction.from_float(float(value.hi)) + Fraction.from_float(float(value.lo))) * (
        Fraction(2) ** int(value.exponent)
    )
    subnormal_unit = Fraction(2) ** -1074
    exact_units = exact / subnormal_unit
    expected_units = round(exact_units)
    assert exact_units == 2**52 - Fraction(1, 128)
    assert expected_units == 2**52
    with localcontext() as context:
        context.prec = 480
        context.Emin, context.Emax = -999999999, 999999999
        exact_decimal = Decimal(exact.numerator) / Decimal(exact.denominator)
    actual = cs.to_float64(value, array_module=np)
    record_property(
        "converter_borrow",
        {
            "input": [float(value.hi).hex(), float(value.lo).hex(), int(value.exponent)],
            "exact_numerator": exact.numerator,
            "exact_denominator": exact.denominator,
            "exact_decimal480": str(exact_decimal),
            "exact_subnormal_units": str(exact_units),
            "rounded_subnormal_units": expected_units,
            "actual_hex": float(actual).hex(),
            "expected_hex": "0x1.0000000000000p-1022",
        },
    )
    assert float(actual).hex() == "0x1.0000000000000p-1022"
