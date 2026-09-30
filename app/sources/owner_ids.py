from collections.abc import Sequence

from app.common.encoding import length_delimited, length_delimited_group, sha256_hex, utf8


def _encode_source_pointer(document_path: str, pointer_tokens: Sequence[str]) -> bytes:
    """I1 spec §8.1/§9.1: "The normalized definition source pointer is the normalized relative
    document path plus decoded RFC 6901 pointer." Encoded as the document path and the pointer's
    decoded tokens (as their own nested group) - two separate fields rather than one joined string,
    to avoid delimiter-collision risk between a path segment and a pointer token (e.g. either could
    contain '/' or '#').
    """
    return length_delimited(
        utf8(document_path),
        length_delimited_group([utf8(token) for token in pointer_tokens]),
    )


class InvalidXVersionError(ValueError):
    """I1 spec §9.1: "another type is REJECTED_INVALID" for a non-string, non-absent `x-version`."""


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()
"""Sentinel for "the `x-version` key is not present at all", distinct from an explicit `null`/`None`
value. A caller reading a parsed YAML/JSON document must pass this instead of relying on `dict.get`'s
default `None`, since `document.get("x-version")` returns `None` for both an absent key and a key
explicitly set to `null` - those two cases are not the same under I1 §9.1 (missing participates as
the empty placeholder; an explicit `null` is a non-string value and is `REJECTED_INVALID`). Callers
should use `document.get("x-version", MISSING)`.
"""


def normalize_x_version(value: object) -> str:
    """I1 spec §9.1: "x-version participates in the owner key only when it is a non-empty string;
    another type is REJECTED_INVALID." A missing key (the `MISSING` sentinel) and an empty string
    both normalize to the empty placeholder; a genuinely non-empty string participates distinctly.
    An explicit `None` (i.e. `x-version: null` in the source document) is a non-string *value*, not
    an absent key, and is therefore rejected exactly like any other non-string type.
    """
    if value is MISSING:
        return ""
    if isinstance(value, str):
        return value
    raise InvalidXVersionError(f"x-version must be a string or absent, got {type(value).__name__}")


def schema_owned_id(
    *,
    canonical_service_id: str,
    source_instance_id: str,
    normalized_definition_document_path: str,
    definition_pointer_tokens: Sequence[str],
) -> str:
    """I1 spec §8.1:

    schema_owner_key
      = length-delimited(canonical Service id, SourceInstanceId, normalized definition source pointer)

    default schema id = schema:owned:<sha256(schema_owner_key)>
    """
    schema_owner_key = length_delimited(
        utf8(canonical_service_id),
        utf8(source_instance_id),
        _encode_source_pointer(normalized_definition_document_path, definition_pointer_tokens),
    )
    return f"schema:owned:{sha256_hex(schema_owner_key)}"


def message_owned_id(
    *,
    canonical_service_id: str,
    source_instance_id: str,
    normalized_definition_document_path: str,
    definition_pointer_tokens: Sequence[str],
    normalized_x_version_or_empty: str = "",
) -> str:
    """I1 spec §9.1:

    message_owner_key
      = length-delimited(canonical Service id, SourceInstanceId,
          normalized resolved message-definition source pointer, normalized x-version-or-empty)

    default message id = message:owned:<sha256(message_owner_key)>
    """
    message_owner_key = length_delimited(
        utf8(canonical_service_id),
        utf8(source_instance_id),
        _encode_source_pointer(normalized_definition_document_path, definition_pointer_tokens),
        utf8(normalized_x_version_or_empty),
    )
    return f"message:owned:{sha256_hex(message_owner_key)}"


def inline_payload_schema_id(
    *,
    message_id: str,
    normalized_inline_payload_document_path: str,
    inline_payload_pointer_tokens: Sequence[str],
) -> str:
    """I1 spec §9.1:

    inline payload schema id
      = schema:owned:<sha256(length-delimited(message id, normalized inline payload source pointer))>
    """
    key = length_delimited(
        utf8(message_id),
        _encode_source_pointer(
            normalized_inline_payload_document_path, inline_payload_pointer_tokens
        ),
    )
    return f"schema:owned:{sha256_hex(key)}"


def queue_owned_id(
    *,
    stable_broker_id: str,
    normalized_namespace_or_empty: str,
    exact_channel_address: str,
) -> str:
    """I1 spec §9:

        derived queue id
          = queue:owned:<sha256(length-delimited(
              stable broker id, normalized namespace-or-empty, exact channel address))>

    The caller is responsible for applying Unicode NFC normalization to the raw channel key before
    calling this (`app.common.encoding.unicode_nfc`) - channel-address normalization is kept out of
    this function so it stays a pure hash-formula function.
    """
    key = length_delimited(
        utf8(stable_broker_id),
        utf8(normalized_namespace_or_empty),
        utf8(exact_channel_address),
    )
    return f"queue:owned:{sha256_hex(key)}"


def topic_owned_id(
    *,
    stable_broker_id: str,
    normalized_namespace_or_empty: str,
    exact_topic_address: str,
) -> str:
    """v0.5.0 I4 spec §7.1:

        topic_owner_key = length-delimited(
            stable broker id, normalized namespace-or-empty, exact normalized topic/channel address)
        topic_id = topic:owned:<sha256(topic_owner_key)>

    Same inputs as `queue_owned_id`, but a distinct prefix - Queue and Topic ids never alias merely
    because their inputs match. As with `queue_owned_id`, the caller applies Unicode NFC first.
    """
    key = length_delimited(
        utf8(stable_broker_id),
        utf8(normalized_namespace_or_empty),
        utf8(exact_topic_address),
    )
    return f"topic:owned:{sha256_hex(key)}"


def subscription_owned_id(
    *,
    stable_broker_id: str,
    normalized_namespace_or_empty: str,
    topic_id: str,
    exact_subscription_name: str,
) -> str:
    """v0.5.0 I4 spec §7.2:

        subscription_owner_key = length-delimited(
            stable broker id, normalized namespace-or-empty, canonical Topic id,
            exact normalized subscription name)
        subscription_id = subscription:owned:<sha256(subscription_owner_key)>

    Binding the canonical Topic id keeps identical Subscription names on different Topics distinct.
    There is deliberately no consumer-group input (spec §7.2). The caller applies Unicode NFC first.
    """
    key = length_delimited(
        utf8(stable_broker_id),
        utf8(normalized_namespace_or_empty),
        utf8(topic_id),
        utf8(exact_subscription_name),
    )
    return f"subscription:owned:{sha256_hex(key)}"
