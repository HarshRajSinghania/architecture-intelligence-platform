"""Dedicated reader for the isolated caller-Pod-scoped v2 records (v0.6.0 I2.2a; I2 decision record
D1 and D3).

Only this module reads `:ScopedObservedCallV2`. The public evidence reads, the snapshot state and the
NL query path never see the label (I2.2b proves it). It filters by caller Service and, optionally,
one canonical Operation - and by nothing else: a request's environment, UTC day, cluster or Workload
are applicability checks (I1 §10.1 phases 3-4), not filters, so a wrong-environment or wrong-day
record must still be returned and then judged (I1 L10b, L17d).
"""

from dataclasses import dataclass

import neo4j

from app.provenance.model import ScopedObservedCall

# D3: fixed page size; an explicit truncation flag is returned whenever a scan stops early.
DEFAULT_PAGE_SIZE = 500

_READ_QUERY = (
    "MATCH (v:ScopedObservedCallV2) "
    "WHERE v.subject_id = $subject_id "
    "AND ($object_id IS NULL OR v.object_id = $object_id) "
    "AND ($after_id IS NULL OR v.id > $after_id) "
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
    "v.normalization_rule_version AS normalization_rule_version "
    "ORDER BY v.id LIMIT $limit"
)

_DATETIME_FIELDS = ("first_seen", "last_seen")


@dataclass(frozen=True)
class ScopedCallPage:
    """One page of v2 records in ascending `id` order. `truncated` means more records follow the
    last one returned; continue with `after_id=records[-1].id`."""

    records: tuple[ScopedObservedCall, ...]
    truncated: bool


def read_scoped_observed_calls(
    runner: neo4j.Session | neo4j.ManagedTransaction,
    *,
    subject_id: str,
    object_id: str | None = None,
    after_id: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> ScopedCallPage:
    """Reads up to `limit` v2 records for one caller Service (and optionally one Operation), after
    `after_id`, in ascending `id` order. Fetches one extra row to decide `truncated` exactly.

    `limit` may not exceed the frozen page size (D3): a larger value is rejected, not silently
    capped, so a caller can never bypass the bound and always sees `truncated` for the rest."""
    if not 1 <= limit <= DEFAULT_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {DEFAULT_PAGE_SIZE}")
    rows = list(
        runner.run(
            _READ_QUERY,
            subject_id=subject_id,
            object_id=object_id,
            after_id=after_id,
            limit=limit + 1,
        )
    )
    records = []
    for row in rows[:limit]:
        data = dict(row)
        for field in _DATETIME_FIELDS:
            # neo4j.time.DateTime -> datetime.datetime, as the v1 evidence reads do.
            data[field] = data[field].to_native()
        records.append(ScopedObservedCall(**data))
    return ScopedCallPage(records=tuple(records), truncated=len(rows) > limit)
