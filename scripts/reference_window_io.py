#!/usr/bin/env python3
"""Compatibility facade for bounded reference I/O (acquisition design §4.1)."""

from __future__ import annotations

from scripts.reference_io_common import validate_verified_source
from scripts.reference_native_io import (
    extract_native,
    iter_native_tokens,
    iter_native_totals,
    native_called_totals,
    query_native_keys,
    query_native_tokens,
    read_native_totals,
)
from scripts.reference_window_fetch import (
    fetch_metadata,
    fetch_range,
    stage_sparse,
    validate_metadata_receipt,
)
from scripts.reference_window_read import (
    iter_original_records,
    iter_source_records,
    load_source_header,
    read_source_header,
    validate_original_evidence,
    validate_original_records,
)

__all__ = [
    "extract_native",
    "fetch_metadata",
    "fetch_range",
    "iter_native_tokens",
    "iter_native_totals",
    "iter_original_records",
    "iter_source_records",
    "load_source_header",
    "native_called_totals",
    "query_native_keys",
    "query_native_tokens",
    "read_native_totals",
    "read_source_header",
    "stage_sparse",
    "validate_metadata_receipt",
    "validate_original_evidence",
    "validate_original_records",
    "validate_verified_source",
]
