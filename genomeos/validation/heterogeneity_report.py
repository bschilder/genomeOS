"""Pure canonical B0H report decoding (report design §§1–2,4; Atlas §§5,7–8,12)."""
from __future__ import annotations

import json
import struct

from genomeos.validation.heterogeneity_reduction import reduction_bytes
from genomeos.validation.heterogeneity_reduction_records import StudyReduction
from genomeos.validation.heterogeneity_simulation_types import SbcCaseId
from genomeos.validation.sbc_ranks import RankTestResult

_RANK_TEST_FIELDS = {
    "counts",
    "statistic",
    "p_value_bits",
    "bonferroni_p_value_bits",
}


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate reduction JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError("nonfinite reduction JSON token")


def _binary64(bits: object) -> float:
    if (
        type(bits) is not str
        or len(bits) != 16
        or any(character not in "0123456789abcdef" for character in bits)
    ):
        raise ValueError("rank p-value bits must be exactly 16 lowercase hexadecimal characters")
    return struct.unpack(">d", bytes.fromhex(bits))[0]


def _decode_rank_tests(document: dict[str, object]) -> None:
    ranks = document.get("ranks")
    if type(ranks) is not list:
        return
    for rank in ranks:
        if type(rank) is not dict or rank.get("test") is None:
            continue
        test = rank["test"]
        if type(test) is not dict or set(test) != _RANK_TEST_FIELDS:
            raise ValueError("rank test fields differ from canonical version1")
        counts = test["counts"]
        if type(counts) is not list:
            raise ValueError("rank test counts must be a JSON array")
        rank["test"] = RankTestResult(
            counts=tuple(counts),
            statistic=test["statistic"],
            p_value=_binary64(test["p_value_bits"]),
            bonferroni_p_value=_binary64(test["bonferroni_p_value_bits"]),
        )


def _tuplify(value: object) -> object:
    if type(value) is list:
        return tuple(_tuplify(item) for item in value)
    if type(value) is dict:
        converted = {key: _tuplify(item) for key, item in value.items()}
        if set(converted) == {"track_id", "study_id", "case_id", "replicate_id"}:
            return SbcCaseId(**converted)
        return converted
    return value


def read_study_reduction(data: bytes) -> StudyReduction:
    """Decode only exact version1 canonical bytes emitted by ``reduction_bytes``."""
    if type(data) is not bytes:
        raise ValueError("study reduction input must be exact bytes")
    try:
        document = json.loads(
            data.decode("ascii"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("invalid reduction JSON") from error
    if type(document) is not dict:
        raise ValueError("study reduction root must be a JSON object")
    _decode_rank_tests(document)
    value = StudyReduction.model_validate(_tuplify(document), strict=True)
    if reduction_bytes(value) != data:
        raise ValueError("study reduction bytes are not canonical")
    return value
