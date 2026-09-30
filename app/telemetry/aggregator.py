import neo4j

from app.graph.importer import KNOWN_RELATION_TYPES
from app.graph.repository import open_session
from app.graph.revision_fence import bump_revision
from app.graph.schema import ensure_schema
from app.provenance.model import (
    ObservedEvidence,
    RuntimeIdentityObservation,
    ScopedObservedCall,
)
from app.settings import ScopedEvidenceConfig
from app.telemetry.model import (
    ObservationBatch,
    ObservedFactCandidate,
    stronger_correlation_mode,
)
from app.telemetry.scoped_evidence import merge_scoped_call, record_from_seed
from app.telemetry.scoped_ledger import ensure_cutover, finalize_unit, log_refusal_samples

_MERGE_STUB_NODE_QUERY = (
    "MERGE (n:{label} {{id: $id}}) "
    "ON CREATE SET n.name = $name, n.discovery_status = $discovery_status"
)

_READ_EVIDENCE_QUERY = (
    "MATCH (e:Evidence {id: $id}) "
    "RETURN e.id AS id, e.source_type AS source_type, e.source_file AS source_file, "
    "e.source_revision AS source_revision, e.evidence_type AS evidence_type, "
    "e.environment AS environment, e.bucket_start AS bucket_start, e.bucket_end AS bucket_end, "
    "e.first_seen AS first_seen, e.last_seen AS last_seen, "
    "e.observation_count AS observation_count, e.sample_trace_ids AS sample_trace_ids, "
    "e.service_version AS service_version, e.correlation_mode AS correlation_mode"
)

_MERGE_EVIDENCE_QUERY = "MERGE (e:Evidence {id: $id}) SET e += $props"

# Mirrors app/graph/importer.py's _MERGE_RELATION_TEMPLATE's evidence_ids dedup-append expression,
# but deliberately never touches r.owner_source_ids - that's declared-import-only reconciliation
# bookkeeping that must not apply to incremental runtime observation (spec §40: absence of
# observation is not evidence of absence, so an observed fact is never "expired" by a later batch
# not re-observing it).
_MERGE_FACT_RELATION_QUERY = (
    "MATCH (a {{id: $subject_id}}), (b {{id: $object_id}}) "
    "MERGE (a)-[r:{relation_type}]->(b) "
    "SET r.evidence_ids = reduce(acc = coalesce(r.evidence_ids, []), eid IN [$evidence_id] | "
    "CASE WHEN eid IN acc THEN acc ELSE acc + eid END)"
)

_DATETIME_FIELDS = ("bucket_start", "bucket_end", "first_seen", "last_seen")

# I3 §9.4/§23 slice 2 - a bare node, never :Evidence (see app.provenance.model.
# RuntimeIdentityObservation's docstring for why: no public reachability gate exists yet).
_READ_RUNTIME_IDENTITY_OBSERVATION_QUERY = (
    "MATCH (o:RuntimeIdentityObservation {id: $id}) "
    "RETURN o.id AS id, o.source_type AS source_type, o.source_file AS source_file, "
    "o.source_revision AS source_revision, o.evidence_type AS evidence_type, "
    "o.service_name AS service_name, o.service_namespace AS service_namespace, "
    "o.service_version AS service_version, o.environment AS environment, "
    "o.k8s_pod_uid AS k8s_pod_uid, o.k8s_pod_name AS k8s_pod_name, "
    "o.k8s_namespace_name AS k8s_namespace_name, o.k8s_cluster_uid AS k8s_cluster_uid, "
    "o.k8s_deployment_name AS k8s_deployment_name, "
    "o.k8s_statefulset_name AS k8s_statefulset_name, "
    "o.k8s_daemonset_name AS k8s_daemonset_name, "
    "o.first_seen AS first_seen, o.last_seen AS last_seen, "
    "o.observation_count AS observation_count, "
    "o.conflicting_consistency_attributes AS conflicting_consistency_attributes, "
    "o.normalization_rule_id AS normalization_rule_id, "
    "o.normalization_rule_version AS normalization_rule_version"
)

_MERGE_RUNTIME_IDENTITY_OBSERVATION_QUERY = (
    "MERGE (o:RuntimeIdentityObservation {id: $id}) SET o += $props"
)

_RUNTIME_IDENTITY_OBSERVATION_DATETIME_FIELDS = ("first_seen", "last_seen")

# v0.6.0 I2.2b (decision record D1, D12.4) - the isolated caller-Pod-scoped v2 record. A bare node
# under its own label: never :Evidence, no relationships, no owner_source_ids. The first statement
# creates the node if needed AND takes its exclusive write lock (a property write, even of the value
# it already holds, locks the node until commit); only then is the committed record read and merged.
# Lock-before-read is what keeps two concurrent POSTs from both reading the old count and one
# overwriting the other - the lost update the v1 read-then-merge above can suffer.
_LOCK_SCOPED_OBSERVED_CALL_QUERY = "MERGE (v:ScopedObservedCallV2 {id: $id}) SET v.id = $id"
_READ_SCOPED_OBSERVED_CALL_QUERY = (
    "MATCH (v:ScopedObservedCallV2 {id: $id}) "
    "RETURN v.id AS id, v.contract_version AS contract_version, v.source_type AS source_type, "
    "v.evidence_type AS evidence_type, v.relation_type AS relation_type, "
    "v.environment AS environment, v.bucket_utc_day AS bucket_utc_day, "
    "v.subject_id AS subject_id, v.object_id AS object_id, "
    "v.caller_cluster_uid AS caller_cluster_uid, v.caller_pod_uid AS caller_pod_uid, "
    "v.first_seen AS first_seen, v.last_seen AS last_seen, "
    "v.observation_count AS observation_count, v.correlation_mode AS correlation_mode, "
    "v.sample_trace_ids AS sample_trace_ids, "
    "v.k8s_namespace_name AS k8s_namespace_name, v.k8s_pod_name AS k8s_pod_name, "
    "v.k8s_deployment_name AS k8s_deployment_name, "
    "v.k8s_statefulset_name AS k8s_statefulset_name, "
    "v.k8s_daemonset_name AS k8s_daemonset_name, "
    "v.conflicting_consistency_attributes AS conflicting_consistency_attributes, "
    "v.key_rule_id AS key_rule_id, v.key_rule_version AS key_rule_version, "
    "v.normalization_rule_id AS normalization_rule_id, "
    "v.normalization_rule_version AS normalization_rule_version"
)
_WRITE_SCOPED_OBSERVED_CALL_QUERY = "MATCH (v:ScopedObservedCallV2 {id: $id}) SET v += $props"
_SCOPED_OBSERVED_CALL_DATETIME_FIELDS = ("first_seen", "last_seen")


def _cap_trace_ids(existing: list[str], new: list[str], limit: int = 5) -> list[str]:
    combined = list(existing)
    for trace_id in new:
        if trace_id not in combined:
            combined.append(trace_id)
    return combined[:limit]


def merge_evidence(existing: ObservedEvidence | None, seed: ObservedEvidence) -> ObservedEvidence:
    """Merges a single-observation seed into the existing persisted evidence bucket, if any (spec
    §36). bucket_start/bucket_end are left untouched (taken from the seed) - observed_evidence_id()
    is deterministic per (fact, day, environment), so existing and seed always share the same day
    boundaries by construction whenever both are present."""
    if existing is None:
        return seed
    return seed.model_copy(
        update={
            "first_seen": min(existing.first_seen, seed.first_seen),
            "last_seen": max(existing.last_seen, seed.last_seen),
            "observation_count": existing.observation_count + seed.observation_count,
            "sample_trace_ids": _cap_trace_ids(existing.sample_trace_ids, seed.sample_trace_ids),
            "correlation_mode": stronger_correlation_mode(
                existing.correlation_mode, seed.correlation_mode
            ),
        }
    )


# I3 §9.4/§9.6 - service_namespace is excluded: it is part of runtime_identity_observation_id()'s
# own bucket identity, so it cannot differ between existing and seed within one bucket.
_CONSISTENCY_ATTRIBUTE_FIELDS = (
    "service_version",
    "k8s_pod_name",
    "k8s_namespace_name",
    "k8s_cluster_uid",
    "k8s_deployment_name",
    "k8s_statefulset_name",
    "k8s_daemonset_name",
)


def merge_runtime_identity_observation(
    existing: RuntimeIdentityObservation | None, seed: RuntimeIdentityObservation
) -> RuntimeIdentityObservation:
    """Merges a single-observation seed into the existing persisted runtime identity observation,
    if any (I3 spec §9.4/§9.6, mirrors merge_evidence's own bucket-merge shape).

    Never silently overwrites disagreeing consistency-attribute evidence: §9.6 requires a directly
    contradictory attribute to surface as CONFLICT downstream, not be lost at persistence time. For
    each of _CONSISTENCY_ATTRIBUTE_FIELDS: a missing value on either side never erases a known value
    from the other side (a missing optional consistency attribute "is not a limitation by itself",
    §9.6); two disagreeing non-null values null the merged field and add the field's name to
    conflicting_consistency_attributes (sorted, deduplicated, monotonic - once flagged for a bucket,
    an attribute stays flagged for that bucket even if a later value happens to agree with whatever
    is currently reconciled)."""
    if existing is None:
        return seed

    conflicts = set(existing.conflicting_consistency_attributes)
    reconciled = {}
    for field in _CONSISTENCY_ATTRIBUTE_FIELDS:
        existing_value = getattr(existing, field)
        seed_value = getattr(seed, field)
        if existing_value is not None and seed_value is not None and existing_value != seed_value:
            conflicts.add(field)
            reconciled[field] = None
        else:
            reconciled[field] = existing_value if existing_value is not None else seed_value

    return seed.model_copy(
        update={
            **reconciled,
            "first_seen": min(existing.first_seen, seed.first_seen),
            "last_seen": max(existing.last_seen, seed.last_seen),
            "observation_count": existing.observation_count + seed.observation_count,
            "conflicting_consistency_attributes": sorted(conflicts),
        }
    )


def _read_existing_runtime_identity_observation(
    tx: neo4j.ManagedTransaction, observation_id: str
) -> RuntimeIdentityObservation | None:
    record = tx.run(_READ_RUNTIME_IDENTITY_OBSERVATION_QUERY, id=observation_id).single()
    if record is None:
        return None
    data = dict(record)
    for field in _RUNTIME_IDENTITY_OBSERVATION_DATETIME_FIELDS:
        # Same neo4j.time.DateTime -> datetime.datetime conversion as _read_existing_evidence.
        data[field] = data[field].to_native()
    return RuntimeIdentityObservation(**data)


def _persist_runtime_identity_observation(
    tx: neo4j.ManagedTransaction, observation: RuntimeIdentityObservation
) -> None:
    existing = _read_existing_runtime_identity_observation(tx, observation.id)
    merged = merge_runtime_identity_observation(existing, observation)
    tx.run(
        _MERGE_RUNTIME_IDENTITY_OBSERVATION_QUERY,
        id=merged.id,
        props=merged.model_dump(exclude={"id"}),
    )


def _read_existing_evidence(
    tx: neo4j.ManagedTransaction, evidence_id: str
) -> ObservedEvidence | None:
    record = tx.run(_READ_EVIDENCE_QUERY, id=evidence_id).single()
    if record is None:
        return None
    data = dict(record)
    for field in _DATETIME_FIELDS:
        # Neo4j returns temporal properties as neo4j.time.DateTime, not datetime.datetime - Pydantic
        # rejects it outright without this conversion. Read-direction only; writing native
        # datetime.datetime query params needs no conversion.
        data[field] = data[field].to_native()
    return ObservedEvidence(**data)


def _persist_fact(tx: neo4j.ManagedTransaction, fact: ObservedFactCandidate) -> None:
    if fact.relation_type not in KNOWN_RELATION_TYPES:
        raise ValueError(f"Unknown relation type: {fact.relation_type}")

    existing = _read_existing_evidence(tx, fact.evidence.id)
    merged = merge_evidence(existing, fact.evidence)
    tx.run(_MERGE_EVIDENCE_QUERY, id=merged.id, props=merged.model_dump(exclude={"id"}))

    query = _MERGE_FACT_RELATION_QUERY.format(relation_type=fact.relation_type)
    # Cypher can't parametrize a relationship type; the check at the top of this function rejects
    # any type outside KNOWN_RELATION_TYPES, so the formatted query is not injectable.
    tx.run(
        query,  # pyright: ignore[reportArgumentType]
        subject_id=fact.subject_id,
        object_id=fact.object_id,
        evidence_id=merged.id,
    )


def _read_existing_scoped_observed_call(
    tx: neo4j.ManagedTransaction, record_id: str
) -> ScopedObservedCall | None:
    record = tx.run(_READ_SCOPED_OBSERVED_CALL_QUERY, id=record_id).single()
    if record is None or record["first_seen"] is None:
        # No node, or the bare node this same transaction just created to take the lock.
        return None
    data = dict(record)
    for field in _SCOPED_OBSERVED_CALL_DATETIME_FIELDS:
        data[field] = data[field].to_native()
    return ScopedObservedCall(**data)


def _persist_scoped_seed(tx: neo4j.ManagedTransaction, seed_record: ScopedObservedCall) -> None:
    """Folds one interaction's v2 record into the committed record for its ID, inside the unit's
    transaction: lock the node, read it, merge (order-independent), write."""
    tx.run(_LOCK_SCOPED_OBSERVED_CALL_QUERY, id=seed_record.id)
    existing = _read_existing_scoped_observed_call(tx, seed_record.id)
    merged = merge_scoped_call(existing, seed_record)
    tx.run(_WRITE_SCOPED_OBSERVED_CALL_QUERY, id=merged.id, props=merged.model_dump(exclude={"id"}))


def _persist_batch_tx(
    tx: neo4j.ManagedTransaction, batch: ObservationBatch, scoped_stream_id: str | None = None
) -> None:
    """One unit. `scoped_stream_id` is the configured scoped-evidence stream when the feature is
    enabled, else None (nothing v2 is read or written)."""
    # v0.6.0 I2.2c: the cutover must record the v1 CALLS buckets that existed BEFORE this unit, so
    # it runs first. It is a no-op after the first enabled unit.
    cutover_written = scoped_stream_id is not None and ensure_cutover(tx, scoped_stream_id)

    for entity in batch.entities:
        query = _MERGE_STUB_NODE_QUERY.format(label=entity.label)
        tx.run(query, id=entity.id, name=entity.name, discovery_status="OBSERVED_ONLY")

    # Sequential, not a bulk UNWIND: this is what correctly handles the same fact appearing more
    # than once within one OTLP batch - each read sees the previous iteration's already-written
    # merge within this same transaction. A later "optimize to UNWIND" edit would silently break
    # within-batch accumulation, since UNWIND rows don't get Python-level merge_evidence semantics.
    for fact in batch.facts:
        _persist_fact(tx, fact)

    # Same sequential-not-UNWIND reasoning as the facts loop above: a batch producing more than one
    # observation for the same (environment, day, service_name, namespace, pod_uid) must have each
    # one merge against the previous iteration's already-written state within this transaction.
    for observation in batch.runtime_identity_observations:
        _persist_runtime_identity_observation(tx, observation)

    if scoped_stream_id is not None:
        # v0.6.0 I2.2b: the eligible v2 seeds of this unit, in the SAME transaction as the v1 facts
        # above, so a v2 failure rolls the whole unit back rather than committing half a pair.
        # Sorted by id so concurrent units always lock nodes in one order (no lock-order
        # deadlocks); the merge itself is order-independent, so the order cannot change a result.
        seed_records = [
            record_from_seed(fact.scoped_seed) for fact in batch.facts if fact.scoped_seed
        ]
        for seed_record in sorted(seed_records, key=lambda record: record.id):
            _persist_scoped_seed(tx, seed_record)

    revision = bump_revision(tx)

    if scoped_stream_id is not None:
        if revision is None:
            # ensure_schema created the singleton before this transaction; only corrupted state gets
            # here, and the ledger, membership and counters must name the revision they commit.
            raise RuntimeError("cannot record scoped-evidence provenance without a revision")
        finalize_unit(
            tx,
            stream_id=scoped_stream_id,
            batch=batch,
            revision=revision,
            cutover_written=cutover_written,
        )


def persist_observation_batch(
    driver: neo4j.Driver,
    database: str,
    batch: ObservationBatch,
    *,
    scoped: ScopedEvidenceConfig | None = None,
) -> None:
    """Persists an ObservationBatch's entities/facts to Neo4j (spec §36) - the first H4 write path.
    UnresolvedObservations are never persisted: purely diagnostic, no graph-model place for them.

    The whole batch is one unit: one `execute_write`, one revision bump. With `scoped` enabled
    (v0.6.0 I2.2b) each fact's eligible v2 seed is also persisted in that same transaction; with it
    off or absent (the default) not a single v2 read or write happens and behaviour is unchanged."""
    stream_id = scoped.stream_id if scoped is not None and scoped.enabled else None
    with open_session(driver, database=database) as session:
        ensure_schema(session)
        session.execute_write(_persist_batch_tx, batch, stream_id)
    if stream_id is not None:
        # Only after the unit committed, so a transaction retry can never log a refusal twice.
        log_refusal_samples(stream_id, batch.scoped_refusals)
