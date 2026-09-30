"""Compatibility re-export: the implementation lives in `app.common.jcs` (a neutral module
`canonical`, `graph` and `telemetry` can depend on without depending on `app.sources`)."""

from app.common.jcs import (
    JSONValue,
    canonical_json_bytes,
    canonical_sha256_hex,
    sort_by_canonical_hash,
    sort_entries_by_canonical_bytes,
)

__all__ = [
    "JSONValue",
    "canonical_json_bytes",
    "canonical_sha256_hex",
    "sort_by_canonical_hash",
    "sort_entries_by_canonical_bytes",
]
