"""Pure record construction and merge for the caller-Pod-scoped v2 evidence (v0.6.0 I2.2a; I1 v2
contract §§1-4, I2 decision record D1).

A `ScopedCallSeed` (one accepted interaction whose original CLIENT passed the ingestion guards)
becomes a one-observation `ScopedObservedCall`; seeds for the same v2 ID are folded together by
`merge_scoped_call`. The fold is **order-independent**: any permutation of the same seeds, and any
grouping of them into merges, yields the identical record - so a clean replay, a different POST
split and a concurrent interleaving all agree. That is what separates it from the v0.5 runtime
identity merge, which refills a conflicted field from later seeds and so depends on order.

Nothing here touches Neo4j; persistence is `app.telemetry.aggregator`'s job.
"""

from app.canonical import ids
from app.provenance.model import ScopedObservedCall
from app.telemetry.model import stronger_correlation_mode
from app.telemetry.scoped_attribution import ScopedCallSeed

SAMPLE_TRACE_ID_LIMIT = 5

# The optional consistency names merged with the absorbing-conflict rule (v2 contract §3).
CONSISTENCY_FIELDS = (
    "k8s_namespace_name",
    "k8s_pod_name",
    "k8s_deployment_name",
    "k8s_statefulset_name",
    "k8s_daemonset_name",
)


def record_from_seed(seed: ScopedCallSeed) -> ScopedObservedCall:
    """The one-observation record for one interaction. `first_seen` and `last_seen` are the accepted
    fact timestamp (matrix §12.6), never the CLIENT's own end time."""
    return ScopedObservedCall(
        id=ids.scoped_observed_call_v2_id(
            environment=seed.environment,
            bucket_utc_day=seed.bucket_utc_day,
            subject_id=seed.subject_id,
            object_id=seed.object_id,
            caller_cluster_uid=seed.caller_cluster_uid,
            caller_pod_uid=seed.caller_pod_uid,
        ),
        environment=seed.environment,
        bucket_utc_day=seed.bucket_utc_day,
        subject_id=seed.subject_id,
        object_id=seed.object_id,
        caller_cluster_uid=seed.caller_cluster_uid,
        caller_pod_uid=seed.caller_pod_uid,
        first_seen=seed.fact_timestamp,
        last_seen=seed.fact_timestamp,
        observation_count=1,
        correlation_mode=seed.correlation_mode,
        sample_trace_ids=[seed.trace_id],
        k8s_namespace_name=seed.k8s_namespace_name,
        k8s_pod_name=seed.k8s_pod_name,
        k8s_deployment_name=seed.k8s_deployment_name,
        k8s_statefulset_name=seed.k8s_statefulset_name,
        k8s_daemonset_name=seed.k8s_daemonset_name,
        normalization_rule_id=seed.normalization_rule_id,
        normalization_rule_version=seed.normalization_rule_version,
    )


def merge_scoped_call(
    existing: ScopedObservedCall | None, seed: ScopedObservedCall
) -> ScopedObservedCall:
    """Folds one seed record into the existing record for the same v2 ID (`None` on first sight).

    - `first_seen` / `last_seen`: min / max. `observation_count`: sum. `correlation_mode`: the
      stronger one (`CLIENT_SERVER` over `CLIENT_ONLY`, as v1 ranks them).
    - `sample_trace_ids`: the distinct union, sorted, truncated to the first five - a prefix of a
      sorted set, so it does not depend on arrival order (v1 keeps arrival order, which does).
    - Optional consistency names, per field, an **absorbing conflict**: (1) once flagged the field
      stays None and stays flagged whatever a later seed carries; (2) otherwise a missing value
      never erases a known one; (3) two different known values set it to None and flag it. The
      final value and flag are therefore a function of the *set* of values seen.
    """
    if existing is None:
        return seed
    if existing.id != seed.id:
        raise ValueError("cannot merge scoped records with different ids")

    conflicts = set(existing.conflicting_consistency_attributes) | set(
        seed.conflicting_consistency_attributes
    )
    merged_names: dict[str, str | None] = {}
    for field in CONSISTENCY_FIELDS:
        old, new = getattr(existing, field), getattr(seed, field)
        if field in conflicts:
            merged_names[field] = None
        elif old is not None and new is not None and old != new:
            conflicts.add(field)
            merged_names[field] = None
        else:
            merged_names[field] = old if old is not None else new

    correlation_mode = stronger_correlation_mode(existing.correlation_mode, seed.correlation_mode)
    assert correlation_mode is not None
    return existing.model_copy(
        update={
            **merged_names,
            "first_seen": min(existing.first_seen, seed.first_seen),
            "last_seen": max(existing.last_seen, seed.last_seen),
            "observation_count": existing.observation_count + seed.observation_count,
            "correlation_mode": correlation_mode,
            "sample_trace_ids": sorted(set(existing.sample_trace_ids) | set(seed.sample_trace_ids))[
                :SAMPLE_TRACE_ID_LIMIT
            ],
            "conflicting_consistency_attributes": sorted(conflicts),
        }
    )
