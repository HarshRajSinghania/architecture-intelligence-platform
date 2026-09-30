"""Cypher text for the source-scoped import write path (`app.graph.importer`): claim MERGE templates,
ownership reads and expiry, per-source replay and capture state, and the per-scope current-inventory
row.

Moved verbatim out of `importer.py`. Two query constants that interpolate the internal infrastructure
labels stay beside their only caller there.
"""

# Ownership is now tracked per SOURCE INSTANCE, not per service-directory slug (ADR 0009): one
# source may declare many services, and a service may be declared by more than one source. A full
# reimport rewrites every `.owner_source_ids` value, so no data migration from the old `.sources`
# property name is required (a fresh graph never has both).
MERGE_NODE_TEMPLATE = (
    "MERGE (n:{label} {{id: $id}}) "
    "SET n += $props "
    "SET n.owner_source_ids = CASE WHEN $source_instance_id IN coalesce(n.owner_source_ids, []) "
    "THEN n.owner_source_ids ELSE coalesce(n.owner_source_ids, []) + $source_instance_id END"
)

MERGE_RELATION_TEMPLATE = (
    "MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
    "MERGE (a)-[r:{relation_type}]->(b) "
    "SET r.key = $key "
    "SET r.owner_source_ids = CASE WHEN $source_instance_id IN coalesce(r.owner_source_ids, []) "
    "THEN r.owner_source_ids ELSE coalesce(r.owner_source_ids, []) + $source_instance_id END "
    "SET r.evidence_ids = reduce(acc = coalesce(r.evidence_ids, []), eid IN $evidence_ids | "
    "CASE WHEN eid IN acc THEN acc ELSE acc + eid END)"
)

# Every claim this source owns, with its full committed owner set: a claim this source stops
# emitting expires only if no other source will own it (I1 §6), so the reconciliation plan needs the
# real owners, not only this source.
OWNED_NODE_IDS_QUERY = (
    "MATCH (n) WHERE $source_instance_id IN coalesce(n.owner_source_ids, []) "
    "RETURN n.id AS id, n.owner_source_ids AS owners"
)

OWNED_RELATION_KEYS_QUERY = (
    "MATCH ()-[r]->() WHERE $source_instance_id IN coalesce(r.owner_source_ids, []) "
    "RETURN r.key AS key, r.owner_source_ids AS owners"
)

STRIP_STALE_EVIDENCE_QUERY = (
    "UNWIND $ids AS eid "
    "MATCH ()-[r]->() WHERE eid IN coalesce(r.evidence_ids, []) "
    "SET r.evidence_ids = [x IN r.evidence_ids WHERE x <> eid]"
)

EXPIRE_NODES_QUERY = (
    "UNWIND $ids AS nid "
    "MATCH (n {id: nid}) "
    "SET n.owner_source_ids = [x IN n.owner_source_ids WHERE x <> $source_instance_id] "
    "WITH n WHERE size(n.owner_source_ids) = 0 "
    "DETACH DELETE n"
)

# A stale relation key must not be deleted outright just because its declaring source stopped
# declaring it - it may still carry OBSERVED evidence (the H4 telemetry pipeline) or DECLARED
# evidence from another declaring source (shared-evidence case). This strips $source_instance_id
# from r.owner_source_ids, recomputes r.evidence_ids by removing only ids that are (a) DECLARED and
# (b) actually attributed to $source_instance_id via that Evidence node's own owner_source_ids -
# never touching another source's DECLARED evidence or any OBSERVED evidence - and only deletes the
# relation once evidence_ids is truly empty.
EXPIRE_RELATIONS_QUERY = (
    "UNWIND $keys AS rkey "
    "MATCH ()-[r {key: rkey}]->() "
    "SET r.owner_source_ids = [x IN r.owner_source_ids WHERE x <> $source_instance_id] "
    "WITH r, [eid IN r.evidence_ids WHERE NOT EXISTS { "
    "MATCH (e:Evidence {id: eid}) "
    "WHERE e.evidence_type = 'DECLARED' AND $source_instance_id IN coalesce(e.owner_source_ids, []) "
    "} ] AS remaining_evidence_ids "
    "SET r.evidence_ids = remaining_evidence_ids "
    "WITH r WHERE size(r.evidence_ids) = 0 "
    "DELETE r"
)

READ_SOURCE_STATE_QUERY = (
    "MATCH (s:SourceState {source_instance_id: $source_instance_id}) "
    "RETURN s.semantic_input_digest AS semantic_input_digest, "
    "s.scope_definition_digest AS scope_definition_digest, "
    "s.capture_scope_namespaces AS capture_scope_namespaces, "
    "s.capture_cluster_uid AS capture_cluster_uid, "
    "s.capture_revision AS capture_revision, "
    "s.capture_evidence_mode AS capture_evidence_mode, "
    "s.capture_captured_at AS capture_captured_at"
)

WRITE_SOURCE_STATE_QUERY = (
    "MERGE (s:SourceState {source_instance_id: $source_instance_id}) "
    "SET s.semantic_input_digest = $semantic_input_digest, "
    "s.scope_definition_digest = $scope_definition_digest, "
    "s.discovery_scope_id = $discovery_scope_id"
)

# v0.6.0 I2.2d (decision record D5): what an accepted Kubernetes envelope says about its capture,
# kept on the source's SourceState so it is readable under the revision fence. Written only for a
# source that carries a capture (never for a filesystem source, and never as nulls), and dropped
# with the node when the source is removed.
WRITE_CAPTURE_SCOPE_QUERY = (
    "MATCH (s:SourceState {source_instance_id: $source_instance_id}) "
    "SET s.capture_scope_namespaces = $namespaces, s.capture_cluster_uid = $cluster_uid, "
    "s.capture_revision = $revision, s.capture_evidence_mode = $evidence_mode, "
    "s.capture_captured_at = $captured_at"
)

ANY_SCOPED_OBSERVED_CALL_QUERY = "MATCH (v:ScopedObservedCallV2) RETURN v.id AS id LIMIT 1"

READ_SOURCE_STATES_FOR_SCOPE_QUERY = (
    "MATCH (s:SourceState {discovery_scope_id: $discovery_scope_id}) "
    "RETURN s.source_instance_id AS source_instance_id, "
    "s.scope_definition_digest AS scope_definition_digest"
)

DELETE_SOURCE_STATE_QUERY = (
    "MATCH (s:SourceState {source_instance_id: $source_instance_id}) DELETE s"
)

# I2 Draft 0.2 §3 prerequisite slice, items 3/4/5: one persisted "current committed inventory" node
# per discovery scope - sibling to `SourceState` above, which tracks per-*source* replay state.
# This tracks per-*scope* inventory-revision/capture/event-id/audit-chain state, feeding the
# transactional predecessor comparison and real (non-self-referential) values into
# `authorize_source_removal`/`validate_tombstone_against_committed_inventory`.
#
# This is a MERGE, not a plain MATCH, even though it is only ever used as a read: under Neo4j's
# default read-committed isolation, a plain MATCH takes no lock, so two concurrent transactions for
# the same scope could both read the same pre-image, both pass their own predecessor check, and
# both proceed to write - a real TOCTOU race found in PR review. MERGE acquires an exclusive lock
# on the matched-or-created node for the rest of the transaction, so a second concurrent
# transaction for the same scope blocks here until the first commits or rolls back, and then
# correctly observes the first transaction's real, committed result rather than a stale snapshot.
# A freshly created node's fields are all null, which this module already treats identically to "no
# prior committed inventory" below.
READ_CURRENT_INVENTORY_QUERY = (
    "MERGE (i:CurrentInventory {discovery_scope_id: $discovery_scope_id}) "
    "RETURN i.inventory_revision AS inventory_revision, "
    "i.inventory_capture_id AS inventory_capture_id, "
    "i.inventory_event_id AS inventory_event_id, "
    "i.scope_definition_digest AS scope_definition_digest, "
    "i.discovery_scope_id AS discovery_scope_id"
)

WRITE_CURRENT_INVENTORY_QUERY = (
    "MERGE (i:CurrentInventory {discovery_scope_id: $discovery_scope_id}) "
    "SET i.inventory_revision = $inventory_revision, "
    "i.inventory_capture_id = $inventory_capture_id, "
    "i.inventory_event_id = $inventory_event_id, "
    "i.scope_definition_digest = $scope_definition_digest"
)

NODE_LABELS_QUERY = "UNWIND $ids AS nid MATCH (n {id: nid}) RETURN n.id AS id, labels(n) AS labels"

SNAPSHOT_NODE_PROPS_QUERY = (
    "UNWIND $ids AS nid MATCH (n {id: nid}) RETURN n.id AS id, properties(n) AS props"
)

SNAPSHOT_RELATION_PROPS_QUERY = (
    "UNWIND $keys AS rkey MATCH ()-[r {key: rkey}]->() RETURN r.key AS key, properties(r) AS props"
)
