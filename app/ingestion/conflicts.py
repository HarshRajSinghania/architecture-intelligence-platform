"""Upsert-or-conflict for Schema and Message entities collected while one adapter maps a source
(first-wins for identical content, a conflict result for disagreeing content)."""

from app.canonical.model import Message, Schema
from app.sources.model import DiagnosticCode, IngestionDiagnostic


def upsert_schema_or_conflict(
    schemas_by_id: dict[str, Schema], schema_id_value: str, candidate: Schema
) -> IngestionDiagnostic | None:
    """I1 spec §8.1: "Two current owners explicitly mapped to one shared Schema ID with different
    canonical hashes are REJECTED_CONFLICT." Two different pointers within one source's own single
    `map()` call can converge on the same id only via an explicit shared-identity mapping (owner-
    scoped default ids are collision-free by construction) - this is the within-source half of
    conflict detection; the cross-source half runs later, over every source's already-returned
    model, in `app.sources.claim_conflicts`. Returns `None` and performs the upsert when there is no
    existing entry, or the existing entry's content agrees (silent merge - identical content under
    a shared id is fine); returns a diagnostic instead of upserting when it disagrees, leaving the
    first-seen entry in place so the caller's own model stays a valid (if soon-to-be-rejected)
    snapshot.
    """
    existing = schemas_by_id.get(schema_id_value)
    if existing is None:
        schemas_by_id[schema_id_value] = candidate
        return None
    if existing.canonical_hash == candidate.canonical_hash:
        return None
    return IngestionDiagnostic(
        code=DiagnosticCode.SCHEMA_CONTENT_CONFLICT,
        message=(
            f"schema {schema_id_value!r} has disagreeing canonical hashes within one source: "
            f"{existing.canonical_hash!r} vs {candidate.canonical_hash!r}"
        ),
        source_pointer=schema_id_value,
    )


def upsert_message_or_conflict(
    messages_by_id: dict[str, Message], message_id_value: str, candidate: Message
) -> IngestionDiagnostic | None:
    """The message equivalent of `upsert_schema_or_conflict`, comparing `contract_digest` (I1 spec
    §9.1's semantic-comparison digest) rather than `canonical_hash`.
    """
    existing = messages_by_id.get(message_id_value)
    if existing is None:
        messages_by_id[message_id_value] = candidate
        return None
    if existing.contract_digest == candidate.contract_digest:
        return None
    return IngestionDiagnostic(
        code=DiagnosticCode.MESSAGE_CONTENT_CONFLICT,
        message=(
            f"message {message_id_value!r} has disagreeing contract digests within one source: "
            f"{existing.contract_digest!r} vs {candidate.contract_digest!r}"
        ),
        source_pointer=message_id_value,
    )
