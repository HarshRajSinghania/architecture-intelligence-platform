"""Caller attribution at ingestion (v0.6.0 I2.1c; I1 support matrix §§10-15.1, I2 spec §5).

After the existing v0.5 correlation accepts a CALLS fact, the *original CLIENT span's* admitted
Kubernetes identity is evaluated against ingestion guards I-1..I-5. The outcome is either an
eligible `ScopedCallSeed` (the six variable inputs of the I1 v2 key, plus the non-identity fields
a later v2 record merges) or an ingestion-only `ScopedIngressRefusal`. Nothing here computes a v2
ID, persists anything or changes the v1 fact: the seed and refusal ride alongside the unchanged v1
observation, and both are inert until I2.2 stores them.

Values are exact: a field is present only if it is a non-empty `str`; there is no trimming,
case-folding or repair, and a value is never taken from anything but the original CLIENT.
"""

from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict

NORMALIZATION_RULE_ID = "otel-client-caller-attribution"
NORMALIZATION_RULE_VERSION = 1

# I1 v2 key constants (v2 contract §1). Only the variable inputs travel on a seed.
V2_CONTRACT_VERSION = 2
V2_SOURCE_TYPE = "OPENTELEMETRY"
V2_EVIDENCE_TYPE = "OBSERVED"
V2_RELATION_TYPE = "CALLS"

REASON_CLIENT_IDENTITY_MISSING = "LOCALITY_CLIENT_IDENTITY_MISSING"
REASON_SERVER_ONLY_NO_CLIENT = "LOCALITY_SERVER_ONLY_NO_CLIENT"
REASON_CLIENT_INTERNAL_CONFLICT = "LOCALITY_CLIENT_INTERNAL_CONFLICT"
REASON_CLIENT_FACT_ENVIRONMENT_MISMATCH = "LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH"
REASON_CLIENT_FACT_DAY_MISMATCH = "LOCALITY_CLIENT_FACT_DAY_MISMATCH"
REASON_CLUSTER_UID_MISSING = "LOCALITY_CLUSTER_UID_MISSING"
REASON_POD_UID_MISSING = "LOCALITY_POD_UID_MISSING"


class LocalityDisposition(StrEnum):
    APPLICABLE = "APPLICABLE"
    INAPPLICABLE = "INAPPLICABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICT = "CONFLICT"
    UNSUPPORTED = "UNSUPPORTED"


# I1 §10.1: the within-phase primary choice when several ingestion causes coexist.
_PRECEDENCE = (
    LocalityDisposition.CONFLICT,
    LocalityDisposition.AMBIGUOUS,
    LocalityDisposition.INAPPLICABLE,
    LocalityDisposition.UNRESOLVED,
    LocalityDisposition.INSUFFICIENT_EVIDENCE,
)
_REASON_DISPOSITION = {
    REASON_CLIENT_IDENTITY_MISSING: LocalityDisposition.INSUFFICIENT_EVIDENCE,
    REASON_SERVER_ONLY_NO_CLIENT: LocalityDisposition.INSUFFICIENT_EVIDENCE,
    REASON_CLUSTER_UID_MISSING: LocalityDisposition.INSUFFICIENT_EVIDENCE,
    REASON_POD_UID_MISSING: LocalityDisposition.INSUFFICIENT_EVIDENCE,
    REASON_CLIENT_FACT_ENVIRONMENT_MISMATCH: LocalityDisposition.INAPPLICABLE,
    REASON_CLIENT_FACT_DAY_MISMATCH: LocalityDisposition.INAPPLICABLE,
    REASON_CLIENT_INTERNAL_CONFLICT: LocalityDisposition.CONFLICT,
}


def admissible(value: Any) -> str | None:
    """Matrix §10.2: present only if a non-empty string. Anything else (missing, empty, int, bool,
    list, ...) is treated as missing; the value is otherwise passed through byte-for-byte."""
    return value if isinstance(value, str) and value != "" else None


def utc_day(instant: datetime) -> date:
    """Matrix §12.2: the calendar date of the instant in UTC. A naive instant is read as UTC, as
    the v1 path already does (`day_bucket` truncates in the value's own, absent, timezone), so the
    v1 and v2 day of one interaction can never disagree. The receiver only produces aware UTC."""
    if instant.tzinfo is None:
        return instant.date()
    return instant.astimezone(UTC).date()


class ClientCarrier(BaseModel):
    """The original CLIENT span's admitted attributes (matrix §10.1), exact and bounded. Built
    only from a CLIENT `RuntimeSpan` or a CLIENT `PendingHttpSpan`."""

    model_config = ConfigDict(frozen=True)

    environment: str | None = None
    pod_uid: str | None = None
    cluster_uid: str | None = None
    end_time: datetime
    namespace: str | None = None
    pod_name: str | None = None
    deployment_name: str | None = None
    statefulset_name: str | None = None
    daemonset_name: str | None = None

    @classmethod
    def from_span(cls, span: Any) -> "ClientCarrier":
        """`span` is a CLIENT RuntimeSpan (`end_time`) or PendingHttpSpan (`timestamp`)."""
        end_time = getattr(span, "end_time", None) or span.timestamp
        return cls(
            environment=admissible(span.environment),
            pod_uid=admissible(span.k8s_pod_uid),
            cluster_uid=admissible(span.k8s_cluster_uid),
            end_time=end_time,
            namespace=admissible(span.k8s_namespace_name),
            pod_name=admissible(span.k8s_pod_name),
            deployment_name=admissible(span.k8s_deployment_name),
            statefulset_name=admissible(span.k8s_statefulset_name),
            daemonset_name=admissible(span.k8s_daemonset_name),
        )


class ScopedCallSeed(BaseModel):
    """An interaction eligible for a caller-Pod-scoped v2 record. The six variable I1 key inputs
    plus the non-identity fields (I1 v2 contract §§1, 3). It carries no ID and no Workload."""

    model_config = ConfigDict(frozen=True)

    environment: str
    bucket_utc_day: str
    subject_id: str
    object_id: str
    caller_cluster_uid: str
    caller_pod_uid: str
    fact_timestamp: datetime
    trace_id: str
    correlation_mode: str
    k8s_namespace_name: str | None = None
    k8s_pod_name: str | None = None
    k8s_deployment_name: str | None = None
    k8s_statefulset_name: str | None = None
    k8s_daemonset_name: str | None = None
    normalization_rule_id: str = NORMALIZATION_RULE_ID
    normalization_rule_version: int = NORMALIZATION_RULE_VERSION


class ScopedIngressRefusal(BaseModel):
    """An ingestion-only diagnostic (I1 §10.2): no v2 is written. It holds codes and identifiers
    only, never an attribute value, and is not architecture evidence. `v1_status` records whether
    the interaction's v1 handling is `unchanged` or `none` (a SERVER_ONLY yields no v1 CALLS)."""

    model_config = ConfigDict(frozen=True)

    trace_id: str
    environment: str | None
    bucket_utc_day: str
    disposition: LocalityDisposition
    reasons: tuple[str, ...]
    v1_status: str = "unchanged"


_WORKLOAD_NAME_FIELDS = ("deployment_name", "statefulset_name", "daemonset_name")


def _primary(reasons: set[str]) -> LocalityDisposition:
    dispositions = {_REASON_DISPOSITION[reason] for reason in reasons}
    return next(d for d in _PRECEDENCE if d in dispositions)


def primary_cause(refusal: "ScopedIngressRefusal") -> str:
    """The single reason a refusal is counted under in the transition report (I2 decision record
    D12.1): among its reasons, those whose disposition is the refusal's primary disposition, and of
    those the lexicographically smallest. The complete sorted reasons stay on the refusal."""
    candidates = [
        reason for reason in refusal.reasons if _REASON_DISPOSITION[reason] == refusal.disposition
    ]
    return min(candidates)


def evaluate_scoped_ingress(
    *,
    subject_id: str,
    object_id: str,
    fact_environment: str,
    fact_timestamp: datetime,
    trace_id: str,
    correlation_mode: str,
    carrier: ClientCarrier | None,
) -> ScopedCallSeed | ScopedIngressRefusal:
    """Guards I-2..I-5 for an already-accepted CALLS (guard I-1: the caller only invokes this once
    a v0.5 CALLS fact exists). Every cause that can actually be established is retained; the
    primary disposition follows the I1 within-phase precedence (matrix §15.1)."""
    day = utc_day(fact_timestamp)
    if carrier is None:
        return ScopedIngressRefusal(
            trace_id=trace_id,
            environment=fact_environment,
            bucket_utc_day=day.isoformat(),
            disposition=LocalityDisposition.INSUFFICIENT_EVIDENCE,
            reasons=(REASON_CLIENT_IDENTITY_MISSING,),
        )

    reasons: set[str] = set()
    if carrier.environment is None:
        reasons.add(REASON_CLIENT_IDENTITY_MISSING)
    elif carrier.environment != fact_environment:
        reasons.add(REASON_CLIENT_FACT_ENVIRONMENT_MISMATCH)
    if carrier.pod_uid is None:
        reasons.add(REASON_POD_UID_MISSING)
    if carrier.cluster_uid is None:
        reasons.add(REASON_CLUSTER_UID_MISSING)
    if utc_day(carrier.end_time) != day:
        reasons.add(REASON_CLIENT_FACT_DAY_MISMATCH)
    if sum(getattr(carrier, name) is not None for name in _WORKLOAD_NAME_FIELDS) > 1:
        reasons.add(REASON_CLIENT_INTERNAL_CONFLICT)

    if reasons:
        return ScopedIngressRefusal(
            trace_id=trace_id,
            environment=fact_environment,
            bucket_utc_day=day.isoformat(),
            disposition=_primary(reasons),
            reasons=tuple(sorted(reasons)),
        )
    assert carrier.pod_uid is not None and carrier.cluster_uid is not None
    return ScopedCallSeed(
        environment=fact_environment,
        bucket_utc_day=day.isoformat(),
        subject_id=subject_id,
        object_id=object_id,
        caller_cluster_uid=carrier.cluster_uid,
        caller_pod_uid=carrier.pod_uid,
        fact_timestamp=fact_timestamp,
        trace_id=trace_id,
        correlation_mode=correlation_mode,
        k8s_namespace_name=carrier.namespace,
        k8s_pod_name=carrier.pod_name,
        k8s_deployment_name=carrier.deployment_name,
        k8s_statefulset_name=carrier.statefulset_name,
        k8s_daemonset_name=carrier.daemonset_name,
    )


def server_only_refusal(
    *, trace_id: str, environment: str | None, timestamp: datetime
) -> ScopedIngressRefusal:
    """A SERVER span whose CLIENT never arrived: v0.5 emits no CALLS fact for it, so there is no
    v1 either, and there is no CLIENT identity to attribute (I1 §6.1, L09b)."""
    return ScopedIngressRefusal(
        trace_id=trace_id,
        environment=environment,
        bucket_utc_day=utc_day(timestamp).isoformat(),
        disposition=LocalityDisposition.INSUFFICIENT_EVIDENCE,
        reasons=(REASON_SERVER_ONLY_NO_CLIENT,),
        v1_status="none",
    )
