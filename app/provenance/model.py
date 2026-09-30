from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


# The source types a *public* evidence answer may carry. `app.architecture_intelligence.contracts`
# types the frozen v0.5 evidence schema's `source_type` from this enum.
#
# KUBERNETES and CONFIGURATION were added in v0.5.0 I3 (spec §16.1): I2 Draft 0.2 §9 kept ALL
# Kubernetes evidence off every public surface with no exception. I3 narrows that boundary rather
# than removing it - a Kubernetes/configuration-mapping evidence record becomes publicly reachable
# only when the current snapshot makes it reachable from a public DEPLOYED_AS claim or
# DeploymentResolution (I3 spec §16.2's exact reachability gate); every other Kubernetes evidence
# record remains exactly as internal as I2 left it. This enum widening reflects that a public
# payload CAN now carry these values under that gate - it does not itself relax the gate, which is
# enforced elsewhere (I3's reconciliation/exposure layer, not this type definition). The internal
# Kubernetes source-type value lives at `app.canonical.infrastructure.KUBERNETES_SOURCE_TYPE`; the
# configuration-mapping source type has no internal-module constant of its own yet since I3's
# mapping-artifact evidence lands in a later slice.
#
# Kept as a comment rather than a class docstring on purpose: Pydantic exports a model/enum
# docstring as the generated JSON Schema's `description`, so writing this as a docstring would
# itself change the frozen public schema (caught by tests/unit/test_architecture_intelligence_
# schema_frozen.py).
class SourceType(StrEnum):
    OPENAPI = "OPENAPI"
    ASYNCAPI = "ASYNCAPI"
    MANIFEST = "MANIFEST"
    OPENTELEMETRY = "OPENTELEMETRY"
    KUBERNETES = "KUBERNETES"
    CONFIGURATION = "CONFIGURATION"


class EvidenceType(StrEnum):
    DECLARED = "DECLARED"
    OBSERVED = "OBSERVED"


class Provenance(BaseModel):
    id: str
    source_type: str  # OPENAPI | ASYNCAPI | MANIFEST | OPENTELEMETRY
    source_file: str
    source_revision: str | None = None
    evidence_type: str = "DECLARED"


class ObservedEvidence(Provenance):
    """A single-observation evidence seed (spec §16) - a degenerate bucket-of-one produced by a
    resolver (e.g. app.telemetry.adapter). The Aggregator (H4 Iteration 11E) merges many seeds for
    the same bucket into the real persisted, time-bounded evidence (summing observation_count,
    expanding first_seen/last_seen, capping sample_trace_ids at 5)."""

    source_type: str = SourceType.OPENTELEMETRY
    source_file: str = "opentelemetry"
    evidence_type: str = EvidenceType.OBSERVED

    environment: str
    bucket_start: datetime
    bucket_end: datetime
    first_seen: datetime
    last_seen: datetime
    observation_count: int
    sample_trace_ids: list[str] = Field(default_factory=list)
    service_version: str | None = None
    # How this evidence was derived (11H R3/spec §14 - see app.telemetry.model.CorrelationMode for
    # the allowed values). Optional so pre-11H-C construction sites keep working unmodified.
    correlation_mode: str | None = None


class RuntimeIdentityObservation(Provenance):
    """A bounded OTel runtime identity observation (I3 spec §9.4) - what a Resource's bounded
    Kubernetes identity attributes (§9.3) describe about one Pod's runtime service identity.

    Deliberately NOT itself a DEPLOYED_AS/CALLS/SENDS/RECEIVES_FROM fact - no relation is ever
    created from this record; it exists so a later slice's Path C reconciliation can look it up by
    (environment, k8s_pod_uid, window). It is also deliberately NOT persisted under the :Evidence
    label (see app.telemetry.aggregator): I3's public evidence-reachability gate (§16.2) doesn't
    exist until slice 5, and the existing :Evidence-scoped public surfaces
    (app.api.evidence, app.architecture_intelligence.repository) filter only on
    source_type != 'KUBERNETES' - an OPENTELEMETRY-sourced :Evidence node would be immediately,
    unconditionally public. Kept separate from ObservedEvidence (a relation-fact's supporting
    evidence) since the two have no field or lifecycle overlap: no sample_trace_ids (§9.4's field
    list is exhaustive and excludes trace/span ids from identity and from the record itself), no
    correlation_mode (nothing to correlate), but adds the normalization_rule fields and the full
    bounded Kubernetes identity attribute set."""

    source_type: str = SourceType.OPENTELEMETRY
    source_file: str = "opentelemetry"
    evidence_type: str = EvidenceType.OBSERVED

    service_name: str
    service_namespace: str | None = None
    service_version: str | None = None
    environment: str
    k8s_pod_uid: str

    # I3 §9.3 optional consistency attributes - see app.telemetry.semconv.resources.
    k8s_pod_name: str | None = None
    k8s_namespace_name: str | None = None
    k8s_cluster_uid: str | None = None
    k8s_deployment_name: str | None = None
    k8s_statefulset_name: str | None = None
    k8s_daemonset_name: str | None = None

    first_seen: datetime
    last_seen: datetime
    observation_count: int

    # I3 §9.4/§9.6 - names of the optional consistency attributes above (service_version or one of
    # the six k8s.* fields; never service_namespace, which is part of this bucket's own identity)
    # that disagreed across two merged observations. Sorted, deduplicated, monotonic - see
    # app.telemetry.aggregator.merge_runtime_identity_observation for why a merge never silently
    # overwrites a disagreement: §9.6 requires a directly contradictory consistency attribute to
    # surface as CONFLICT downstream, not be lost at persistence time.
    conflicting_consistency_attributes: list[str] = Field(default_factory=list)

    # I3 §9.4 - identifies the normalization rule/version that produced this record, so a later
    # rule revision can be distinguished from earlier persisted observations.
    normalization_rule_id: str = "otel-runtime-identity-observation"
    normalization_rule_version: int = 1


class ScopedObservedCall(BaseModel):
    """A caller-Pod-scoped v2 observed CALLS record (v0.6.0 I1 v2 contract §§1 and 3, I2 decision
    record D1). It represents the *same* interaction as a v1 `ObservedEvidence` bucket, isolated
    from it: it is never `:Evidence`, never attached to a relation's `evidence_ids`, and never
    counted in v0.5 qualification, coverage or public evidence.

    The identity is the ten key fields (`id` is derived from them by
    `app.canonical.ids.scoped_observed_call_v2_id`); everything after `caller_pod_uid` is merged,
    order-independently, by `app.telemetry.scoped_evidence.merge_scoped_call`. No raw Resource, no
    resolved Workload and no capture identity is stored: the Workload is resolved at query time
    against the selected capture (I1 §9).

    The optional `k8s_*` names are consistency metadata only. A name whose merged seeds disagreed is
    set to None and listed in `conflicting_consistency_attributes` for good (an absorbing conflict).
    Kept apart from `RuntimeIdentityObservation`, whose per-Service/Pod merge is order-dependent.
    """

    model_config = ConfigDict(frozen=True)

    id: str

    # The I1 v2 contract §1 identity (ten fields).
    contract_version: int = 2
    source_type: str = SourceType.OPENTELEMETRY
    evidence_type: str = EvidenceType.OBSERVED
    relation_type: str = "CALLS"
    environment: str
    bucket_utc_day: str
    subject_id: str
    object_id: str
    caller_cluster_uid: str
    caller_pod_uid: str

    # Non-identity fields (v2 contract §3).
    first_seen: datetime
    last_seen: datetime
    observation_count: int
    correlation_mode: str
    sample_trace_ids: list[str] = Field(default_factory=list)
    k8s_namespace_name: str | None = None
    k8s_pod_name: str | None = None
    k8s_deployment_name: str | None = None
    k8s_statefulset_name: str | None = None
    k8s_daemonset_name: str | None = None
    conflicting_consistency_attributes: list[str] = Field(default_factory=list)
    key_rule_id: str = "otel-calls-scoped-evidence-v2-key"
    key_rule_version: int = 1
    normalization_rule_id: str = "otel-client-caller-attribution"
    normalization_rule_version: int = 1
