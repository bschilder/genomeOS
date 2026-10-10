"""ECMAScript ``JSON.parse`` and ``String.prototype.trim`` in Python (fast-load spec §B.3)."""

from __future__ import annotations

import pytest

from genomeos.publication import ecmascript

#: Node 23.9 (V8): every non-surrogate code point c with ``String.fromCodePoint(c).trim() === ''``.
NODE_TRIMMED = [0x9, 0xA, 0xB, 0xC, 0xD, 0x20, 0xA0, 0x1680, *range(0x2000, 0x200B), 0x2028, 0x2029]
NODE_TRIMMED += [0x202F, 0x205F, 0x3000, 0xFEFF]


def test_trim_strips_what_javascript_strips_and_not_what_str_strip_strips() -> None:
    assert sorted(map(ord, ecmascript.WHITESPACE)) == NODE_TRIMMED
    assert ecmascript.trim("\ufeff\u3000\x1c\x85 a \u2028") == "\x1c\x85 a"
    assert "\x1c\x85 a".strip() == "a"  # str.strip() also strips U+001C and U+0085


def test_integers_are_read_as_javascript_numbers() -> None:
    assert repr(ecmascript.json_parse("[9007199254740991,9007199254740993,-0,3]")) == (
        "[9007199254740991, 9007199254740992.0, 0, 3]"
    )
    assert ecmascript.json_parse("1" + "0" * 5000) == float("inf")  # int() refuses 4,301+ digits
    for constant in ("NaN", "Infinity", "-Infinity"):
        with pytest.raises(ValueError):
            ecmascript.json_parse(f"[{constant}]")


def test_nesting_depth_is_unlimited_as_in_v8() -> None:
    value = ecmascript.json_parse("[" * 100_000 + "]" * 100_000)  # json.loads: RecursionError
    for _ in range(100_000 - 1):
        value = value[0]
    assert value == []
    with pytest.raises(ValueError):
        ecmascript.json_parse("[" * 100_000 + "]" * 99_999)


@pytest.mark.parametrize(
    "text",
    [
        ' { "a" : [ 1 , -0.5e+3 , 2E2 , {} , [ ] , "\\u00e9\\n\\ud800" , true , false , null ] } ',
        '{"a":1,"a":2,"b":{"c":[[0]]}}',
        "9007199254740993",
        '"x"',
        *("[1,]", "{,}", "[01]", "[1 2]", '{"a":1,}', '{"a"}', "[.5]", "[-]", "[1.]", "[NaN]", "[tru]"),
        *('["\x01"]', "[1]x", "[", "]", "", " ", "[}", "{]", '{"a":}', "[1}", "1e", '{"a" 1}', '"\\x"'),
    ],
)
def test_the_iterative_parser_reads_json_exactly_as_json_loads(text: str) -> None:
    try:
        expected = repr(ecmascript.json_parse(text))  # shallow, so this is the json.loads path
    except ValueError:
        with pytest.raises(ValueError):
            ecmascript._parse_iteratively(text)
    else:
        assert repr(ecmascript._parse_iteratively(text)) == expected  # repr tells 1 from 1.0
