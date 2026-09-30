"""I1 spec §9.1's two message-level digests:

    message_document_digest - the complete normalized message document, retained as provenance
    message_contract_digest - the same document after excluding presentation/identity metadata,
                               used for semantic comparison and conflict detection

Exact §9.1 exclusion list: "name, title, description, summary, example, examples, externalDocs,
x-version, x-aip-* identity/mapping extensions, component key and source pointer (never part of
the message object itself)." Everything else - "payload, headers, contentType, correlationId,
traits, bindings, and all other non-documentation, non-identity fields and extensions" - is
retained. "Two explicitly shared Messages with different local labels but equal contract digests
merge; different contract digests under the same explicit shared ID conflict."
"""

from typing import Any

from app.common.jcs import JSONValue, canonical_sha256_hex

CONTRACT_EXCLUDED_KEYS = frozenset(
    {"name", "title", "description", "summary", "example", "examples", "externalDocs", "x-version"}
)

_AIP_EXTENSION_PREFIX = "x-aip-"


def message_contract_projection(
    message_document: dict[str, Any], *, normalized_payload: JSONValue | None
) -> dict[str, Any]:
    """§9.1's contract projection: strips presentation/identity metadata and every `x-aip-*`
    extension, and replaces the raw `payload` value (which may still be an unresolved `$ref`) with
    its already-resolved, already-normalized shape - so two sources whose payload `$ref` differs
    syntactically but resolves to identical content correctly compare as equal contracts. Component
    key and source pointer are never part of `message_document` itself, so nothing here needs to
    strip them explicitly.
    """
    projection = {
        key: value
        for key, value in message_document.items()
        if key != "payload"
        and key not in CONTRACT_EXCLUDED_KEYS
        and not key.startswith(_AIP_EXTENSION_PREFIX)
    }
    if normalized_payload is not None:
        projection["payload"] = normalized_payload
    return projection


def message_contract_digest(
    message_document: dict[str, Any], *, normalized_payload: JSONValue | None
) -> str:
    return canonical_sha256_hex(
        message_contract_projection(message_document, normalized_payload=normalized_payload)
    )


def message_document_digest(message_document: dict[str, Any]) -> str:
    """§9.1: "The complete normalized message document is retained as `message_document_digest`
    provenance" - the full document, no exclusions, distinct from `message_contract_digest`.
    """
    return canonical_sha256_hex(message_document)
