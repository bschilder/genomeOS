"""JSON text and strings read as ECMAScript reads them (fast-load spec §B.3, "same error class").

The Python and TypeScript GOSA decoders must refuse a container with the same code, so Python reads
a header the way ``JSON.parse`` does and trims text the way ``String.prototype.trim`` (zod
``z.string().trim()``) does. CPython differs in four ways, each closed here: its C JSON parser
recurses and fails near 10,000 levels (V8's has no depth limit); ``int`` refuses literals over 4,300
digits (``JSON.parse`` reads ``Infinity``); integers stay exact past 2**53 (JavaScript rounds them to
doubles); and ``str.strip`` strips a different whitespace set (U+001C-U+001F and U+0085, but not
U+FEFF).

Pure standard library, no I/O.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: What ``String.prototype.trim`` strips: the ECMAScript WhiteSpace and LineTerminator code points.
WHITESPACE = (
    "\t\n\v\f\r \xa0\u1680" + "".join(map(chr, range(0x2000, 0x200B)))
    + "\u2028\u2029\u202f\u205f\u3000\ufeff"
)

#: JSON whitespace, then the first token of a value (RFC 8259: ASCII digits, no NaN or Infinity).
_VALUE = re.compile(
    r'[ \t\n\r]*(?:(?P<open>[\[{])|(?P<string>")|(?P<word>true|false|null)'
    r"|(?P<number>-?(?:0|[1-9][0-9]*)(?P<real>(?:\.[0-9]+)?(?:[eE][-+]?[0-9]+)?)))"
)
_NEXT = re.compile(r"[ \t\n\r]*(.?)", re.DOTALL)  # JSON whitespace, then one character or none
_WORDS = {"true": True, "false": False, "null": None}
_STRINGS = json.JSONDecoder()  # ``raw_decode`` at a quote reads one string exactly as json.loads does


def trim(text: str) -> str:
    """``text.trim()`` in JavaScript."""
    return text.strip(WHITESPACE)


def json_parse(text: str) -> Any:
    """``JSON.parse(text)``; raise ``ValueError`` where it throws.

    Integers read as JavaScript numbers and ``NaN``/``Infinity`` are not JSON. A document nested past
    CPython's C parser limit is read again by an iterative parser with the same grammar.
    """
    try:
        return json.loads(text, parse_constant=_reject_constant, parse_int=_int_literal)
    except RecursionError:
        return _parse_iteratively(text)


def _reject_constant(token: str) -> None:
    raise ValueError(f"{token} is not JSON")


def _int_literal(token: str) -> int | float:
    """A JSON integer as JavaScript reads it: exact below 2**53, else the nearest double."""
    value = float(token)  # correctly rounded, with no digit limit
    return int(token) if abs(value) < 2**53 else value


def _next(text: str, at: int) -> tuple[str, int]:
    """The next non-whitespace character (``""`` at the end of ``text``) and the index after it."""
    match = _NEXT.match(text, at)
    return (match.group(1), match.end()) if match else ("", at)


def _key(text: str, at: int, frame: list[Any]) -> int:
    """Read ``"key":`` into ``frame``'s pending key; return the index after the colon."""
    quote, at = _next(text, at)
    if quote != '"':
        raise ValueError(f"expected an object key before {at}")
    frame[2], at = _STRINGS.raw_decode(text, at - 1)
    colon, at = _next(text, at)
    if colon != ":":
        raise ValueError(f"expected ':' before {at}")
    return at


def _parse_iteratively(text: str) -> Any:
    """``json_parse`` with an explicit stack in place of recursion."""
    frames: list[list[Any]] = []  # [container, closing bracket, pending key]
    at = 0
    while True:
        token = _VALUE.match(text, at)
        if token is None:
            raise ValueError(f"expected a JSON value at {at}")
        at = token.end()
        if token.group("open"):
            square = token.group("open") == "["
            frame: list[Any] = [[] if square else {}, "]" if square else "}", None]
            frames.append(frame)
            char, after = _next(text, at)
            if char != frame[1]:
                at = at if square else _key(text, at, frame)
                continue
            at, value = after, frames.pop()[0]
        elif token.group("string"):
            value, at = _STRINGS.raw_decode(text, at - 1)
        elif token.group("word"):
            value = _WORDS[token.group("word")]
        else:
            number = token.group("number")
            value = float(number) if token.group("real") else _int_literal(number)
        while frames:
            frame = frames[-1]
            if frame[1] == "]":
                frame[0].append(value)
            else:
                frame[0][frame[2]] = value
            char, at = _next(text, at)
            if char == ",":
                at = at if frame[1] == "]" else _key(text, at, frame)
                break
            if char != frame[1]:
                raise ValueError(f"expected ',' or {frame[1]!r} before {at}")
            value = frames.pop()[0]
        else:
            if _next(text, at)[0]:
                raise ValueError(f"extra data before {at}")
            return value
