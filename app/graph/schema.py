from typing import LiteralString

import neo4j

from app.graph.revision_fence import ensure_revision_singleton

CONSTRAINTS: list[LiteralString] = [
    "CREATE CONSTRAINT service_id IF NOT EXISTS FOR (s:Service) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT operation_id IF NOT EXISTS FOR (o:Operation) REQUIRE o.id IS UNIQUE",
    "CREATE CONSTRAINT queue_id IF NOT EXISTS FOR (q:Queue) REQUIRE q.id IS UNIQUE",
    # v0.5.0 I4 (spec §7/§11): uniqueness for the Topic/Subscription identities, plus the two
    # internal source-owned Pub/Sub carriers (app.canonical.pubsub).
    "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
    ("CREATE CONSTRAINT subscription_id IF NOT EXISTS FOR (s:Subscription) REQUIRE s.id IS UNIQUE"),
    (
        "CREATE CONSTRAINT pubsub_declaration_id IF NOT EXISTS "
        "FOR (d:PubSubDeclaration) REQUIRE d.id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT subscription_dead_letter_configuration_id IF NOT EXISTS "
        "FOR (c:SubscriptionDeadLetterConfiguration) REQUIRE c.id IS UNIQUE"
    ),
    "CREATE CONSTRAINT message_id IF NOT EXISTS FOR (m:Message) REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT schema_id IF NOT EXISTS FOR (s:Schema) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (e:Evidence) REQUIRE e.id IS UNIQUE",
    # I1 v0.5.0 PR 3a: one committed-replay-state node per source instance, read/written by
    # app.graph.importer to feed app.sources.replay.classify_replay_case. v0.6.0 I2.2d (decision
    # record D5): a Kubernetes source's SourceState also carries the capture its accepted envelope
    # describes - capture_scope_namespaces (sorted), capture_cluster_uid, capture_revision,
    # capture_evidence_mode, capture_captured_at (the raw envelope string). They are written only
    # for a source that has a capture (never nulls, never for a filesystem source), are dropped
    # with the node on removal, and are not part of the snapshot until scoped v2 evidence exists.
    (
        "CREATE CONSTRAINT source_state_source_instance_id IF NOT EXISTS "
        "FOR (s:SourceState) REQUIRE s.source_instance_id IS UNIQUE"
    ),
    # I2 Draft 0.2 §3 prerequisite slice: one persisted "current committed inventory" node per
    # discovery scope, read/written by app.graph.importer to feed the transactional predecessor
    # comparison and the inventory_event_id audit chain.
    (
        "CREATE CONSTRAINT current_inventory_discovery_scope_id IF NOT EXISTS "
        "FOR (i:CurrentInventory) REQUIRE i.discovery_scope_id IS UNIQUE"
    ),
    # I2 Draft 0.2 §3 item 6 / §7: internal-only infrastructure facts, owned and reconciled through
    # the same per-source machinery as every other canonical node - so they need the same stable-id
    # uniqueness guarantee.
    (
        "CREATE CONSTRAINT infrastructure_entity_id IF NOT EXISTS "
        "FOR (e:InfrastructureEntity) REQUIRE e.id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT infrastructure_contribution_id IF NOT EXISTS "
        "FOR (c:InfrastructureContribution) REQUIRE c.id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT infrastructure_claim_id IF NOT EXISTS "
        "FOR (c:InfrastructureClaim) REQUIRE c.id IS UNIQUE"
    ),
    # I2 Draft 0.2 §7.2: one per-source claim-support row, id-scoped per (claim, source) exactly
    # like InfrastructureContribution - see app.graph.importer's own module docstring on why a
    # claim's shared evidence_refs is derived from these rather than written to directly.
    (
        "CREATE CONSTRAINT infrastructure_claim_contribution_id IF NOT EXISTS "
        "FOR (c:InfrastructureClaimContribution) REQUIRE c.id IS UNIQUE"
    ),
    # v0.4.0 I1.2, spec §19: read_revision()/bump_revision() rely on (:AipInternalState {id}) being
    # a true singleton (read_revision() uses .single()) - without this, a concurrent
    # ensure_revision_singleton() race could create a duplicate and break stable-read fencing.
    "CREATE CONSTRAINT aip_internal_state_id IF NOT EXISTS FOR (s:AipInternalState) REQUIRE s.id IS UNIQUE",
    # v0.5.0 I3 §9.4/§23 slice 2: a bounded OTel runtime identity observation, kept under its own
    # label rather than :Evidence - see app.provenance.model.RuntimeIdentityObservation's docstring.
    (
        "CREATE CONSTRAINT runtime_identity_observation_id IF NOT EXISTS "
        "FOR (o:RuntimeIdentityObservation) REQUIRE o.id IS UNIQUE"
    ),
    # v0.6.0 I2.2a (decision record D1): the isolated caller-Pod-scoped v2 observed CALLS record -
    # its own label, never :Evidence, no relationships, no owner_source_ids. See
    # app.provenance.model.ScopedObservedCall.
    (
        "CREATE CONSTRAINT scoped_observed_call_v2_id IF NOT EXISTS "
        "FOR (v:ScopedObservedCallV2) REQUIRE v.id IS UNIQUE"
    ),
    # v0.6.0 I2.2c (decision record D7/D8): operational provenance for scoped evidence - the cutover
    # ledger (a per-graph singleton), the durable pre-enablement v1 CALLS-bucket membership and the
    # exact transition counters. Bare nodes: no relationships, no owner_source_ids, never part of
    # the snapshot, the public evidence surface or the NL approved labels.
    (
        "CREATE CONSTRAINT scoped_evidence_cutover_id IF NOT EXISTS "
        "FOR (c:ScopedEvidenceCutover) REQUIRE c.id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT scoped_evidence_legacy_bucket_id IF NOT EXISTS "
        "FOR (b:ScopedEvidenceLegacyBucket) REQUIRE b.id IS UNIQUE"
    ),
    (
        "CREATE CONSTRAINT scoped_evidence_transition_counter_id IF NOT EXISTS "
        "FOR (c:ScopedEvidenceTransitionCounter) REQUIRE c.id IS UNIQUE"
    ),
]

INDEXES: list[LiteralString] = [
    # The v2 candidate reader filters by caller Service (decision record D3); without this it would
    # scan every v2 node, which grows with Pod churn.
    (
        "CREATE INDEX scoped_observed_call_v2_subject IF NOT EXISTS "
        "FOR (v:ScopedObservedCallV2) ON (v.subject_id)"
    ),
]


def ensure_schema(session: neo4j.Session) -> None:
    """Applies the spec §11.4 uniqueness constraints idempotently, and ensures the v0.4.0 I1.2
    internal revision-fence singleton exists (spec §19) before the graph is written to or read
    through the architecture-intelligence contract."""
    for statement in CONSTRAINTS:
        session.run(statement)
    for statement in INDEXES:
        session.run(statement)
    ensure_revision_singleton(session)
