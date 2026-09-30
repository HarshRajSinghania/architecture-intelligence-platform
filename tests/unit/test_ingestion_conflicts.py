from app.canonical.model import Message, Schema
from app.ingestion.conflicts import upsert_message_or_conflict, upsert_schema_or_conflict
from app.sources.model import DiagnosticCode


def test_upsert_schema_inserts_a_new_entry():
    schemas_by_id: dict[str, Schema] = {}
    candidate = Schema(id="schema:X", name="X", canonical_hash="h1")
    diagnostic = upsert_schema_or_conflict(schemas_by_id, "schema:X", candidate)
    assert diagnostic is None
    assert schemas_by_id["schema:X"] is candidate


def test_upsert_schema_silently_merges_identical_content():
    schemas_by_id: dict[str, Schema] = {
        "schema:X": Schema(id="schema:X", name="X", canonical_hash="h1")
    }
    diagnostic = upsert_schema_or_conflict(
        schemas_by_id, "schema:X", Schema(id="schema:X", name="X", canonical_hash="h1")
    )
    assert diagnostic is None


def test_upsert_schema_flags_disagreeing_content():
    schemas_by_id: dict[str, Schema] = {
        "schema:X": Schema(id="schema:X", name="X", canonical_hash="h1")
    }
    diagnostic = upsert_schema_or_conflict(
        schemas_by_id, "schema:X", Schema(id="schema:X", name="X", canonical_hash="h2")
    )
    assert diagnostic is not None
    assert diagnostic.code is DiagnosticCode.SCHEMA_CONTENT_CONFLICT
    # the first-seen entry is left in place, not overwritten by the conflicting candidate
    assert schemas_by_id["schema:X"].canonical_hash == "h1"


def test_upsert_message_inserts_a_new_entry():
    messages_by_id: dict[str, Message] = {}
    candidate = Message(id="message:X", name="X", contract_digest="d1")
    diagnostic = upsert_message_or_conflict(messages_by_id, "message:X", candidate)
    assert diagnostic is None
    assert messages_by_id["message:X"] is candidate


def test_upsert_message_silently_merges_identical_content():
    messages_by_id: dict[str, Message] = {
        "message:X": Message(id="message:X", name="X", contract_digest="d1")
    }
    diagnostic = upsert_message_or_conflict(
        messages_by_id, "message:X", Message(id="message:X", name="X", contract_digest="d1")
    )
    assert diagnostic is None


def test_upsert_message_flags_disagreeing_content():
    messages_by_id: dict[str, Message] = {
        "message:X": Message(id="message:X", name="X", contract_digest="d1")
    }
    diagnostic = upsert_message_or_conflict(
        messages_by_id, "message:X", Message(id="message:X", name="X", contract_digest="d2")
    )
    assert diagnostic is not None
    assert diagnostic.code is DiagnosticCode.MESSAGE_CONTENT_CONFLICT
    assert messages_by_id["message:X"].contract_digest == "d1"
