"""Pure source validation for indexed evidence (Atlas design §§6, 10, 12).

A source pointer/checksum is traceability, not independent scientific verification.
No analysis is authorized from significant hits, map labels, or source URLs alone.
"""

from __future__ import annotations

import math
import re
from urllib.parse import urlsplit

PUBLIC_LOCATIONS = {
    ("https", "pan-ukb-us-east-1.s3.amazonaws.com"),
    ("s3", "pan-ukb-us-east-1"),
    ("gs", "ukb-diverse-pops-public"),
}


def provenance_issues(source: str, uri: str, checksum: str | None) -> list[str]:
    issues = []
    if source != "pan-ukb":
        issues.append("source_not_panukb")
    try:
        location = urlsplit(uri)
        allowed = (
            (location.scheme, location.netloc) in PUBLIC_LOCATIONS
            and not location.query
            and not location.fragment
            and location.path.startswith("/")
            and len(location.path) > 1
        )
    except ValueError:
        allowed = False
    if not allowed:
        issues.append("source_location_not_qualified")
    if checksum is None or re.fullmatch(r"[0-9a-f]{64}", checksum) is None:
        issues.append("source_sha256_unrecorded")
    return issues


def validate_p_value(encoded: float, encoding: str, canonical: float) -> None:
    """Refuse corrupt encoding; never repair stored scientific values on read."""
    if not math.isfinite(encoded) or not math.isfinite(canonical) or canonical < 0:
        raise ValueError("invalid p-value")
    if encoding == "raw" and 0 < encoded <= 1:
        expected = -math.log10(encoded)
    elif encoding == "ln" and encoded <= 0:
        expected = -encoded / math.log(10)
    elif encoding == "neg_log10" and encoded >= 0:
        expected = encoded
    else:
        raise ValueError("invalid p-value encoding or domain")
    if not math.isclose(expected, canonical, rel_tol=1e-10, abs_tol=1e-12):
        raise ValueError("encoded and canonical p-values disagree")
