"""Graph writes and snapshot reads for the source-scoped import (`app.graph.importer`): MERGE of
canonical nodes, Pub/Sub carriers, infrastructure entities/contributions/claims and relations, claim
expiry, infrastructure-claim evidence recomputation, the Kubernetes capture scope, and the
property snapshots the importer diffs before and after a write. Every function runs inside the
caller's transaction; none opens a session.

Moved verbatim out of `importer.py`.
"""

import neo4j

from app.canonical.model import ArchitectureModel, relation_key
from app.canonical.pubsub import (
    PUBSUB_DECLARATION_LABEL,
    SUBSCRIPTION_DEAD_LETTER_CONFIGURATION_LABEL,
)
from app.common.jcs import canonical_json_bytes
from app.graph import claim_planning
from app.graph.labels import (
    INFRASTRUCTURE_CLAIM_CONTRIBUTION_LABEL,
    INFRASTRUCTURE_CLAIM_LABEL,
    INFRASTRUCTURE_CONTRIBUTION_LABEL,
    INFRASTRUCTURE_ENTITY_LABEL,
    NODE_LABELS,
)
from app.graph.queries import (
    EXPIRE_NODES_QUERY,
    EXPIRE_RELATIONS_QUERY,
    MERGE_NODE_TEMPLATE,
    MERGE_RELATION_TEMPLATE,
    SNAPSHOT_NODE_PROPS_QUERY,
    SNAPSHOT_RELATION_PROPS_QUERY,
    STRIP_STALE_EVIDENCE_QUERY,
    WRITE_CAPTURE_SCOPE_QUERY,
)
from app.sources.claim_reconciliation import (
    SourceClaimReconciliationPlan,
)
from app.sources.model import (
    KubernetesCaptureScope,
)


def expire_dropped_claims(
    tx: neo4j.ManagedTransaction,
    *,
    source_instance_id: str,
    node_plan: SourceClaimReconciliationPlan,
    relation_plan: SourceClaimReconciliationPlan,
) -> None:
    """Retire every claim this source dropped. Expired and ownership-removed claims share the same
    queries: each removes this source as an owner and deletes only what is left without one, and the
    relation query also strips this source's DECLARED evidence, which a shared relation must lose
    too. The plan's split decides only what the report says, never a different mutation."""
    dropped_relations = (
        relation_plan.expired_claim_keys | relation_plan.ownership_removed_claim_keys
    )
    if dropped_relations:
        tx.run(
            EXPIRE_RELATIONS_QUERY,
            keys=sorted(dropped_relations),
            source_instance_id=source_instance_id,
        )
    if node_plan.expired_claim_keys:
        tx.run(STRIP_STALE_EVIDENCE_QUERY, ids=sorted(node_plan.expired_claim_keys))
    dropped_nodes = node_plan.expired_claim_keys | node_plan.ownership_removed_claim_keys
    if dropped_nodes:
        tx.run(
            EXPIRE_NODES_QUERY,
            ids=sorted(dropped_nodes),
            source_instance_id=source_instance_id,
        )


def write_nodes(
    tx: neo4j.ManagedTransaction, source_instance_id: str, model: ArchitectureModel
) -> int:
    count = 0
    for field_name, label in NODE_LABELS.items():
        query = MERGE_NODE_TEMPLATE.format(label=label)
        for entity in getattr(model, field_name):
            # Cypher can't parametrize a label; `label` comes from NODE_LABELS or a module-level
            # carrier label constant, never from input, so the formatted query is not injectable.
            tx.run(
                query,  # pyright: ignore[reportArgumentType]
                id=entity.id,
                props=entity.model_dump(exclude={"id"}),
                source_instance_id=source_instance_id,
            )
            count += 1
    count += _write_pubsub_carrier_nodes(tx, source_instance_id, model)
    return count + _write_infrastructure_nodes(tx, source_instance_id, model)


def _write_pubsub_carrier_nodes(
    tx: neo4j.ManagedTransaction, source_instance_id: str, model: ArchitectureModel
) -> int:
    """v0.5.0 I4 spec §10/§11: the internal source-owned carriers, deliberately outside
    `NODE_LABELS` (their `id` is a computed property, and they must stay out of the NL-query label
    allowlist and snapshot canonicalization), written with the same MERGE template as
    `_write_infrastructure_nodes`' contributions."""
    count = 0
    for label, carriers in (
        (PUBSUB_DECLARATION_LABEL, model.pubsub_declarations),
        (
            SUBSCRIPTION_DEAD_LETTER_CONFIGURATION_LABEL,
            model.subscription_dead_letter_configurations,
        ),
    ):
        query = MERGE_NODE_TEMPLATE.format(label=label)
        for carrier in carriers:
            # Cypher can't parametrize a label; `label` comes from NODE_LABELS or a module-level
            # carrier label constant, never from input, so the formatted query is not injectable.
            tx.run(
                query,  # pyright: ignore[reportArgumentType]
                id=carrier.id,
                props=carrier.model_dump(),
                source_instance_id=source_instance_id,
            )
            count += 1
    return count


def _infrastructure_entity_props(entity) -> dict:
    """I2 Draft 0.2 §7.1 delegates "persistence encoding" to the implementation. Everything except
    `ports` is already a Neo4j-storable primitive; `ports` is the Canonical Model's only nested
    object, and Neo4j properties cannot hold nested maps - so each port is stored as one RFC 8785
    canonical-JSON string, reusing `app.common.jcs` rather than inventing a second canonicalization.
    The list stays in the entity's own §7.1 sorted order, so the stored value is deterministic and
    the before/after property snapshot that drives the revision fence stays meaningful.
    """
    props = entity.model_dump(exclude={"id", "ports"})
    props["ports"] = [
        canonical_json_bytes(port.model_dump()).decode("utf-8") for port in entity.ports
    ]
    return props


_INFRASTRUCTURE_CLAIM_ID_PREFIX = "urn:aip:infra-claim:"


_READ_CLAIM_CONTRIBUTION_EVIDENCE_QUERY = (
    f"MATCH (c:{INFRASTRUCTURE_CLAIM_CONTRIBUTION_LABEL} {{claim_id: $claim_id}}) "
    "RETURN c.evidence_refs AS evidence_refs"
)


_SET_CLAIM_EVIDENCE_REFS_QUERY = (
    f"MATCH (n:{INFRASTRUCTURE_CLAIM_LABEL} {{id: $claim_id}}) SET n.evidence_refs = $evidence_refs"
)


def recompute_affected_infrastructure_claims(
    tx: neo4j.ManagedTransaction,
    node_plan,
    *,
    currently_emitted_claim_ids: frozenset[str] = frozenset(),
) -> None:
    """Recomputes every infrastructure claim a source's own reconciliation step could have
    affected: every claim it currently emits (`currently_emitted_claim_ids` - empty for whole-source
    removal, which emits nothing), plus every claim it just stopped emitting (found by filtering
    `node_plan`'s expired/ownership-removed id set for the claim-id prefix, since that set mixes
    every node kind together). Must run AFTER this source's own nodes are written/reconciled, so the
    read-your-own-writes view each recompute sees already reflects them.
    """
    affected_claim_ids = currently_emitted_claim_ids | {
        node_id
        for node_id in node_plan.expired_claim_keys | node_plan.ownership_removed_claim_keys
        if node_id.startswith(_INFRASTRUCTURE_CLAIM_ID_PREFIX)
    }
    for claim_id in sorted(affected_claim_ids):
        _recompute_infrastructure_claim_evidence(tx, claim_id)


def _recompute_infrastructure_claim_evidence(tx: neo4j.ManagedTransaction, claim_id: str) -> None:
    """A claim's `evidence_refs` is never written directly from any one source's model - it is
    recomputed, from scratch, as the sorted union of every *currently live*
    `InfrastructureClaimContribution` row for this claim id. Correct regardless of why this claim
    was touched: a brand-new claim, a retained claim whose owning source replaced its own evidence
    (the specific bug this replaces two prior write-time-union attempts to fix), or a claim losing
    one of several owners (a real co-ownership bug found in PR review) - all three reduce to "read
    what's currently there and set the union," with no incremental accumulate/strip logic to get
    subtly wrong. A no-op if the claim node was already deleted (its last contribution just expired):
    `MATCH` finds no rows to `SET`.
    """
    refs: set[str] = set()
    for record in tx.run(_READ_CLAIM_CONTRIBUTION_EVIDENCE_QUERY, claim_id=claim_id):
        refs.update(record["evidence_refs"] or [])
    tx.run(_SET_CLAIM_EVIDENCE_REFS_QUERY, claim_id=claim_id, evidence_refs=sorted(refs))


def _write_infrastructure_nodes(
    tx: neo4j.ManagedTransaction, source_instance_id: str, model: ArchitectureModel
) -> int:
    """I2 Draft 0.2 §3 item 6: infrastructure entities, contributions, and claims are written
    through the same MERGE-with-`owner_source_ids` template as every other canonical node, so they
    inherit the identical ownership, shared-ownership, reconciliation, and expiry semantics without
    a second mechanism (§12: "no second reconciliation engine is permitted").

    Contributions and claims are nodes rather than graph relationships on purpose: `WORKLOAD_EXISTS`
    is a first-class *unary* claim, and §7.2 forbids inventing "a sentinel entity or self-edge to
    force it through a binary-relation representation" - modelling all four claim kinds uniformly as
    owned claim nodes honors that, and keeps these internal-only facts out of every existing
    untyped relationship traversal (§9: they "MUST NOT leak through generic serialization, existing
    dependency answers, or a graph tool").
    """
    count = 0
    entity_query = MERGE_NODE_TEMPLATE.format(label=INFRASTRUCTURE_ENTITY_LABEL)
    for entity in model.infrastructure_entities:
        tx.run(
            entity_query,
            id=entity.id,
            props=_infrastructure_entity_props(entity),
            source_instance_id=source_instance_id,
        )
        count += 1

    contribution_query = MERGE_NODE_TEMPLATE.format(label=INFRASTRUCTURE_CONTRIBUTION_LABEL)
    for contribution in model.infrastructure_contributions:
        tx.run(
            contribution_query,
            id=contribution.id,
            props=contribution.model_dump(),
            source_instance_id=source_instance_id,
        )
        count += 1

    # I2 Draft 0.2 §7.2: "Evidence mode is retained per contribution... merging declarations and
    # captures never turns all support into observation" - the same requirement §7.1 states for
    # entity contributions, applied to claim contributions too. `InfrastructureClaim` itself (§7.2's
    # frozen adapter-facing schema) carries no `evidence_mode` field - by design, since that's a
    # per-CONTRIBUTION property, not a property of the shared claim - so it is looked up here from
    # this SAME model's own entity contribution for the claim's subject, which does carry it. This
    # holds because a claim and its subject's own contribution are always emitted together by the
    # same adapter for the same source in the same model, and §4.1 guarantees one source has exactly
    # one immutable evidence mode - so the subject's contribution is authoritative for this claim's
    # contribution too. `None` only if the model is malformed (a claim whose subject has no
    # contribution from this same source at all).
    contribution_by_entity_id = {c.entity_id: c for c in model.infrastructure_contributions}

    # The claim node itself carries every field EXCEPT evidence_refs, which is never written here -
    # see `_recompute_infrastructure_claim_evidence`. Its own per-source CONTRIBUTION row (id-scoped
    # per (claim, source), so a reimport correctly overwrites rather than accumulates) is what
    # actually carries this source's own evidence_refs and evidence mode.
    claim_query = MERGE_NODE_TEMPLATE.format(label=INFRASTRUCTURE_CLAIM_LABEL)
    claim_contribution_query = MERGE_NODE_TEMPLATE.format(
        label=INFRASTRUCTURE_CLAIM_CONTRIBUTION_LABEL
    )
    for claim in model.infrastructure_claims:
        tx.run(
            claim_query,
            id=claim.id,
            props=claim.model_dump(exclude={"evidence_refs"}),
            source_instance_id=source_instance_id,
        )
        subject_contribution = contribution_by_entity_id.get(claim.subject_id)
        tx.run(
            claim_contribution_query,
            id=claim_planning.infrastructure_claim_contribution_id(claim.id, source_instance_id),
            props={
                "claim_id": claim.id,
                "evidence_refs": claim.evidence_refs,
                "mapping_rule_id": claim.mapping_rule_id,
                "mapping_rule_version": claim.mapping_rule_version,
                "evidence_mode": (
                    subject_contribution.evidence_mode if subject_contribution else None
                ),
            },
            source_instance_id=source_instance_id,
        )
        count += 2
    return count


def snapshot_node_props(tx: neo4j.ManagedTransaction, node_ids: set[str]) -> dict[str, dict]:
    if not node_ids:
        return {}
    return {
        record["id"]: dict(record["props"])
        for record in tx.run(SNAPSHOT_NODE_PROPS_QUERY, ids=list(node_ids))
    }


def snapshot_relation_props(
    tx: neo4j.ManagedTransaction, relation_keys: set[str]
) -> dict[str, dict]:
    if not relation_keys:
        return {}
    return {
        record["key"]: dict(record["props"])
        for record in tx.run(SNAPSHOT_RELATION_PROPS_QUERY, keys=list(relation_keys))
    }


def write_relations(
    tx: neo4j.ManagedTransaction, source_instance_id: str, model: ArchitectureModel
) -> int:
    for relation in model.relations:
        query = MERGE_RELATION_TEMPLATE.format(relation_type=relation.type)
        # Cypher can't parametrize a relationship type; `_import_source_tx` rejects any type outside
        # KNOWN_RELATION_TYPES before this runs, so the formatted query is not injectable.
        tx.run(
            query,  # pyright: ignore[reportArgumentType]
            source_id=relation.source_id,
            target_id=relation.target_id,
            key=relation_key(relation),
            source_instance_id=source_instance_id,
            evidence_ids=relation.evidence_ids,
        )
    return len(model.relations)


def capture_properties(record: neo4j.Record | None) -> tuple | None:
    """The five persisted capture properties of a committed SourceState, or None if it has none
    (no SourceState yet, or a source that never carried a capture)."""
    if record is None or record["capture_cluster_uid"] is None:
        return None
    return (
        tuple(record["capture_scope_namespaces"] or ()),
        record["capture_cluster_uid"],
        record["capture_revision"],
        record["capture_evidence_mode"],
        record["capture_captured_at"],
    )


def write_capture_scope(
    tx: neo4j.ManagedTransaction, source_instance_id: str, capture_scope: KubernetesCaptureScope
) -> tuple:
    tx.run(
        WRITE_CAPTURE_SCOPE_QUERY,
        source_instance_id=source_instance_id,
        namespaces=sorted(capture_scope.namespaces),
        cluster_uid=capture_scope.cluster_uid,
        revision=capture_scope.revision,
        evidence_mode=capture_scope.evidence_mode,
        captured_at=capture_scope.captured_at,
    )
    return (
        tuple(sorted(capture_scope.namespaces)),
        capture_scope.cluster_uid,
        capture_scope.revision,
        capture_scope.evidence_mode,
        capture_scope.captured_at,
    )
