"""Independent arithmetic and probability-lattice checks (design §7, §8).

Fixed E1 values are synthetic arithmetic inputs. Decimal480 evaluates represented
tuples; exact rational identities separately catch packing and promotion losses.
Every numerical assertion records its reference and actual expansion in JUnit.
"""

from __future__ import annotations

import json
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
from pathlib import Path

import numpy as np
import pytest

from genomeos.validation import count_scaled as cs

INPUTS = json.loads((Path(__file__).parent / "fixtures/count_scaled/e1_inputs.json").read_text())
P = [tuple(row) for row in INPUTS["positive_pairs"]]
ZERO = ("0x0.0p+0", "0x0.0p+0", 0)
S = [
    ZERO,
    *P,
    *[(float.fromhex(h).__neg__().hex(), float.fromhex(low).__neg__().hex(), e) for h, low, e in P],
]
OPS = {
    "add": lambda a, b: a + b,
    "subtract": lambda a, b: a - b,
    "multiply": lambda a, b: a * b,
    "divide": lambda a, b: a / b,
}


@pytest.fixture(autouse=True)
def strict_arithmetic():
    with localcontext() as context, np.errstate(all="raise"):
        context.prec = 480
        context.Emin, context.Emax = -999999999, 999999999
        yield


def pair(row):
    h, low, e = row
    return cs.ScaledPair(np.asarray(float.fromhex(h)), np.asarray(float.fromhex(low)), np.asarray(e))


def packed(number):
    return cs.from_int64(np.asarray(number, dtype=np.int64), array_module=np)


def tuple_of(value):
    return [float(value.hi).hex(), float(value.lo).hex(), int(value.exponent)]


def rational(value):
    return (Fraction.from_float(float(value.hi)) + Fraction.from_float(float(value.lo))) * (
        Fraction(2) ** int(value.exponent)
    )


def decimal(value):
    exact = rational(value)
    return Decimal(exact.numerator) / Decimal(exact.denominator)


def canonical(value):
    assert value.hi.dtype == value.lo.dtype == np.dtype("float64")
    assert value.exponent.dtype == np.dtype("int64")
    h, low, e = float(value.hi), float(value.lo), int(value.exponent)
    assert np.isfinite(h) and np.isfinite(low)
    if h == 0:
        assert low == e == 0 and not np.signbit(h) and not np.signbit(low)
    else:
        assert 0.5 <= abs(h) < 1
        assert low == 0 or abs(low) >= 2.0**-120
        assert abs(low) <= 2.0**-53 * abs(h)
        assert float(Fraction.from_float(h) + Fraction.from_float(low)) == h


def check(name, a, b, out, record_property, *, factor=None):
    aa, bb = decimal(a), decimal(b)
    expected = OPS[name](aa, bb)
    actual = decimal(out)
    scale = abs(aa) + abs(bb) if name in {"add", "subtract"} else abs(expected)
    bound = (Decimal(2) ** -98 if factor is None else factor) * scale
    record_property(
        "arithmetic",
        json.dumps(
            {
                "operation": name,
                "a": tuple_of(a),
                "b": tuple_of(b),
                "actual_pair": tuple_of(out),
                "reference_decimal480": str(expected),
                "actual_decimal480": str(actual),
                "absolute_error": str(abs(actual - expected)),
                "bound": str(bound),
            }
        ),
    )
    canonical(out)
    assert abs(actual - expected) <= bound
    if expected == 0:
        assert tuple_of(out) == list(ZERO)
    elif name in {"multiply", "divide"}:
        assert (actual > 0) == (expected > 0)
    return out


@pytest.mark.parametrize("name", ["add", "subtract", "multiply"])
@pytest.mark.parametrize("i,j", product(range(25), repeat=2))
def test_signed_cartesian(name, i, j, record_property):
    a, b = pair(S[i]), pair(S[j])
    out = getattr(cs, name)(a, b, array_module=np)
    check(name, a, b, out, record_property)
    if j == 0 and name in {"add", "subtract"}:
        assert rational(out) == rational(a)
    if i == 0 and name == "add":
        assert rational(out) == rational(b)


@pytest.mark.parametrize("i,j", product(range(25), range(12)))
def test_signed_division(i, j, record_property):
    a, b = pair(S[i]), pair(P[j])
    check("divide", a, b, cs.divide(a, b, array_module=np), record_property)


@pytest.mark.parametrize("text", INPUTS["packing_hex"])
def test_float_packing_exact(text, record_property):
    value = float.fromhex(text)
    out = cs.from_float64(np.asarray(value), array_module=np)
    canonical(out)
    record_property("packing", json.dumps({"input_hex": text, "output": tuple_of(out)}))
    assert rational(out) == Fraction.from_float(value)


@pytest.mark.parametrize("number", INPUTS["integer_inputs"])
def test_int64_packing_exact(number, record_property):
    out = packed(number)
    canonical(out)
    record_property("packing", json.dumps({"input_int64": number, "output": tuple_of(out)}))
    assert rational(out) == number


@pytest.mark.parametrize("sign,j", product([-1, 1], range(12)))
def test_residual_promotion_composes(sign, j, record_property):
    a, b = pair(P[1]), pair(P[0])
    if sign < 0:
        a, b = b, a
    residual = check("subtract", a, b, cs.subtract(a, b, array_module=np), record_property)
    assert tuple_of(residual) == [float(sign * 0.5).hex(), "0x0.0p+0", -54]
    negative = cs.ScaledPair(-residual.hi, np.zeros_like(residual.lo), residual.exponent)
    check("add", residual, negative, cs.add(residual, negative, array_module=np), record_property)
    for name in ("multiply", "divide"):
        other = pair(P[j])
        out = getattr(cs, name)(residual, other, array_module=np)
        check(name, residual, other, out, record_property)
        exact = OPS[name](Decimal(sign) * Decimal(2) ** -55, decimal(other))
        assert abs(decimal(out) - exact) <= abs(exact) * Decimal(2) ** -98


@pytest.mark.parametrize("i,j", product(range(12), repeat=2))
def test_exact_zero_composes(i, j, record_property):
    a, negative, other = pair(P[i]), pair(S[i + 13]), pair(P[j])
    zero = check("add", a, negative, cs.add(a, negative, array_module=np), record_property)
    for name in OPS:
        out = getattr(cs, name)(zero, other, array_module=np)
        check(name, zero, other, out, record_property)
        assert rational(out) == OPS[name](Fraction(0), rational(other))


@pytest.mark.parametrize("numerator,denominator", INPUTS["division_traces"])
def test_actual_division_trace(numerator, denominator, monkeypatch, record_property):
    traces = []
    original_estimate = cs._estimate

    def estimate(a, b, xp):
        out = original_estimate(a, b, xp)
        expected = decimal(a) / decimal(b)
        error = abs(decimal(out) - expected)
        bound = abs(expected) * Decimal(4) * Decimal(2) ** -53
        record_property(
            "estimate",
            json.dumps(
                {
                    "a": tuple_of(a),
                    "b": tuple_of(b),
                    "actual": tuple_of(out),
                    "reference_decimal480": str(expected),
                    "absolute_error": str(error),
                    "bound": str(bound),
                }
            ),
        )
        assert error <= bound
        traces.append(("estimate", out))
        return out

    monkeypatch.setattr(cs, "_estimate", estimate)
    for name in ("multiply", "subtract", "add"):
        original = getattr(cs, name)

        def observed(a, b, *, array_module, _name=name, _original=original):
            out = _original(a, b, array_module=array_module)
            check(_name, a, b, out, record_property)
            traces.append((_name, out))
            return out

        monkeypatch.setattr(cs, name, observed)
    a, b = packed(numerator), packed(denominator)
    check("divide", a, b, cs.divide(a, b, array_module=np), record_property)
    assert [name for name, _ in traces] == [
        "estimate",
        "multiply",
        "subtract",
        "estimate",
        "multiply",
        "subtract",
        "estimate",
        "add",
        "add",
    ]
    r0, r1 = traces[2][1], traces[5][1]
    if denominator == 2:
        assert all(rational(traces[i][1]) == 0 for i in (2, 3, 5, 6))
    else:
        assert (rational(r0) > 0) == (numerator == 1 and denominator == 3)
    record_property(
        "division_trace",
        json.dumps(
            {
                "q0": tuple_of(traces[0][1]),
                "r0": tuple_of(r0),
                "q1": tuple_of(traces[3][1]),
                "r1": tuple_of(r1),
                "q2": tuple_of(traces[6][1]),
            }
        ),
    )


@pytest.mark.parametrize("text", INPUTS["complement_hex"])
def test_complement_and_shape_composition(text, record_property):
    p = cs.from_float64(np.asarray(float.fromhex(text)), array_module=np)
    c = cs.from_float64(np.asarray(float.fromhex(INPUTS["shape_concentration_hex"])), array_module=np)
    one = packed(1)
    q = check("subtract", one, p, cs.subtract(one, p, array_module=np), record_property)
    exact_q = Decimal(1) - decimal(p)
    if float.fromhex(text) >= 0.5:
        assert rational(q) == Fraction(1) - rational(p)
    else:
        assert abs(decimal(q) - exact_q) <= Decimal(2) ** -118
    alpha = check("multiply", p, c, cs.multiply(p, c, array_module=np), record_property)
    assert rational(alpha) == rational(p) * rational(c)
    beta = check("multiply", q, c, cs.multiply(q, c, array_module=np), record_property)
    exact_beta = exact_q * decimal(c)
    assert abs(decimal(beta) - exact_beta) <= abs(exact_beta) * 9 * Decimal(2) ** -106
    for offset in INPUTS["shape_offsets"]:
        integer = packed(offset)
        aa = check("add", alpha, integer, cs.add(alpha, integer, array_module=np), record_property)
        bb = check("add", beta, integer, cs.add(beta, integer, array_module=np), record_property)
        left, right = [packed(n) for n in INPUTS["ratio_count_factors"]]
        top = check("multiply", aa, left, cs.multiply(aa, left, array_module=np), record_property)
        bottom = check("multiply", bb, right, cs.multiply(bb, right, array_module=np), record_property)
        for numerator, denominator, exact in (
            (top, bottom, (decimal(p) * decimal(c) + offset) * 65536 / (exact_beta + offset)),
            (bottom, top, (exact_beta + offset) / ((decimal(p) * decimal(c) + offset) * 65536)),
        ):
            out = check(
                "divide",
                numerator,
                denominator,
                cs.divide(numerator, denominator, array_module=np),
                record_property,
            )
            record_property(
                "shape_ratio",
                json.dumps(
                    {
                        "input_p": text,
                        "offset": offset,
                        "exact_original_expression_decimal480": str(exact),
                        "actual": tuple_of(out),
                        "relative_bound": str(69 * Decimal(2) ** -106),
                    }
                ),
            )
            assert abs(decimal(out) - exact) <= abs(exact) * 69 * Decimal(2) ** -106


@pytest.mark.parametrize("case", INPUTS["rounding"], ids=lambda case: case["id"])
def test_probability_lattice_rounding(case, record_property):
    value = pair(case["pair"])
    out = cs.to_float64(value, array_module=np)
    expected = float.fromhex(case["expected_hex"])
    record_property(
        "conversion",
        json.dumps(
            {
                "input": tuple_of(value),
                "actual_hex": float(out).hex(),
                "reference_hex": case["expected_hex"],
                "exact_decimal480": str(decimal(value)),
            }
        ),
    )
    assert out.dtype == np.dtype("float64")
    assert float(out).hex() == expected.hex()
    assert not np.signbit(out) and np.isfinite(out)


@pytest.mark.parametrize("low", INPUTS["threshold_lows"])
def test_low_cutoff_only_after_normalization(low, record_property):
    small = cs.from_float64(np.asarray(float.fromhex(low)), array_module=np)
    large = pair(P[0])
    out = check("add", large, small, cs.add(large, small, array_module=np), record_property)
    if float.fromhex(low) < 2.0**-120:
        assert float(out.lo) == 0
    else:
        assert float(out.lo).hex() == low


@pytest.mark.parametrize("name", list(OPS))
def test_mixed_eager_lanes_and_broadcast(name, record_property):
    rows = np.array([float.fromhex(h) for h, _, _ in S], dtype=np.float64)[:, None]
    lows = np.array([float.fromhex(low) for _, low, _ in S], dtype=np.float64)[:, None]
    exponents = np.array([e for _, _, e in S], dtype=np.int64)[:, None]
    aa = cs.ScaledPair(rows, lows, exponents)
    bb = cs.ScaledPair(
        np.array([float.fromhex(h) for h, _, _ in P])[None, :],
        np.array([float.fromhex(low) for _, low, _ in P])[None, :],
        np.array([e for _, _, e in P], dtype=np.int64)[None, :],
    )
    before = [x.copy() for x in (aa.hi, aa.lo, aa.exponent, bb.hi, bb.lo, bb.exponent)]
    out = getattr(cs, name)(aa, bb, array_module=np)
    assert out.hi.shape == out.lo.shape == out.exponent.shape == (25, 12)
    for i, j in product(range(25), range(12)):
        scalar = cs.ScaledPair(out.hi[i, j], out.lo[i, j], out.exponent[i, j])
        check(name, pair(S[i]), pair(P[j]), scalar, record_property)
    for original, saved in zip((aa.hi, aa.lo, aa.exponent, bb.hi, bb.lo, bb.exponent), before, strict=True):
        np.testing.assert_array_equal(original, saved)


@pytest.mark.parametrize("name", list(OPS))
def test_empty_arrays(name):
    value = cs.ScaledPair(np.empty(0), np.empty(0), np.empty(0, dtype=np.int64))
    out = getattr(cs, name)(value, value, array_module=np)
    assert out.hi.shape == out.lo.shape == out.exponent.shape == (0,)
    assert cs.to_float64(out, array_module=np).shape == (0,)


@pytest.mark.parametrize(
    "row",
    [
        (0.0, 2.0**-121, 0),
        (0.25, 0.0, 0),
        (1.0, 0.0, 0),
        (0.5, 2.0**-121, 0),
        (0.5, 3 * 2.0**-55, 0),
        (0.0, 0.0, 1),
        (-0.0, 0.0, 0),
        (0.0, -0.0, 0),
        (float("nan"), 0.0, 0),
        (float("inf"), 0.0, 0),
        (0.5, float("nan"), 0),
    ],
)
def test_noncanonical_pairs_fail_closed(row):
    bad = cs.ScaledPair(np.asarray(row[0]), np.asarray(row[1]), np.asarray(row[2]))
    for name in OPS:
        with pytest.raises(ValueError):
            getattr(cs, name)(bad, packed(1), array_module=np)
    with pytest.raises(ValueError):
        cs.to_float64(bad, array_module=np)


@pytest.mark.parametrize("name", list(OPS))
def test_noncanonical_second_operand_fails(name):
    bad = cs.ScaledPair(np.asarray(0.25), np.asarray(0.0), np.asarray(0))
    with pytest.raises(ValueError):
        getattr(cs, name)(packed(1), bad, array_module=np)


@pytest.mark.parametrize("value", [0, -1])
def test_divisor_domain(value):
    with pytest.raises(ValueError):
        cs.divide(packed(1), packed(value), array_module=np)


@pytest.mark.parametrize("row", [(-0.5, 0.0, -1076), (0.5, 2.0**-55, 1), (0.5, 0.0, 2)])
def test_conversion_domain_before_rounding(row):
    value = cs.ScaledPair(np.asarray(row[0]), np.asarray(row[1]), np.asarray(row[2]))
    with pytest.raises(ValueError):
        cs.to_float64(value, array_module=np)


@pytest.mark.parametrize(
    "kind",
    [
        "float32",
        "float_int",
        "float_bool",
        "int_float",
        "int_uint",
        "pair_low",
        "pair_exp",
        "pair_shape",
        "packing_nan",
        "packing_inf",
    ],
)
def test_dtype_shape_and_finite_contract(kind):
    with pytest.raises((TypeError, ValueError)):
        if kind == "float32":
            cs.from_float64(np.asarray(0.5, dtype=np.float32), array_module=np)
        elif kind == "float_int":
            cs.from_float64(np.asarray(1), array_module=np)
        elif kind == "float_bool":
            cs.from_float64(np.asarray(True), array_module=np)
        elif kind == "int_float":
            cs.from_int64(np.asarray(1.0), array_module=np)
        elif kind == "int_uint":
            cs.from_int64(np.asarray(2**63, dtype=np.uint64), array_module=np)
        elif kind.startswith("packing_"):
            cs.from_float64(np.asarray(float(kind.removeprefix("packing_"))), array_module=np)
        else:
            low = np.asarray(0.0, dtype=np.float32 if kind == "pair_low" else np.float64)
            exponent = np.asarray(1, dtype=np.int32 if kind == "pair_exp" else np.int64)
            high = np.asarray([0.5] if kind == "pair_shape" else 0.5)
            cs.add(cs.ScaledPair(high, low, exponent), packed(1), array_module=np)


@pytest.mark.parametrize(
    "name,ea,eb",
    [
        ("multiply", 2**63 - 1, 1),
        ("multiply", -(2**63), -1),
        ("divide", 2**63 - 1, -1),
        ("divide", -(2**63), 1),
        ("add", 2**63 - 1, 2**63 - 1),
    ],
)
def test_exponent_overflow_is_a_hard_error(name, ea, eb):
    a = cs.ScaledPair(np.asarray(0.75), np.asarray(0.0), np.asarray(ea))
    b = cs.ScaledPair(np.asarray(0.75), np.asarray(0.0), np.asarray(eb))
    with pytest.raises(OverflowError):
        getattr(cs, name)(a, b, array_module=np)


def test_extreme_exponent_alignment_and_zero_lanes():
    a = cs.ScaledPair(np.array([0.5, 0.5, 0.0]), np.zeros(3), np.array([2**63 - 1, -(2**63), 0]))
    b = cs.ScaledPair(np.array([0.5, 0.5, 0.5]), np.zeros(3), np.array([-(2**63), 2**63 - 1, -(2**63)]))
    out = cs.add(a, b, array_module=np)
    np.testing.assert_array_equal(out.hi, [0.5, 0.5, 0.5])
    np.testing.assert_array_equal(out.exponent, [2**63 - 1, 2**63 - 1, -(2**63)])
    zero = cs.ScaledPair(np.zeros(3), np.zeros(3), np.zeros(3, dtype=np.int64))
    for name in ("multiply", "divide"):
        out = getattr(cs, name)(zero, b, array_module=np)
        np.testing.assert_array_equal(out.exponent, [0, 0, 0])
        np.testing.assert_array_equal(out.hi, [0.0, 0.0, 0.0])


def test_converter_masks_extreme_inactive_lanes():
    value = cs.ScaledPair(np.array([0.5, 0.5, 0.0, 0.5]), np.zeros(4), np.array([-(2**63), -1073, 0, 1]))
    out = cs.to_float64(value, array_module=np)
    np.testing.assert_array_equal(out, [0.0, float.fromhex("0x0.0000000000001p-1022"), 0.0, 1.0])


@pytest.mark.parametrize(
    "text",
    [
        "0x0.0000000000001p-1022",
        "-0x0.0000000000001p-1022",
        "0x1.0000000000000p-1022",
        "-0x1.0000000000000p-1022",
    ],
)
@pytest.mark.parametrize("name", [*OPS, "to_float64"])
def test_noncanonical_tiny_high_refuses_without_underflow(text, name):
    bad = cs.ScaledPair(np.asarray(float.fromhex(text)), np.asarray(0.0), np.asarray(0))
    with pytest.raises(ValueError):
        if name == "to_float64":
            cs.to_float64(bad, array_module=np)
        else:
            getattr(cs, name)(bad, packed(1), array_module=np)
