"""Compatibility re-export: the implementation lives in `app.common.encoding` (a neutral module
`canonical`, `graph` and `telemetry` can depend on without depending on `app.sources`)."""

from app.common.encoding import (
    length_delimited,
    length_delimited_group,
    sha256_hex,
    unicode_nfc,
)

__all__ = ["length_delimited", "length_delimited_group", "sha256_hex", "unicode_nfc"]
