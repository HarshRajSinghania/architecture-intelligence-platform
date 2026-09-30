from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field

from app.common.encoding import length_delimited, length_delimited_group, sha256_hex, utf8
from app.sources.model import DiscoveryScopeId, IngestionDiagnostic
from app.sources.tombstones import Tombstone


class InventoryStatus(StrEnum):
    """I1 spec §6: "status (COMPLETE, PARTIAL, or FAILED)"."""

    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class SourceInventorySnapshot(BaseModel):
    """I1 spec §6: "Every discovery run SHALL produce a SourceInventorySnapshot containing an
    inventory revision and capture identity, DiscoveryScopeId, scope digest, discoverer/adapter and
    mapping-rule identities, status ..., discovered source IDs, explicit tombstones, provider
    revision where available, capture time, and diagnostic references."

    Field shape is this PR's own choice - the spec gives only a prose bullet list, not a schema, the
    same discipline `SourceDescriptor` used in PR #1 - and is called out for review. The one prose
    bullet "discoverer/adapter and mapping-rule identities" is split into three fields here.
    "Diagnostic references" is interpreted as embedding full `IngestionDiagnostic` objects, since no
    separate diagnostic store exists yet to reference by id.
    """

    inventory_revision: str
    inventory_capture_id: str
    inventory_event_id: str | None = None
    discovery_scope_id: str
    scope_definition_digest: str
    discoverer_identity: str
    adapter_identities: tuple[str, ...] = ()
    mapping_rule_identities: tuple[str, ...] = ()
    status: InventoryStatus
    discovered_source_ids: tuple[str, ...] = ()
    tombstones: tuple[Tombstone, ...] = ()
    provider_revision: str | None = None
    capture_time: str
    diagnostics: tuple[IngestionDiagnostic, ...] = Field(default_factory=tuple)


def _tombstone_sort_key(tombstone: Tombstone) -> tuple[str, str]:
    return (tombstone.target_source_instance_id, tombstone.tombstone_revision)


def _tombstone_bytes(tombstone: Tombstone) -> bytes:
    """Deterministic encoding of a tombstone's identity-relevant fields, used only to feed
    `inventory_revision`'s "ordered tombstones" hash input. Not itself a spec-named formula.
    """
    return length_delimited(
        utf8(tombstone.target_source_instance_id),
        utf8(tombstone.discovery_scope_id),
        utf8(tombstone.expected_prior_inventory_revision),
        utf8(tombstone.scope_definition_digest),
        utf8(tombstone.actor),
        utf8(tombstone.reason),
        utf8(tombstone.tombstone_revision),
    )


def inventory_revision(
    *,
    discovery_scope_id: DiscoveryScopeId,
    scope_definition_digest: str,
    source_instance_ids: Sequence[str],
    tombstones: Sequence[Tombstone],
    status: InventoryStatus,
) -> str:
    """I1 spec §6:

        inventory_revision
          = urn:aip:inventory-revision:<sha256(DiscoveryScopeId, scope_definition_digest,
              ordered source ids, ordered tombstones, completion status)>

        "inventory_revision is semantic and idempotent: identical enumerations produce the same
        revision."

    Unlike `scope_definition_digest` (which leaves ordering to the caller), this function
    internally sorts `source_instance_ids` and `tombstones` before hashing, since idempotence under
    permutation is a hard requirement stated explicitly for this formula. Each sequence is nested
    via `length_delimited_group` so the two groups can never bleed into each other.
    """
    ordered_source_ids = sorted(source_instance_ids)
    ordered_tombstones = sorted(tombstones, key=_tombstone_sort_key)
    digest_input = length_delimited(
        utf8(discovery_scope_id),
        utf8(scope_definition_digest),
        length_delimited_group([utf8(sid) for sid in ordered_source_ids]),
        length_delimited_group([_tombstone_bytes(t) for t in ordered_tombstones]),
        utf8(status.value),
    )
    return f"urn:aip:inventory-revision:{sha256_hex(digest_input)}"


def inventory_capture_id(
    *,
    inventory_revision: str,
    normalized_provider_revision: str | None,
    capture_time: str,
) -> str:
    """I1 spec §6:

        inventory_capture_id
          = urn:aip:inventory-capture:<sha256(inventory_revision,
              normalized provider revision, capture time)>

        "inventory_capture_id distinguishes repeated captures without affecting semantic replay."

    Unlike `source_capture_id` (§5.2), there is no "equals verbatim when no provider revision"
    special case here: `capture_time` is always present, so this always produces a freshly hashed,
    `urn:aip:inventory-capture:`-prefixed value distinguishing repeated captures even absent a
    provider revision.
    """
    digest_input = length_delimited(
        utf8(inventory_revision),
        utf8(normalized_provider_revision or ""),
        utf8(capture_time),
    )
    return f"urn:aip:inventory-capture:{sha256_hex(digest_input)}"


def inventory_event_id(*, previous_event_id: str | None, inventory_capture_id: str) -> str:
    """I1 spec §6:

        inventory_event_id, optional audit-chain identity
          = urn:aip:inventory-event:<sha256(previous event id, inventory_capture_id)>

        "The optional event ID may provide chronology but MUST NOT participate in semantic
        equality, removal authority, or graph-revision decisions."

    Genesis (no previous event) is encoded as an explicit empty-string placeholder field, not
    specified by the spec text.
    """
    digest_input = length_delimited(utf8(previous_event_id or ""), utf8(inventory_capture_id))
    return f"urn:aip:inventory-event:{sha256_hex(digest_input)}"
