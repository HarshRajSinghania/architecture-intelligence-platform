import hashlib
import unicodedata
from collections.abc import Sequence

_LENGTH_PREFIX_BYTES = 8
_LENGTH_PREFIX_BYTEORDER = "big"


def length_delimited(*parts: bytes) -> bytes:
    """The one canonical, unambiguous concatenation used by every identity hash in this package
    (I1 spec §5.1: "The concatenation used for every identity hash SHALL be length-delimited or
    otherwise unambiguously encoded"). Each part is prefixed with its exact byte length as an
    unsigned 8-byte big-endian integer, so no part boundary can be confused with adjacent content.

    This is also the literal per-entry encoding §5.3 specifies for dependency-closure entries: "UTF-8
    byte length of normalized POSIX path" + "UTF-8 bytes of ... path" + "exact file byte length" +
    "exact file bytes" is exactly length_delimited(path_bytes, file_bytes).
    """
    encoded = bytearray()
    for part in parts:
        encoded += len(part).to_bytes(_LENGTH_PREFIX_BYTES, _LENGTH_PREFIX_BYTEORDER)
        encoded += part
    return bytes(encoded)


def length_delimited_group(parts: Sequence[bytes]) -> bytes:
    """Nests a variable-length sequence of parts as one opaque, self-delimited blob: `length_delimited
    (*parts)`, the same encoding as `length_delimited` itself. The distinct name marks intent at the
    call site - the result is meant to be passed as a single part to an *outer* `length_delimited(...)`
    call, not concatenated loose. Used wherever several such groups sit side by side (e.g. several
    distinct field lists in one identity hash): a flat `length_delimited(*group_a, *group_b)` would
    lose the boundary between the groups, letting an item shift from one group to another produce an
    identical encoding for a differently-partitioned input. Nesting fixes this without any extra
    part-count field - each group becomes one length-prefixed part at the outer level, so the outer
    call's own length prefix bounds exactly where that group's bytes end, regardless of how many
    parts or how much internal structure it contains.
    """
    return length_delimited(*parts)


def utf8(text: str) -> bytes:
    """The UTF-8 bytes of `text` - the one text-to-bytes step every identity hash input goes through."""
    return text.encode("utf-8")


def sha256_hex(data: bytes) -> str:
    """Lowercase hexadecimal SHA-256, the fixed output encoding for every identity/digest formula."""
    return hashlib.sha256(data).hexdigest()


def unicode_nfc(text: str) -> str:
    """Unicode NFC normalization only - no trimming, no case folding. Used by the AsyncAPI Queue
    channel-address rule (I1 spec §9): "Channel address is the channel key normalized to Unicode NFC
    without trimming or case folding."
    """
    return unicodedata.normalize("NFC", text)
