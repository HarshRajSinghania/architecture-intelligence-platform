"""Operational provenance for scoped v2 evidence (v0.6.0 I2.2c; I2 decision record D7, D8, D12).

Three kinds of bare, relationship-free internal node, all written inside the same per-POST
transaction as the unit they describe (so a rolled-back unit leaves none of them):

- `ScopedEvidenceCutover` - one per graph. Written by the first unit processed with scoped evidence
  enabled: the stream it belongs to, and the count and digest of the v1 CALLS buckets that already
  existed before that unit.
- `ScopedEvidenceLegacyBucket` - one per such pre-enablement bucket: the durable membership that
  survives restarts. A later enabled unit that contributes to a member marks it `mixed`.
- `ScopedEvidenceTransitionCounter` - exact per-(stream, environment, UTC day, category, primary
  cause) interaction counts. Never truncated.

None of them is architecture evidence, none enters the snapshot or any public read, and none is
reachable through the NL path. They describe *when scoped evidence began and how many interactions it
accepted or refused*; they never assert that any v1 bucket is wholly legacy (that is derived at read
time, and unknown whenever the membership cannot be proved).
"""

import hashlib
import json
import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import neo4j

from app.canonical import ids
from app.graph.revision_fence import lock_revision, read_revision
from app.telemetry.model import ObservationBatch
from app.telemetry.scoped_attribution import ScopedIngressRefusal, primary_cause

logger = logging.getLogger(__name__)

TRANSITION_REPORT_SCHEMA = "aip-scoped-evidence-transition-report/1"
CATEGORY_WRITTEN = "SCOPED_V2_WRITTEN"
CATEGORY_REFUSED = "SCOPED_V2_REFUSED"
CUTOVER_ID = "graph"
# D7: at most this many refusal samples are logged per primary cause per unit; the rest are counted.
SAMPLES_PER_REASON = 20

_V1_ID_PREFIX = "evidence:otel:"

_CUTOVER_EXISTS_QUERY = "MATCH (c:ScopedEvidenceCutover {id: $id}) RETURN count(c) AS c"
# The distinct v1 OTel evidence IDs referenced by CALLS relations. v1 evidence nodes do not record
# their relation type, so the relation is the only place a CALLS bucket is identifiable (D12.2). A
# v2 ID can never be here (isolation), and is excluded regardless.
_PRE_ENABLEMENT_BUCKETS_QUERY = (
    "MATCH ()-[r:CALLS]->() UNWIND coalesce(r.evidence_ids, []) AS eid "
    "WITH DISTINCT eid WHERE eid STARTS WITH $v1_prefix AND NOT eid STARTS WITH $v2_prefix "
    "RETURN eid AS id ORDER BY id"
)
_WRITE_CUTOVER_QUERY = (
    "MERGE (c:ScopedEvidenceCutover {id: $id}) "
    "ON CREATE SET c.stream_id = $stream_id, "
    "c.pre_enablement_v1_bucket_count = $count, c.pre_enablement_v1_bucket_digest = $digest"
)
_WRITE_MEMBERSHIP_QUERY = (
    "UNWIND $ids AS bucket_id MERGE (b:ScopedEvidenceLegacyBucket {id: bucket_id})"
)
_SET_CUTOVER_REVISION_QUERY = (
    "MATCH (c:ScopedEvidenceCutover {id: $id}) SET c.enabled_at_revision = $revision"
)
_SET_MEMBERSHIP_REVISION_QUERY = (
    "MATCH (b:ScopedEvidenceLegacyBucket) WHERE b.cutover_revision IS NULL "
    "SET b.cutover_revision = $revision"
)
_MARK_MIXED_QUERY = (
    "MATCH (b:ScopedEvidenceLegacyBucket) "
    "WHERE b.id IN $ids AND b.mixed_at_revision IS NULL SET b.mixed_at_revision = $revision"
)
_INCREMENT_COUNTER_QUERY = (
    "MERGE (c:ScopedEvidenceTransitionCounter {id: $id}) "
    "ON CREATE SET c.stream_id = $stream_id, c.environment = $environment, c.utc_day = $utc_day, "
    "c.category = $category, c.primary_reason = $primary_reason, c.count = 0 "
    "SET c.count = c.count + $delta, c.last_revision = $revision"
)


def ensure_cutover(tx: neo4j.ManagedTransaction, stream_id: str) -> bool:
    """Writes the cutover ledger and the durable legacy membership if this is the first unit ever
    processed with scoped evidence enabled; returns True only for that unit.

    Called BEFORE the unit's own v1 facts are persisted, so the recorded buckets are exactly those
    that existed before it. Double-checked (D12.5): an unlocked existence check, then the revision
    singleton's write lock, then the check again - so two racing first units write one ledger, the
    second blocking until the first commits and then finding it.
    """
    if _cutover_exists(tx):
        return False
    lock_revision(tx)
    if _cutover_exists(tx):
        return False
    bucket_ids = [
        record["id"]
        for record in tx.run(
            _PRE_ENABLEMENT_BUCKETS_QUERY,
            v1_prefix=_V1_ID_PREFIX,
            v2_prefix=ids.SCOPED_CALL_V2_ID_PREFIX,
        )
    ]
    tx.run(
        _WRITE_CUTOVER_QUERY,
        id=CUTOVER_ID,
        stream_id=stream_id,
        count=len(bucket_ids),
        digest=ids.legacy_bucket_digest(bucket_ids),
    )
    if bucket_ids:
        tx.run(_WRITE_MEMBERSHIP_QUERY, ids=bucket_ids)
    return True


def _cutover_exists(tx: neo4j.ManagedTransaction) -> bool:
    record = tx.run(_CUTOVER_EXISTS_QUERY, id=CUTOVER_ID).single()
    return record is not None and record["c"] > 0


def counter_id(
    stream_id: str, environment: str | None, utc_day: str, category: str, primary_reason: str | None
) -> str:
    key = json.dumps(
        [stream_id, environment, utc_day, category, primary_reason],
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return f"scoped-evidence-counter:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"


def _counter_deltas(
    batch: ObservationBatch,
) -> Counter[tuple[str | None, str, str, str | None]]:
    """Interaction counts for this unit: one per accepted seed, one per refusal under its primary
    cause - counted per interaction, so several seeds merging into one record still count each."""
    deltas: Counter[tuple[str | None, str, str, str | None]] = Counter()
    for fact in batch.facts:
        if fact.scoped_seed is not None:
            seed = fact.scoped_seed
            deltas[(seed.environment, seed.bucket_utc_day, CATEGORY_WRITTEN, None)] += 1
    for refusal in batch.scoped_refusals:
        key = (
            refusal.environment,
            refusal.bucket_utc_day,
            CATEGORY_REFUSED,
            primary_cause(refusal),
        )
        deltas[key] += 1
    return deltas


def _touched_v1_call_buckets(batch: ObservationBatch) -> list[str]:
    return sorted(
        {
            fact.evidence.id
            for fact in batch.facts
            if fact.relation_type == "CALLS"
            and fact.evidence.id.startswith(_V1_ID_PREFIX)
            and not fact.evidence.id.startswith(ids.SCOPED_CALL_V2_ID_PREFIX)
        }
    )


def finalize_unit(
    tx: neo4j.ManagedTransaction,
    *,
    stream_id: str,
    batch: ObservationBatch,
    revision: int,
    cutover_written: bool,
) -> None:
    """Runs after the unit's revision bump, so `revision` is the one this unit commits (D12.3)."""
    if cutover_written:
        tx.run(_SET_CUTOVER_REVISION_QUERY, id=CUTOVER_ID, revision=revision)
        tx.run(_SET_MEMBERSHIP_REVISION_QUERY, revision=revision)

    touched = _touched_v1_call_buckets(batch)
    if touched:
        # Any enabled unit's v1 CALLS contribution - written to v2 or refused - ends "legacy-only".
        tx.run(_MARK_MIXED_QUERY, ids=touched, revision=revision)

    deltas = _counter_deltas(batch)
    for (environment, utc_day, category, primary_reason), delta in sorted(
        deltas.items(), key=lambda item: counter_id(stream_id, item[0][0], *item[0][1:])
    ):
        tx.run(
            _INCREMENT_COUNTER_QUERY,
            id=counter_id(stream_id, environment, utc_day, category, primary_reason),
            stream_id=stream_id,
            environment=environment,
            utc_day=utc_day,
            category=category,
            primary_reason=primary_reason,
            delta=delta,
            revision=revision,
        )


def log_refusal_samples(stream_id: str, refusals: list[ScopedIngressRefusal]) -> None:
    """Bounded, sanitized operational samples of ingestion refusals (D7). Called only after the
    unit committed, so a transaction retry can never log the same refusals twice. Carries the
    stream, the trace ID and reason codes only - never an attribute value - at most
    `SAMPLES_PER_REASON` per primary cause, plus one overflow line with the suppressed count."""
    logged: Counter[str] = Counter()
    suppressed: Counter[str] = Counter()
    for refusal in refusals:
        cause = primary_cause(refusal)
        if logged[cause] < SAMPLES_PER_REASON:
            logged[cause] += 1
            logger.info(
                "scoped-evidence refusal stream=%s primary_reason=%s trace_id=%s reasons=%s",
                stream_id,
                cause,
                refusal.trace_id,
                ",".join(refusal.reasons),
            )
        else:
            suppressed[cause] += 1
    for cause in sorted(suppressed):
        logger.info(
            "scoped-evidence refusal samples suppressed stream=%s primary_reason=%s suppressed=%d",
            stream_id,
            cause,
            suppressed[cause],
        )


# --- the operational transition report ---------------------------------------------------------

_READ_CUTOVER_QUERY = (
    "MATCH (c:ScopedEvidenceCutover {id: $id}) "
    "RETURN c.stream_id AS stream_id, c.enabled_at_revision AS enabled_at_revision, "
    "c.pre_enablement_v1_bucket_count AS count, c.pre_enablement_v1_bucket_digest AS digest"
)
_READ_MEMBERSHIP_QUERY = (
    "MATCH (b:ScopedEvidenceLegacyBucket) "
    "RETURN b.id AS id, b.mixed_at_revision AS mixed_at_revision ORDER BY id"
)
_READ_COUNTERS_QUERY = (
    "MATCH (c:ScopedEvidenceTransitionCounter {stream_id: $stream_id}) "
    "RETURN c.environment AS environment, c.utc_day AS utc_day, c.category AS category, "
    "c.primary_reason AS primary_reason, c.count AS count, c.last_revision AS last_revision"
)

UnknownReason = Literal["NO_LEDGER", "STREAM_ID_MISMATCH", "MEMBERSHIP_MISMATCH"]


@dataclass(frozen=True)
class CounterRow:
    """Exact interaction count for one (environment, UTC day) and, for refusals, primary cause."""

    environment: str | None
    utc_day: str
    primary_reason: str | None
    count: int
    last_revision: int


@dataclass(frozen=True)
class LegacyHistory:
    """What can be proved about v1 CALLS buckets that predate scoped evidence. `known` is False
    whenever the membership cannot be tied to this stream's cutover ledger - then no bucket is
    called legacy, mixed or anything else: the answer is `unknown`, never legacy-by-absence."""

    known: bool
    unknown_reason: UnknownReason | None
    enabled_at_revision: int | None
    legacy_unscoped_buckets: int | None
    mixed_buckets: int | None


@dataclass(frozen=True)
class TransitionReport:
    """`aip-scoped-evidence-transition-report/1` (I1 v2 contract §6, decision record D7/D8): an
    operational artifact, never architecture evidence and never a snapshot input. Count units:
    `legacy` counts v1 *buckets*; the two scoped categories count *interactions*."""

    schema: str
    stream_id: str
    as_of_revision: int
    legacy: LegacyHistory
    scoped_v2_written: tuple[CounterRow, ...]
    scoped_v2_refused: tuple[CounterRow, ...]


class TransitionReportUnstable(RuntimeError):
    """The graph kept changing while the report was read, so no consistent as-of revision exists.
    Fails closed, like `app.architecture_intelligence.repository.SnapshotUnstable`."""


def read_transition_report(
    session: neo4j.Session,
    stream_id: str,
    *,
    read_revision_fn: Callable[[], int] | None = None,
    max_attempts: int = 3,
) -> TransitionReport:
    """Builds the report for one stream from the graph alone (so it survives a restart). The
    counters are exact for the stream; the legacy classification is derived, and unknown whenever
    the cutover ledger is absent, belongs to another stream, or no longer matches the membership.

    The ledger, membership and counters are read by separate read-committed queries, so a unit
    could commit between them. The read therefore follows the stable-read rule of the snapshot
    reader: read the revision, read everything, read the revision again, accept only if the two
    match (every unit commits together with its own bump), otherwise discard and retry - and fail
    closed after `max_attempts`. That is what makes `as_of_revision` true of every figure reported.
    `read_revision_fn` exists so the race can be tested deterministically.
    """
    revision_of = read_revision_fn or (lambda: read_revision(session))
    for _ in range(max_attempts):
        revision_before = revision_of()
        report = _read_report_once(session, stream_id, revision_before)
        if revision_of() == revision_before:
            return report
    raise TransitionReportUnstable(f"no consistent report after {max_attempts} attempts")


def _read_report_once(
    session: neo4j.Session, stream_id: str, as_of_revision: int
) -> TransitionReport:
    ledger = session.run(_READ_CUTOVER_QUERY, id=CUTOVER_ID).single()
    membership = [(r["id"], r["mixed_at_revision"]) for r in session.run(_READ_MEMBERSHIP_QUERY)]

    legacy = _classify_legacy(ledger, membership, stream_id)

    rows: dict[str, list[CounterRow]] = {CATEGORY_WRITTEN: [], CATEGORY_REFUSED: []}
    for record in session.run(_READ_COUNTERS_QUERY, stream_id=stream_id):
        rows[record["category"]].append(
            CounterRow(
                environment=record["environment"],
                utc_day=record["utc_day"],
                primary_reason=record["primary_reason"],
                count=record["count"],
                last_revision=record["last_revision"],
            )
        )

    def ordered(items: list[CounterRow]) -> tuple[CounterRow, ...]:
        return tuple(
            sorted(items, key=lambda r: (r.utc_day, r.environment or "", r.primary_reason or ""))
        )

    return TransitionReport(
        schema=TRANSITION_REPORT_SCHEMA,
        stream_id=stream_id,
        as_of_revision=as_of_revision,
        legacy=legacy,
        scoped_v2_written=ordered(rows[CATEGORY_WRITTEN]),
        scoped_v2_refused=ordered(rows[CATEGORY_REFUSED]),
    )


def _classify_legacy(
    ledger: neo4j.Record | None, membership: list[tuple[str, int | None]], stream_id: str
) -> LegacyHistory:
    def unknown(reason: UnknownReason, enabled_at: int | None = None) -> LegacyHistory:
        return LegacyHistory(False, reason, enabled_at, None, None)

    if ledger is None:
        return unknown("NO_LEDGER")
    enabled_at = ledger["enabled_at_revision"]
    if ledger["stream_id"] != stream_id:
        return unknown("STREAM_ID_MISMATCH", enabled_at)
    member_ids = [bucket_id for bucket_id, _ in membership]
    if (
        len(member_ids) != ledger["count"]
        or ids.legacy_bucket_digest(member_ids) != ledger["digest"]
    ):
        return unknown("MEMBERSHIP_MISMATCH", enabled_at)
    mixed = sum(1 for _, mixed_at in membership if mixed_at is not None)
    return LegacyHistory(True, None, enabled_at, len(membership) - mixed, mixed)
