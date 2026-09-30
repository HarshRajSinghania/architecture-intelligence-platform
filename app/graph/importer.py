from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import replace

import neo4j

from app.canonical.model import ArchitectureModel, relation_key
from app.graph import claim_planning, writers
from app.graph.labels import (
    KNOWN_RELATION_TYPES,
    NODE_LABELS,
)
from app.graph.queries import (
    ANY_SCOPED_OBSERVED_CALL_QUERY,
    DELETE_SOURCE_STATE_QUERY,
    NODE_LABELS_QUERY,
    OWNED_NODE_IDS_QUERY,
    OWNED_RELATION_KEYS_QUERY,
    READ_CURRENT_INVENTORY_QUERY,
    READ_SOURCE_STATE_QUERY,
    READ_SOURCE_STATES_FOR_SCOPE_QUERY,
    WRITE_CURRENT_INVENTORY_QUERY,
    WRITE_SOURCE_STATE_QUERY,
)
from app.graph.repository import open_session
from app.graph.revision_fence import bump_revision, lock_revision
from app.graph.schema import ensure_schema
from app.ingestion.orchestrator import (
    DiscoveryRunResult,
    SourceRunOutcome,
    run_filesystem_discovery,
    run_kubernetes_discovery,
)
from app.sources.claim_reconciliation import (
    plan_source_claim_reconciliation,
)
from app.sources.import_stats import (
    EmittedCounts,
    ImportRunStats,
    SourceClaimEffects,
    SourceImportStats,
    SourceRunResult,
    TombstoneDecision,
)
from app.sources.inventory import InventoryStatus
from app.sources.inventory import inventory_event_id as compute_inventory_event_id
from app.sources.migration_mappings import SharedIdentityMappingIndex
from app.sources.model import (
    NOT_SUPPLIED,
    DiagnosticCode,
    FilesystemSourceConfig,
    IngestionDiagnostic,
    IngestionResult,
    KubernetesCaptureScope,
    KubernetesSourceConfig,
    NotSupplied,
    SourceInstanceId,
)
from app.sources.removal_authority import authorize_source_removal
from app.sources.replay import ReplayCase, classify_replay_case
from app.sources.tombstones import (
    Tombstone,
    TombstoneValidation,
    validate_tombstone_against_committed_inventory,
)

# NotSupplied/NOT_SUPPLIED were relocated to app.sources.model in I2 Draft 0.2 slice 2b-ii - see
# that module's own docstring for why (app.sources.registry/app.ingestion.orchestrator, both lower
# layers this module already imports from, also need the type for their own
# `expected_prior_inventory_revision` fields).


class StalePredecessorError(RuntimeError):
    """Raised inside `_import_all_sources_tx` when a caller-supplied expected predecessor
    inventory revision does not match what is actually committed for the scope - I2 Draft 0.2 §3
    prerequisite slice, item 4. Raising aborts the whole transaction before any write, so prior
    committed state is left untouched; `import_discovery_run` catches this and reports the run as
    not committed."""


# The public canonical node labels (the `NODE_LABELS` entities, minus Evidence). Every other owned
# node is internal-only, and appears in a `ClaimEffectSet` only as a count.
_PUBLIC_NODE_LABELS = frozenset(label for label in NODE_LABELS.values() if label != "Evidence")
_PUBLIC_MODEL_FIELDS = tuple(
    field for field, label in NODE_LABELS.items() if label in _PUBLIC_NODE_LABELS
)


def _public_node_ids(
    tx: neo4j.ManagedTransaction, node_ids: set[str], model: ArchitectureModel
) -> frozenset[str]:
    """The public canonical ids among `node_ids`: by the model's own fields for what this source
    emits, and by committed label for what it owned before (which may no longer be emitted)."""
    public = {entity.id for field in _PUBLIC_MODEL_FIELDS for entity in getattr(model, field)}
    if node_ids:
        public.update(
            record["id"]
            for record in tx.run(NODE_LABELS_QUERY, ids=list(node_ids))
            if _PUBLIC_NODE_LABELS.intersection(record["labels"])
        )
    return frozenset(public & node_ids)


def import_source(
    session: neo4j.Session,
    *,
    source_instance_id: str,
    locator: str,
    model: ArchitectureModel,
    result: IngestionResult = IngestionResult.ACCEPTED,
    semantic_input_digest: str,
    discovery_scope_id: str,
    scope_definition_digest: str,
    capture_scope: KubernetesCaptureScope | None = None,
) -> SourceImportStats:
    """Transactionally MERGEs one source instance's facts and expires its stale ones, applying the
    I1 spec §5.4 replay decision against this source's own previously committed state. Public
    (unlike the transaction function it wraps) so callers - tests included - can drive one source's
    import directly without needing a full filesystem discovery run.
    """
    return session.execute_write(
        _import_source_tx,
        source_instance_id=source_instance_id,
        locator=locator,
        model=model,
        result=result,
        semantic_input_digest=semantic_input_digest,
        discovery_scope_id=discovery_scope_id,
        scope_definition_digest=scope_definition_digest,
        capture_scope=capture_scope,
    )


def _import_source_tx(
    tx: neo4j.ManagedTransaction,
    *,
    source_instance_id: str,
    locator: str,
    model: ArchitectureModel,
    result: IngestionResult,
    # `None` only via `import_discovery_run` with a caller-built run result; the replay
    # classification and the SourceState write both already handle it.
    semantic_input_digest: str | None,
    discovery_scope_id: str | None,
    scope_definition_digest: str | None,
    committed_nodes_before: dict[str, dict] | None = None,
    committed_relations_before: dict[str, dict] | None = None,
    run_source_ids: AbstractSet[str] | None = None,
    run_node_emitters: Mapping[str, AbstractSet[str]] | None = None,
    run_relation_emitters: Mapping[str, AbstractSet[str]] | None = None,
    capture_scope: KubernetesCaptureScope | None = None,
) -> SourceImportStats:
    """`run_source_ids`/`run_node_emitters`/`run_relation_emitters` describe the whole discovery run
    (every source reconciled in it, and which of them emits each node id and relation key), so a
    dropped claim is classified by who owns it after the run; `None` means a run of this source
    alone.

    `committed_nodes_before`/`committed_relations_before`, when given, must be a snapshot of
    every node/relation this call could touch, taken before ANY write in this run (including
    another source's pre-merge) - see `_import_all_sources_tx`, which is the only caller that needs
    this: `import_all_sources` pre-merges every source's nodes before any source's own
    `_import_source_tx` runs (so cross-source relation targets always resolve), which would
    otherwise already have applied this exact source's own new property values by the time this
    function queried "before" state itself, making a real property-only change invisible to the
    no-op check below (a real bug found in PR review). `None` (the default, and always the case for
    a direct standalone `import_source()` call, which has no pre-merge step to race against) means
    "query the current graph state now" - correct there, since nothing else has written yet.
    """
    for relation in model.relations:
        if relation.type not in KNOWN_RELATION_TYPES:
            raise ValueError(f"Unknown relation type: {relation.type}")

    committed = tx.run(READ_SOURCE_STATE_QUERY, source_instance_id=source_instance_id).single()
    committed_semantic_input_digest = committed["semantic_input_digest"] if committed else None
    committed_scope_definition_digest = committed["scope_definition_digest"] if committed else None
    committed_capture = writers.capture_properties(committed)

    replay_decision = classify_replay_case(
        load_or_reevaluation_successful=True,
        committed_semantic_input_digest=committed_semantic_input_digest,
        new_semantic_input_digest=semantic_input_digest,
        committed_scope_definition_digest=committed_scope_definition_digest,
        new_scope_definition_digest=scope_definition_digest,
    )

    owned_nodes = {
        record["id"]: set(record["owners"] or ())
        for record in tx.run(OWNED_NODE_IDS_QUERY, source_instance_id=source_instance_id)
    }
    owned_relations = {
        record["key"]: set(record["owners"] or ())
        for record in tx.run(OWNED_RELATION_KEYS_QUERY, source_instance_id=source_instance_id)
    }
    existing_node_ids = set(owned_nodes)
    existing_relation_keys = set(owned_relations)

    new_node_ids = claim_planning.model_node_ids(model, source_instance_id=source_instance_id)
    new_relation_keys = claim_planning.model_relation_keys(model)
    if replay_decision.case is ReplayCase.SCOPE_CHANGED_PRESERVE_PENDING_TOMBSTONE:
        # I1 spec §5.4/§6: a scope change must not itself authorize expiring claims absent from the
        # new scope - only an explicit inventory transition/tombstone may. Treat everything this
        # source already owned as still "emitted" so nothing computes as dropped this run.
        new_node_ids = new_node_ids | existing_node_ids
        new_relation_keys = new_relation_keys | existing_relation_keys

    if run_source_ids is None:
        run_source_ids = {source_instance_id}
        run_node_emitters = {node_id: {source_instance_id} for node_id in new_node_ids}
        run_relation_emitters = {key: {source_instance_id} for key in new_relation_keys}
    node_plan = plan_source_claim_reconciliation(
        source_instance_id=SourceInstanceId(source_instance_id),
        committed_claim_owners=claim_planning.dropped_claim_owners(
            owned_nodes,
            source_instance_id=source_instance_id,
            run_source_ids=run_source_ids,
            run_emitters=run_node_emitters or {},
        ),
        newly_emitted_claim_keys=new_node_ids,
    )
    relation_plan = plan_source_claim_reconciliation(
        source_instance_id=SourceInstanceId(source_instance_id),
        committed_claim_owners=claim_planning.dropped_claim_owners(
            owned_relations,
            source_instance_id=source_instance_id,
            run_source_ids=run_source_ids,
            run_emitters=run_relation_emitters or {},
        ),
        newly_emitted_claim_keys=new_relation_keys,
    )

    # I1 §5.4/§14: a semantic no-op means the canonical snapshot doesn't change, not merely that
    # semantic_input_digest changed - an adapter's normalized projection can hash raw input the
    # canonical model never surfaces at all (e.g. OpenAPI's info.description, unmapped to any
    # canonical field). Snapshotting each emitted node/relation's properties immediately before and
    # after this source's own write isolates exactly what THIS write actually changed, independent
    # of what varied in the raw input bytes. Combined with node_plan/relation_plan's claim-KEY-set
    # diff (added/removed/expired), this is the complete no-op signal - the claim-set diff alone
    # misses a property-only change on a retained claim, and semantic_input_digest alone
    # over-triggers on a canonically-inert input change.
    if committed_nodes_before is not None:
        nodes_before = {k: v for k, v in committed_nodes_before.items() if k in new_node_ids}
    else:
        nodes_before = writers.snapshot_node_props(tx, new_node_ids)
    if committed_relations_before is not None:
        relations_before = {
            k: v for k, v in committed_relations_before.items() if k in new_relation_keys
        }
    else:
        relations_before = writers.snapshot_relation_props(tx, new_relation_keys)

    public_node_ids = _public_node_ids(tx, existing_node_ids | new_node_ids, model)

    nodes_written = writers.write_nodes(tx, source_instance_id, model)
    relations_written = writers.write_relations(tx, source_instance_id, model)

    writers.expire_dropped_claims(
        tx, source_instance_id=source_instance_id, node_plan=node_plan, relation_plan=relation_plan
    )

    # I2 Draft 0.2 §7.2: a brand-new claim, a retained one whose owning source just replaced its own
    # evidence (the specific bug this mechanism replaces two prior write-time-union attempts to
    # fix), and a claim losing one of several owners (a real co-ownership bug found in PR review)
    # all reduce to the same derive-from-scratch recompute.
    writers.recompute_affected_infrastructure_claims(
        tx,
        node_plan,
        currently_emitted_claim_ids=frozenset(claim.id for claim in model.infrastructure_claims),
    )

    tx.run(
        WRITE_SOURCE_STATE_QUERY,
        source_instance_id=source_instance_id,
        semantic_input_digest=semantic_input_digest,
        scope_definition_digest=scope_definition_digest,
        discovery_scope_id=discovery_scope_id,
    )
    new_capture = None
    if capture_scope is not None:
        new_capture = writers.write_capture_scope(tx, source_instance_id, capture_scope)

    nodes_after = writers.snapshot_node_props(tx, new_node_ids)
    relations_after = writers.snapshot_relation_props(tx, new_relation_keys)
    content_changed = nodes_before != nodes_after or relations_before != relations_after

    # graph_revision_advance_possible=False (FAILED_LOAD_PRESERVE_PRIOR, or REPLAY_NO_OP whose
    # byte-identical semantic_input_digest already proves nothing could have changed) is a
    # necessary condition: skip it and never advance, without paying for the snapshot diff at all.
    # Otherwise, is_no_op is the real decision - both the claim-KEY-set diff (an add/remove/
    # expire/ownership change, e.g. node_plan.is_semantic_no_op is False) AND the before/after
    # content diff above (a property-only change on a claim this source retains) count as a real
    # change; neither alone is sufficient (the claim-set diff alone misses property-only edits, and
    # semantic_input_digest alone over-triggers on an input change the canonical model never
    # surfaces, e.g. OpenAPI's info.description).
    is_no_op = (
        node_plan.is_semantic_no_op and relation_plan.is_semantic_no_op and not content_changed
    )
    graph_revision_advanced = replay_decision.graph_revision_advance_possible and not is_no_op
    if graph_revision_advanced:
        bump_revision(tx)
    elif new_capture is not None and new_capture != committed_capture:
        # v0.6.0 I2.2d (decision record D5 item 4): the capture's own properties feed the scoped
        # snapshot key once v2 records exist, but they are not part of the semantic input digest, so
        # a scope-, revision- or capturedAt-only change can be a replay no-op that would otherwise
        # leave the fence where it was. Take the fence lock BEFORE looking for v2, so a concurrent
        # unit writing the first v2 record cannot slip in unseen; with no v2 record nothing is
        # visible to advance and v0.5 behaviour is unchanged.
        lock_revision(tx)
        if tx.run(ANY_SCOPED_OBSERVED_CALL_QUERY).single() is not None:
            bump_revision(tx)
            graph_revision_advanced = True

    # Canonical effects by identity. Added-vs-retained is decided from the pre-run snapshot, not
    # from `node_plan`: in `_import_all_sources_tx` every source's nodes are pre-merged (with their
    # owner ids) before this function runs, so its ownership query already counts every emitted
    # node as owned. `changed` is attributed to this source alone, independent of the order the
    # run's sources are reconciled in: a retained node whose properties differ, ignoring the owner
    # bookkeeping another source's reconciliation may change (every source's property writes are
    # already pre-merged); and a retained relation that gains evidence this source emits, since a
    # relation's only other properties are its key and owners.
    model_node_ids = claim_planning.model_node_ids(model, source_instance_id=source_instance_id)
    previously_owned_nodes = (existing_node_ids - model_node_ids) | {
        node_id
        for node_id in model_node_ids
        if source_instance_id in (nodes_before.get(node_id) or {}).get("owner_source_ids", [])
    }
    model_relation_keys = claim_planning.model_relation_keys(model)
    previously_owned_relations = (existing_relation_keys - model_relation_keys) | {
        key
        for key in model_relation_keys
        if source_instance_id in (relations_before.get(key) or {}).get("owner_source_ids", [])
    }
    emitted_evidence: dict[str, set[str]] = {}
    for relation in model.relations:
        emitted_evidence.setdefault(relation_key(relation), set()).update(relation.evidence_ids)
    retained_nodes = new_node_ids & previously_owned_nodes
    retained_relations = new_relation_keys & previously_owned_relations
    effects = SourceClaimEffects(
        added=claim_planning.effect_set(
            new_node_ids - previously_owned_nodes,
            new_relation_keys - previously_owned_relations,
            public_node_ids,
        ),
        changed=claim_planning.effect_set(
            {
                i
                for i in retained_nodes
                if claim_planning.without_owners(nodes_before.get(i))
                != claim_planning.without_owners(nodes_after.get(i))
            },
            {
                k
                for k in retained_relations
                if not emitted_evidence.get(k, set())
                <= set((relations_before.get(k) or {}).get("evidence_ids") or ())
            },
            public_node_ids,
        ),
        expired=claim_planning.effect_set(
            node_plan.expired_claim_keys, relation_plan.expired_claim_keys, public_node_ids
        ),
        ownership_removed=claim_planning.effect_set(
            node_plan.ownership_removed_claim_keys,
            relation_plan.ownership_removed_claim_keys,
            public_node_ids,
        ),
    )

    return SourceImportStats(
        source_instance_id=source_instance_id,
        locator=locator,
        result=result,
        nodes_written=nodes_written,
        relations_written=relations_written,
        nodes_expired=len(node_plan.expired_claim_keys),
        relations_expired=len(relation_plan.expired_claim_keys),
        graph_revision_advanced=graph_revision_advanced,
        effects=effects,
    )


def _remove_source_tx(
    tx: neo4j.ManagedTransaction,
    *,
    source_instance_id: str,
    removed_source_ids: AbstractSet[str] = frozenset(),
) -> SourceImportStats:
    """`removed_source_ids` is every source the run removes (this one included): a claim they all
    owned expires for each of them, whichever is removed first."""
    owned_nodes = {
        record["id"]: set(record["owners"] or ())
        for record in tx.run(OWNED_NODE_IDS_QUERY, source_instance_id=source_instance_id)
    }
    owned_relations = {
        record["key"]: set(record["owners"] or ())
        for record in tx.run(OWNED_RELATION_KEYS_QUERY, source_instance_id=source_instance_id)
    }
    existing_node_ids = set(owned_nodes)
    removed = {source_instance_id, *removed_source_ids}
    node_plan = plan_source_claim_reconciliation(
        source_instance_id=SourceInstanceId(source_instance_id),
        committed_claim_owners=claim_planning.dropped_claim_owners(
            owned_nodes,
            source_instance_id=source_instance_id,
            run_source_ids=removed,
            run_emitters={},
        ),
        newly_emitted_claim_keys=frozenset(),
    )
    relation_plan = plan_source_claim_reconciliation(
        source_instance_id=SourceInstanceId(source_instance_id),
        committed_claim_owners=claim_planning.dropped_claim_owners(
            owned_relations,
            source_instance_id=source_instance_id,
            run_source_ids=removed,
            run_emitters={},
        ),
        newly_emitted_claim_keys=frozenset(),
    )
    # Classified before anything expires: an expired node may be deleted.
    public_node_ids = _public_node_ids(tx, existing_node_ids, ArchitectureModel())

    writers.expire_dropped_claims(
        tx, source_instance_id=source_instance_id, node_plan=node_plan, relation_plan=relation_plan
    )
    # This source dropped every claim it owned (emits nothing) - see the identical mechanism in
    # `_import_source_tx`.
    writers.recompute_affected_infrastructure_claims(tx, node_plan)
    tx.run(DELETE_SOURCE_STATE_QUERY, source_instance_id=source_instance_id)
    bump_revision(tx)

    return SourceImportStats(
        source_instance_id=source_instance_id,
        locator="",
        result=IngestionResult.ACCEPTED,
        nodes_written=0,
        relations_written=0,
        nodes_expired=len(node_plan.expired_claim_keys),
        relations_expired=len(relation_plan.expired_claim_keys),
        graph_revision_advanced=True,
        effects=SourceClaimEffects(
            expired=claim_planning.effect_set(
                node_plan.expired_claim_keys, relation_plan.expired_claim_keys, public_node_ids
            ),
            ownership_removed=claim_planning.effect_set(
                node_plan.ownership_removed_claim_keys,
                relation_plan.ownership_removed_claim_keys,
                public_node_ids,
            ),
        ),
    )


def _import_all_sources_tx(
    tx: neo4j.ManagedTransaction,
    *,
    run_result: DiscoveryRunResult,
    expected_prior_inventory_revision: str | None | NotSupplied = NOT_SUPPLIED,
) -> tuple[
    dict[str, SourceImportStats],
    tuple[str, ...],
    tuple[IngestionDiagnostic, ...],
    tuple[TombstoneDecision, ...],
    tuple[SourceImportStats, ...],
]:
    """Pre-merge, per-source reconciliation, and removal for one whole discovery run, all against
    the same transaction - a run either commits in full or (on any error, including a driver/
    infrastructure failure partway through) rolls back in full. Previously these were separate
    `execute_write` calls per source: a failure partway through the loop left earlier sources'
    writes committed even though the run as a whole never reached `ImportRunStats(committed=True)`
    - contradicting this module's own "nothing is written unless the whole run is COMPLETE"
    contract (I1 spec §6), a real bug found in PR review.

    I2 Draft 0.2 §3 prerequisite slice, items 3/4/5: also reads and (on success) rewrites the
    scope's `CurrentInventory` state in this same transaction. `expected_prior_inventory_revision`
    defaults to `NOT_SUPPLIED` (skip the check entirely - every existing caller's behavior is
    unchanged); a caller that opts in (including with an explicit `None`, meaning "expect no prior
    committed inventory") gets a real transactional predecessor comparison against what is actually
    persisted, raising `StalePredecessorError` (aborting the whole transaction, writing nothing) on
    a mismatch.
    """
    # A MERGE, not a MATCH - see _READ_CURRENT_INVENTORY_QUERY's own comment: this acquires an
    # exclusive per-scope lock for the rest of this transaction, so `.single()` always returns
    # exactly one row. For a freshly created node, `discovery_scope_id` is set immediately (it's
    # part of the MERGE's own matching pattern), but `inventory_revision`/`scope_definition_digest`/
    # `inventory_event_id` remain null - there is no real committed inventory yet. Treat
    # `inventory_revision is None` as the single source of truth for "nothing committed yet", and
    # normalize `discovery_scope_id` to `None` alongside it wherever "committed state" is passed
    # onward - passing the MERGE-created `discovery_scope_id` on its own would present a partially
    # populated committed state (id set, revision/digest null) to
    # `validate_tombstone_against_committed_inventory`, which raises
    # `InconsistentCommittedInventoryStateError` on exactly that inconsistency (a real bug found in
    # PR review: a tombstone submitted on a brand-new scope's very first run crashed instead of
    # being classified `NO_COMMITTED_INVENTORY`).
    persisted_inventory = tx.run(
        READ_CURRENT_INVENTORY_QUERY, discovery_scope_id=run_result.discovery_scope_id
    ).single()
    assert persisted_inventory is not None  # the MERGE always yields exactly one row
    has_committed_inventory = persisted_inventory["inventory_revision"] is not None
    committed_discovery_scope_id = (
        persisted_inventory["discovery_scope_id"] if has_committed_inventory else None
    )

    # Type-based, not identity-based: NotSupplied is a public type (relocated here from a
    # file-private sentinel in I2 Draft 0.2 slice 2b-ii specifically so lower layers could also use
    # it), so a caller can legally construct its own NotSupplied() instance - `is not NOT_SUPPLIED`
    # would treat that as a real predecessor value and incorrectly reject the run as stale. Any
    # NotSupplied instance, not only the canonical singleton, must mean "skip the check" (a real
    # finding from PR review).
    if not isinstance(expected_prior_inventory_revision, NotSupplied):
        actual_committed_revision = persisted_inventory["inventory_revision"]
        if actual_committed_revision != expected_prior_inventory_revision:
            raise StalePredecessorError(
                f"expected prior inventory revision {expected_prior_inventory_revision!r} for "
                f"scope {run_result.discovery_scope_id!r}, but the currently committed revision "
                f"is {actual_committed_revision!r}"
            )

    if run_result.inventory_snapshot is None:
        raise ValueError(
            "a commit-eligible discovery run must carry a real inventory_snapshot "
            f"(discovery_scope_id={run_result.discovery_scope_id!r})"
        )

    tombstone_validations: dict[str, TombstoneValidation] = {}
    tombstone_diagnostics: list[IngestionDiagnostic] = []
    tombstone_decisions: list[TombstoneDecision] = []
    for tombstone in run_result.inventory_snapshot.tombstones:
        validation = validate_tombstone_against_committed_inventory(
            tombstone=tombstone,
            committed_discovery_scope_id=committed_discovery_scope_id,
            committed_scope_definition_digest=persisted_inventory["scope_definition_digest"],
            committed_inventory_revision=persisted_inventory["inventory_revision"],
        )
        tombstone_validations[tombstone.target_source_instance_id] = validation
        tombstone_decisions.append(
            TombstoneDecision(
                target_source_instance_id=tombstone.target_source_instance_id,
                tombstone_revision=tombstone.tombstone_revision,
                accepted=validation.accepted,
                reason=(
                    validation.rejection_reason.value
                    if validation.rejection_reason is not None
                    else None
                ),
            )
        )
        # A rejected tombstone must not silently no-op from the caller's perspective (no removal,
        # no explanation) - a real finding from PR review.
        if not validation.accepted and validation.diagnostic is not None:
            tombstone_diagnostics.append(validation.diagnostic)

    # Snapshot every source's own emitted node/relation properties BEFORE the pre-merge pass below
    # touches anything - the pre-merge writes every source's nodes first (see its own comment), so
    # by the time a given source's own `_import_source_tx` ran, its own PRE-MERGE write had already
    # applied its new property values, making its no-op check's "before" snapshot indistinguishable
    # from "after" even for a genuine property-only change (a real bug found in PR review: this
    # made a title-only reimport through the real `import_all_sources` path silently skip the
    # revision fence). Captured once, for the union of every source's own node ids/relation keys.
    all_node_ids: set[str] = set()
    all_relation_keys: set[str] = set()
    for source_instance_id, source_outcome in run_result.source_outcomes.items():
        all_node_ids |= claim_planning.model_node_ids(
            source_outcome.outcome.model, source_instance_id=source_instance_id
        )
        all_relation_keys |= claim_planning.model_relation_keys(source_outcome.outcome.model)
    committed_nodes_before = writers.snapshot_node_props(tx, all_node_ids)
    committed_relations_before = writers.snapshot_relation_props(tx, all_relation_keys)

    # Pre-merge every source's nodes first so cross-source relation targets always resolve
    # regardless of processing order - unchanged in spirit from the PoC-era pre-merge pass, now
    # scoped per source instance instead of per service. This pass does NOT bump the revision fence
    # itself: MERGE here is idempotent, and the real "did anything semantically change" decision
    # (and the resulting conditional bump) happens once, per source, in `_import_source_tx` below.
    for source_instance_id, source_outcome in run_result.source_outcomes.items():
        writers.write_nodes(tx, source_instance_id, source_outcome.outcome.model)

    # Which absent sources this COMPLETE run removes is decided before any source is reconciled:
    # they take part in the run too (they will own nothing after it), so a claim a present source
    # drops and a removed source co-owned expires rather than surviving for an owner that is about
    # to leave. Removing a source never changes another's authorization, so deciding early is safe.
    removed_source_instance_ids: list[str] = []
    if run_result.inventory_status is InventoryStatus.COMPLETE:
        known_states = list(
            tx.run(
                READ_SOURCE_STATES_FOR_SCOPE_QUERY,
                discovery_scope_id=run_result.discovery_scope_id,
            )
        )
        for record in known_states:
            source_instance_id = record["source_instance_id"]
            if source_instance_id in run_result.source_outcomes:
                continue
            # `committed_discovery_scope_id` is `None` when this scope has no committed inventory
            # yet, which `known_states` does not rule out: `import_source` writes a scoped
            # `SourceState` without a `CurrentInventory`. `authorize_source_removal` then denies
            # enumeration-based removal; only an accepted tombstone can authorize it.
            decision = authorize_source_removal(
                tombstone_validation=tombstone_validations.get(source_instance_id),
                enumeration_status=run_result.inventory_status,
                enumeration_discovery_scope_id=run_result.discovery_scope_id,
                enumeration_scope_definition_digest=run_result.scope_definition_digest,
                committed_discovery_scope_id=committed_discovery_scope_id,
                committed_scope_definition_digest=record["scope_definition_digest"],
                source_absent_from_enumeration=True,
            )
            if decision.authorized:
                removed_source_instance_ids.append(source_instance_id)

    run_node_emitters: dict[str, set[str]] = {}
    run_relation_emitters: dict[str, set[str]] = {}
    for source_instance_id, source_outcome in run_result.source_outcomes.items():
        model = source_outcome.outcome.model
        for node_id in claim_planning.model_node_ids(model, source_instance_id=source_instance_id):
            run_node_emitters.setdefault(node_id, set()).add(source_instance_id)
        for key in claim_planning.model_relation_keys(model):
            run_relation_emitters.setdefault(key, set()).add(source_instance_id)

    per_source: dict[str, SourceImportStats] = {}
    for source_instance_id, source_outcome in run_result.source_outcomes.items():
        per_source[source_instance_id] = _import_source_tx(
            tx,
            source_instance_id=source_instance_id,
            locator=source_outcome.descriptor_locator,
            model=source_outcome.outcome.model,
            result=source_outcome.outcome.result,
            semantic_input_digest=source_outcome.outcome.semantic_input_digest,
            discovery_scope_id=run_result.discovery_scope_id,
            scope_definition_digest=run_result.scope_definition_digest,
            committed_nodes_before=committed_nodes_before,
            committed_relations_before=committed_relations_before,
            run_source_ids=frozenset(run_result.source_outcomes) | set(removed_source_instance_ids),
            run_node_emitters=run_node_emitters,
            run_relation_emitters=run_relation_emitters,
            capture_scope=(
                source_outcome.descriptor.capture_scope if source_outcome.descriptor else None
            ),
        )

    # Decided before any is removed, so a claim several removed sources shared expires for each.
    removal_stats: list[SourceImportStats] = []
    for source_instance_id in removed_source_instance_ids:
        removal_stats.append(
            _remove_source_tx(
                tx,
                source_instance_id=source_instance_id,
                removed_source_ids=frozenset(removed_source_instance_ids),
            )
        )

    new_event_id = compute_inventory_event_id(
        previous_event_id=persisted_inventory["inventory_event_id"],
        inventory_capture_id=run_result.inventory_snapshot.inventory_capture_id,
    )
    tx.run(
        WRITE_CURRENT_INVENTORY_QUERY,
        discovery_scope_id=run_result.discovery_scope_id,
        inventory_revision=run_result.inventory_snapshot.inventory_revision,
        inventory_capture_id=run_result.inventory_snapshot.inventory_capture_id,
        inventory_event_id=new_event_id,
        scope_definition_digest=run_result.scope_definition_digest,
    )

    return (
        per_source,
        tuple(removed_source_instance_ids),
        tuple(tombstone_diagnostics),
        tuple(tombstone_decisions),
        tuple(removal_stats),
    )


def _source_run_results(run_result: DiscoveryRunResult) -> tuple[SourceRunResult, ...]:
    """Every discovered source's own I1 §10 result, sorted by source instance id - taken from the
    discovery run itself, so it exists whether or not the run commits."""
    return tuple(
        _source_run_result(source_instance_id, run_outcome)
        for source_instance_id, run_outcome in sorted(run_result.source_outcomes.items())
    )


def _source_run_result(source_instance_id: str, run_outcome: SourceRunOutcome) -> SourceRunResult:
    descriptor = run_outcome.descriptor
    model = run_outcome.outcome.model
    return SourceRunResult(
        source_instance_id=source_instance_id,
        locator=run_outcome.descriptor_locator,
        result=run_outcome.outcome.result,
        diagnostics=tuple(run_outcome.outcome.diagnostics),
        source_kind=descriptor.source_kind.value if descriptor is not None else "",
        adapter_identity=(descriptor.adapter_identity or None) if descriptor is not None else None,
        mapping_rule_version=(
            (descriptor.mapping_rule_version or None) if descriptor is not None else None
        ),
        dialect_version=descriptor.document_dialect_version if descriptor is not None else None,
        semantic_input_digest=run_outcome.outcome.semantic_input_digest,
        service_ids=tuple(sorted({service.id for service in model.services})),
        emitted=EmittedCounts.of(model),
    )


def import_discovery_run(
    driver: neo4j.Driver,
    *,
    database: str,
    run_result: DiscoveryRunResult,
    expected_prior_inventory_revision: str | None | NotSupplied = NOT_SUPPLIED,
) -> ImportRunStats:
    """I2 Draft 0.2 §3 prerequisite slice, items 2/4: the source-neutral commit entry point - takes
    an already-computed `DiscoveryRunResult` (from `run_discovery` or any source-neutral discovery
    path) rather than constructing discovery itself, and does not branch on source kind.
    `import_all_sources` below is now a thin compatibility wrapper over this function for the
    filesystem source kind.

    Nothing is written to Neo4j unless the whole discovery run is COMPLETE (I1 spec §6 - a
    PARTIAL/FAILED run must preserve prior state, never a partial write), and pre-merge/
    reconciliation/removal for every source in the run share one transaction (see
    `_import_all_sources_tx`), so a failure partway through the run - including a stale
    `expected_prior_inventory_revision` - leaves nothing committed.
    """
    source_results = _source_run_results(run_result)
    if not run_result.commit_eligible:
        return ImportRunStats(
            inventory_status=run_result.inventory_status,
            committed=False,
            per_source={},
            removed_source_instance_ids=(),
            diagnostics=run_result.diagnostics,
            source_results=source_results,
            discovery_scope_id=run_result.discovery_scope_id,
            scope_definition_digest=run_result.scope_definition_digest,
        )

    with open_session(driver, database=database) as session:
        ensure_schema(session)
        try:
            (
                per_source,
                removed_source_instance_ids,
                tombstone_diagnostics,
                tombstone_decisions,
                removal_stats,
            ) = session.execute_write(
                _import_all_sources_tx,
                run_result=run_result,
                expected_prior_inventory_revision=expected_prior_inventory_revision,
            )
        except StalePredecessorError as exc:
            return ImportRunStats(
                inventory_status=run_result.inventory_status,
                committed=False,
                per_source={},
                removed_source_instance_ids=(),
                diagnostics=(
                    *run_result.diagnostics,
                    IngestionDiagnostic(
                        code=DiagnosticCode.STALE_INVENTORY_PREDECESSOR,
                        message=str(exc),
                    ),
                ),
                source_results=source_results,
                discovery_scope_id=run_result.discovery_scope_id,
                scope_definition_digest=run_result.scope_definition_digest,
            )

        # _import_all_sources_tx rejects a commit-eligible run without an inventory snapshot.
        assert run_result.inventory_snapshot is not None
        return ImportRunStats(
            inventory_status=run_result.inventory_status,
            committed=True,
            per_source=per_source,
            removed_source_instance_ids=removed_source_instance_ids,
            diagnostics=(*run_result.diagnostics, *tombstone_diagnostics),
            source_results=source_results,
            discovery_scope_id=run_result.discovery_scope_id,
            scope_definition_digest=run_result.scope_definition_digest,
            inventory_revision=run_result.inventory_snapshot.inventory_revision,
            tombstone_decisions=tombstone_decisions,
            removal_stats=removal_stats,
        )


def import_all_sources(
    driver: neo4j.Driver,
    *,
    database: str,
    source_config: FilesystemSourceConfig,
    migration_mappings: SharedIdentityMappingIndex | None = None,
    tombstones: Sequence[Tombstone] = (),
    expected_prior_inventory_revision: str | None | NotSupplied = NOT_SUPPLIED,
) -> ImportRunStats:
    """Thin compatibility wrapper over `run_filesystem_discovery` + `import_discovery_run` for the
    filesystem source kind - every existing caller/test keeps working unchanged."""
    run_result = run_filesystem_discovery(
        source_config, migration_mappings=migration_mappings, tombstones=tombstones
    )
    return import_discovery_run(
        driver,
        database=database,
        run_result=run_result,
        expected_prior_inventory_revision=expected_prior_inventory_revision,
    )


def import_kubernetes_source(
    driver: neo4j.Driver,
    *,
    database: str,
    source_config: KubernetesSourceConfig,
    migration_mappings: SharedIdentityMappingIndex | None = None,
    tombstones: Sequence[Tombstone] = (),
) -> ImportRunStats:
    """Thin wrapper over `run_kubernetes_discovery` + `import_discovery_run` for the Kubernetes
    source kind, mirroring `import_all_sources`'s exact shape (I2 Draft 0.2 slice 2b-i). Threads the
    envelope's own `completeness.expectedPriorInventoryRevision` (carried on `run_result` by
    `KubernetesSourceDiscoverer`) into the predecessor-check transaction, and layers the
    Kubernetes-specific `K8S_STALE_INVENTORY` diagnostic alongside the generic
    `STALE_INVENTORY_PREDECESSOR` one on a stale predecessor (I2 Draft 0.2 §4.2/§10, slice 2b-ii) -
    at this wrapper level, not inside `_import_all_sources_tx`, which stays source-kind-neutral.
    """
    run_result = run_kubernetes_discovery(
        source_config, migration_mappings=migration_mappings, tombstones=tombstones
    )
    stats = import_discovery_run(
        driver,
        database=database,
        run_result=run_result,
        expected_prior_inventory_revision=run_result.expected_prior_inventory_revision,
    )
    # STALE_INVENTORY_PREDECESSOR can only appear here when a real (non-NOT_SUPPLIED) expectation
    # was actually checked - i.e. only for a fully-accepted Kubernetes envelope - so this never
    # spuriously fires for a rejected source or bleeds into a filesystem source's own diagnostics.
    if any(d.code == DiagnosticCode.STALE_INVENTORY_PREDECESSOR for d in stats.diagnostics):
        # §10: "K8S_STALE_INVENTORY | REJECTED_CONFLICT; no commit." `committed=False` alone
        # satisfies "no commit" but not the REJECTED_CONFLICT classification itself -
        # import_discovery_run's stale-predecessor path returns per_source={} (the transaction
        # aborted before any write), so there is nothing to rewrite there. `run_result.
        # source_outcomes` still holds the pre-transaction (accepted-at-discovery-time) outcome for
        # exactly this reason: staleness is a commit-time-only check (§4.2), undetectable at
        # discovery time. Mirrors K8S_RESOURCE_CONFLICT's own precedent (`_rejected_conflict`
        # rewriting the affected source's own result) - reconstructed here, not inside the
        # transaction, since that is source-kind-neutral and must not classify a Kubernetes-
        # specific outcome.
        stale_per_source = {
            source_instance_id: SourceImportStats(
                source_instance_id=source_instance_id,
                locator=run_outcome.descriptor_locator,
                result=IngestionResult.REJECTED_CONFLICT,
                nodes_written=0,
                relations_written=0,
                nodes_expired=0,
                relations_expired=0,
                graph_revision_advanced=False,
            )
            for source_instance_id, run_outcome in run_result.source_outcomes.items()
        }
        stats = replace(
            stats,
            per_source=stale_per_source,
            source_results=tuple(
                replace(source_result, result=IngestionResult.REJECTED_CONFLICT)
                for source_result in stats.source_results
            ),
            diagnostics=(
                *stats.diagnostics,
                IngestionDiagnostic(
                    code=DiagnosticCode.K8S_STALE_INVENTORY,
                    message="stale or racing predecessor: expectedPriorInventoryRevision did not "
                    "match the currently committed inventory revision",
                ),
            ),
        )
    return stats
