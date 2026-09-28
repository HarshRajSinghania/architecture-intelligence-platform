"""v0.5.0 I3 spec §7 (Path A), §8 (Path B), §9 (Path C), §13 (resolution identity/shape) - pure
functions projecting already-persisted I2 Kubernetes facts, OTel runtime identity evidence, and a
locally loaded configured mapping artifact into `DeploymentClaim`/`DeploymentResolution` instances
(frozen contracts from `app.architecture_intelligence.contracts`). No Neo4j access here - real reads
live in `app.architecture_intelligence.deployment_repository`, which supplies this module's row
types and lookup callables; unit tests supply fakes instead, mirroring how
`app.architecture_intelligence.dependency_projection` takes plain rows rather than a live database.
Cross-path agreement/conflict reduction across A/B/C (slice 5b) is out of scope here - each path
below runs alone and returns its own resolutions/claims.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.architecture_intelligence.canonical_json import canonical_json_bytes
from app.architecture_intelligence.contracts import (
    DEPLOYMENT_RECONCILIATION_RULE_ID,
    DeploymentClaim,
    DeploymentPredicate,
    DeploymentResolution,
    DeploymentResolutionMethod,
    DeploymentResolutionStatus,
    EntityRef,
    EntityType,
    LimitationCode,
    ObservationContextRef,
    WorkloadKind,
    WorkloadRef,
)
from app.sources.identity import kubernetes_logical_resource_id
from app.sources.service_workload_mapping import (
    ServiceWorkloadMappingDocument,
    ServiceWorkloadMappingEntry,
)
from app.telemetry.model import DiscoveryStatus
from app.telemetry.service_resolver import DeclaredServiceCandidate, resolve_service

_RECONCILIATION_RULE_VERSION = 1

# I3 spec §11 / §8.1: the raw Kubernetes controller-kind string (matching I2's own
# `InfrastructureEntity.resource_kind` convention) mapped onto the public, uppercase
# `WorkloadKind` enum. No case folding or fuzzy matching - a `workload_kind` outside this map is a
# real defect (I2 already restricts KUBERNETES_WORKLOAD promotion to exactly these three kinds).
_WORKLOAD_KIND_BY_RAW = {
    "Deployment": WorkloadKind.DEPLOYMENT,
    "StatefulSet": WorkloadKind.STATEFULSET,
    "DaemonSet": WorkloadKind.DAEMONSET,
}


@dataclass(frozen=True)
class WorkloadContribution:
    """One I2 `InfrastructureContribution` row for a Workload, reduced to the fields Path A needs:
    the retained `service-id` annotation (`None` if this contribution carries none) and the
    contribution's own evidence references."""

    annotation: str | None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class CurrentKubernetesWorkload:
    """One current I2 `InfrastructureEntity` of kind `KUBERNETES_WORKLOAD`, identified by its
    logical resource id (`app.sources.identity.kubernetes_logical_resource_id`). `contributions` is
    populated for Path A's full scan and left empty (the default) when this row is returned as a
    single Path B point-lookup result, where only the Workload's own identity fields are needed."""

    workload_id: str
    workload_kind: str
    namespace: str
    name: str
    contributions: tuple[WorkloadContribution, ...] = ()


@dataclass(frozen=True)
class PathResolutionResult:
    resolutions: list[DeploymentResolution]
    claims: list[DeploymentClaim]


def compute_deployment_claim_id(*, service_id: str, workload_id: str) -> str:
    """Spec §6: `aip:claim:v1:sha256(canonical-json({"DEPLOYED_AS", canonical Service id, logical
    Workload id}))`. Deliberately excludes evidence method - "changing evidence method without
    changing the Service/Workload pair does not create a different semantic claim id" - mirrors
    `app.architecture_intelligence.dependency_projection.compute_claim_id`'s identical shape."""
    payload = {
        "predicate": "DEPLOYED_AS",
        "service_id": service_id,
        "workload_id": workload_id,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"aip:claim:v1:{digest}"


def compute_deployment_group_key(
    *,
    workload_id: str | None = None,
    mapping_artifact_id: str | None = None,
    mapping_artifact_revision: str | None = None,
    mapping_id: str | None = None,
    otel_observation_id: str | None = None,
) -> str:
    """Spec §13.1's reconciliation-candidate-group key, all three branches. Exactly one of
    `workload_id`, the three `mapping_*` arguments, or `otel_observation_id` must be given.

    The mapping branch's canonical-JSON dict encoding (not delimiter concatenation) is normative
    per §13.1, specifically so delimiter-bearing artifact id/revision/mappingId values can never
    collide across a different `(artifact_id, artifact_revision, mapping_id)` tuple.

    The `otel_observation_id` branch (I3 slice 4) is spec §13.1's third branch: "OTel runtime
    identity observation whose Pod UID cannot resolve to exactly one current Workload." If an
    observation *does* resolve to a current Workload, it joins that Workload's `workload:<id>`
    group instead (§13.1: "it joins that Workload's group rather than creating a separate OTel
    group") - callers never pass both `workload_id` and `otel_observation_id` for one observation.
    """
    mapping_fields_given = any(
        value is not None for value in (mapping_artifact_id, mapping_artifact_revision, mapping_id)
    )
    branches_given = sum(
        [workload_id is not None, mapping_fields_given, otel_observation_id is not None]
    )
    if branches_given > 1:
        raise ValueError(
            "compute_deployment_group_key accepts exactly one of workload_id, the mapping_* "
            "fields, or otel_observation_id, not more than one"
        )
    if workload_id is not None:
        return f"workload:{workload_id}"
    if otel_observation_id is not None:
        return f"otel:{otel_observation_id}"
    if mapping_artifact_id is None or mapping_artifact_revision is None or mapping_id is None:
        raise ValueError(
            "compute_deployment_group_key requires exactly one of workload_id, all three of "
            "mapping_artifact_id/mapping_artifact_revision/mapping_id, or otel_observation_id"
        )
    payload = {
        "artifact_id": mapping_artifact_id,
        "artifact_revision": mapping_artifact_revision,
        "mapping_id": mapping_id,
    }
    return "mapping:" + canonical_json_bytes(payload).decode("utf-8")


def compute_deployment_resolution_id(
    *,
    snapshot_id: str,
    context_id: str,
    group_key: str,
    reconciliation_rule_id: str = DEPLOYMENT_RECONCILIATION_RULE_ID,
    reconciliation_rule_version: int = _RECONCILIATION_RULE_VERSION,
) -> str:
    """Spec §13.2's literal formula. The exact canonical-JSON key names hashed here are this
    module's own implementation choice (§13.2 states the formula in prose, not a schema) - only
    "same 5 components -> same id, any different component -> a different id" is observable/
    normative behavior."""
    payload = {
        "snapshot_id": snapshot_id,
        "context_id": context_id,
        "group_key": group_key,
        "reconciliation_rule_id": reconciliation_rule_id,
        "reconciliation_rule_version": reconciliation_rule_version,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"aip:deployment-resolution:v1:{digest}"


def compute_service_workload_mapping_evidence_id(
    *, artifact_id: str, artifact_revision: str, content_digest: str, mapping_id: str
) -> str:
    """Spec §8.3: deterministic evidence identity bound to the mapping artifact's id, revision,
    content digest, and this entry's `mappingId`. Uses the same canonical-JSON dict-encoding
    approach as `compute_deployment_group_key`'s mapping branch (not delimiter concatenation), for
    consistency with §13.1's explicit normative requirement and because this is the same 4-field
    identity reused across both formulas."""
    payload = {
        "artifact_id": artifact_id,
        "artifact_revision": artifact_revision,
        "content_digest": content_digest,
        "mapping_id": mapping_id,
    }
    digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return f"urn:aip:service-workload-mapping-evidence:v1:{digest}"


def _workload_ref(workload: CurrentKubernetesWorkload) -> WorkloadRef:
    return WorkloadRef(
        id=workload.workload_id,
        type=EntityType.WORKLOAD,
        name=workload.name,
        workload_kind=_WORKLOAD_KIND_BY_RAW[workload.workload_kind],
        namespace=workload.namespace,
    )


def _resolved_claim(
    *,
    service_id: str,
    service_name: str,
    workload_ref: WorkloadRef,
    method: DeploymentResolutionMethod,
    evidence_refs: list[str],
) -> DeploymentClaim:
    claim_id = compute_deployment_claim_id(service_id=service_id, workload_id=workload_ref.id)
    return DeploymentClaim(
        claim_id=claim_id,
        subject=EntityRef(id=service_id, type=EntityType.SERVICE, name=service_name),
        predicate=DeploymentPredicate.DEPLOYED_AS,
        object=workload_ref,
        resolution_method=method,
        supporting_methods=[method],
        reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
        reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
        evidence_refs=evidence_refs,
    )


def resolve_path_a(
    *,
    workloads: Sequence[CurrentKubernetesWorkload],
    lookup_service_name: Callable[[str], str | None],
    snapshot_id: str,
    context_id: str,
) -> PathResolutionResult:
    """Spec §7: for every current I2 `KUBERNETES_WORKLOAD` entity, group its contributions'
    retained `service-id` annotations by exact string equality (no trim/case-fold/fuzzy matching).
    A Workload with no annotated contribution at all produces no resolution (there is no Path A
    evidence to report); one agreed annotation resolves or is `UNRESOLVED` depending on whether it
    names a real declared Service; more than one distinct annotation is `CONFLICT`."""
    resolutions: list[DeploymentResolution] = []
    claims: list[DeploymentClaim] = []

    for workload in workloads:
        annotated = [c for c in workload.contributions if c.annotation is not None]
        if not annotated:
            continue

        distinct_values = sorted({c.annotation for c in annotated if c.annotation is not None})
        evidence_refs = sorted({ref for c in annotated for ref in c.evidence_refs})
        workload_ref = _workload_ref(workload)
        group_key = compute_deployment_group_key(workload_id=workload.workload_id)
        resolution_id = compute_deployment_resolution_id(
            snapshot_id=snapshot_id, context_id=context_id, group_key=group_key
        )

        if len(distinct_values) > 1:
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.CONFLICT,
                    service_id=None,
                    candidate_service_ids=distinct_values,
                    supporting_methods=[],
                    supporting_evidence_refs=[],
                    conflicting_evidence_refs=evidence_refs,
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_CONFLICT],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
            continue

        [value] = distinct_values
        service_name = lookup_service_name(value)
        if service_name is not None:
            claim = _resolved_claim(
                service_id=value,
                service_name=service_name,
                workload_ref=workload_ref,
                method=DeploymentResolutionMethod.RESOLVED_EXPLICIT,
                evidence_refs=evidence_refs,
            )
            claims.append(claim)
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.RESOLVED_EXPLICIT,
                    service_id=value,
                    candidate_service_ids=[value],
                    supporting_methods=[DeploymentResolutionMethod.RESOLVED_EXPLICIT],
                    supporting_evidence_refs=evidence_refs,
                    conflicting_evidence_refs=[],
                    limitation_codes=[],
                    claim_id=claim.claim_id,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
        else:
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.UNRESOLVED,
                    service_id=None,
                    candidate_service_ids=[value],
                    supporting_methods=[],
                    supporting_evidence_refs=evidence_refs,
                    conflicting_evidence_refs=[],
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )

    return PathResolutionResult(resolutions=resolutions, claims=claims)


@dataclass(frozen=True)
class _MappingRecord:
    document: ServiceWorkloadMappingDocument
    entry: ServiceWorkloadMappingEntry
    mapping_evidence_id: str
    workload: CurrentKubernetesWorkload | None


def resolve_path_b(
    *,
    document: ServiceWorkloadMappingDocument | None,
    configured_kubernetes_sources: Sequence[tuple[str, str]],
    resolve_workload: Callable[[str], CurrentKubernetesWorkload | None],
    lookup_service_name: Callable[[str], str | None],
    snapshot_id: str,
    context_id: str,
) -> PathResolutionResult:
    """Spec §8.1: "Path B uses one local, versioned mapping artifact" - `document` is that single
    artifact (or `None` when none is configured), never a collection. For every entry, check its
    `(kubernetesSourceId, clusterUid)` against the currently configured I2 sources, then resolve the
    exact Workload via `kubernetes_logical_resource_id` + `resolve_workload` (a point lookup the
    caller supplies - real reads live in `app.architecture_intelligence.deployment_repository`).
    Entries resolving to the same Workload are grouped per §13.1's `"workload:"` branch
    (`RESOLVED_CONFIGURED`/`UNRESOLVED`/`CONFLICT`, mirroring `resolve_path_a`'s identical
    reduction); entries whose target Workload didn't resolve (wrong source/cluster UID, or no
    matching current Workload) each get their own `"mapping:"`-keyed group -> `UNRESOLVED` with
    `workload = null`.
    """
    if document is None:
        return PathResolutionResult(resolutions=[], claims=[])

    current_source_pairs = set(configured_kubernetes_sources)
    records: list[_MappingRecord] = []

    for entry in document.entries:
        mapping_evidence_id = compute_service_workload_mapping_evidence_id(
            artifact_id=document.artifact_id,
            artifact_revision=document.artifact_revision,
            content_digest=document.content_digest,
            mapping_id=entry.mapping_id,
        )
        matches_current_source = (
            entry.kubernetes_source_id,
            entry.cluster_uid,
        ) in current_source_pairs
        workload: CurrentKubernetesWorkload | None = None
        if matches_current_source:
            entity_id = kubernetes_logical_resource_id(
                cluster_uid=entry.cluster_uid,
                api_group=entry.api_group,
                kind=entry.workload_kind,
                namespace=entry.namespace,
                name=entry.name,
            )
            workload = resolve_workload(entity_id)
        records.append(
            _MappingRecord(
                document=document,
                entry=entry,
                mapping_evidence_id=mapping_evidence_id,
                workload=workload,
            )
        )

    by_workload_id: dict[str, list[_MappingRecord]] = defaultdict(list)
    unmatched: list[_MappingRecord] = []
    for record in records:
        if record.workload is not None:
            by_workload_id[record.workload.workload_id].append(record)
        else:
            unmatched.append(record)

    resolutions: list[DeploymentResolution] = []
    claims: list[DeploymentClaim] = []

    for workload_id in sorted(by_workload_id):
        group_records = by_workload_id[workload_id]
        workload_ref = _workload_ref(group_records[0].workload)  # type: ignore[arg-type]
        group_key = compute_deployment_group_key(workload_id=workload_id)
        resolution_id = compute_deployment_resolution_id(
            snapshot_id=snapshot_id, context_id=context_id, group_key=group_key
        )
        distinct_services = sorted({record.entry.service_id for record in group_records})
        evidence_refs = sorted({record.mapping_evidence_id for record in group_records})

        if len(distinct_services) > 1:
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.CONFLICT,
                    service_id=None,
                    candidate_service_ids=distinct_services,
                    supporting_methods=[],
                    supporting_evidence_refs=[],
                    conflicting_evidence_refs=evidence_refs,
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_CONFLICT],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
            continue

        [service_id] = distinct_services
        service_name = lookup_service_name(service_id)
        if service_name is not None:
            claim = _resolved_claim(
                service_id=service_id,
                service_name=service_name,
                workload_ref=workload_ref,
                method=DeploymentResolutionMethod.RESOLVED_CONFIGURED,
                evidence_refs=evidence_refs,
            )
            claims.append(claim)
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.RESOLVED_CONFIGURED,
                    service_id=service_id,
                    candidate_service_ids=[service_id],
                    supporting_methods=[DeploymentResolutionMethod.RESOLVED_CONFIGURED],
                    supporting_evidence_refs=evidence_refs,
                    conflicting_evidence_refs=[],
                    limitation_codes=[],
                    claim_id=claim.claim_id,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
        else:
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.UNRESOLVED,
                    service_id=None,
                    candidate_service_ids=[service_id],
                    supporting_methods=[],
                    supporting_evidence_refs=evidence_refs,
                    conflicting_evidence_refs=[],
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )

    for record in sorted(
        unmatched,
        key=lambda r: (r.document.artifact_id, r.document.artifact_revision, r.entry.mapping_id),
    ):
        group_key = compute_deployment_group_key(
            mapping_artifact_id=record.document.artifact_id,
            mapping_artifact_revision=record.document.artifact_revision,
            mapping_id=record.entry.mapping_id,
        )
        resolution_id = compute_deployment_resolution_id(
            snapshot_id=snapshot_id, context_id=context_id, group_key=group_key
        )
        resolutions.append(
            DeploymentResolution(
                resolution_id=resolution_id,
                workload=None,
                status=DeploymentResolutionStatus.UNRESOLVED,
                service_id=None,
                candidate_service_ids=[record.entry.service_id],
                supporting_methods=[],
                supporting_evidence_refs=[record.mapping_evidence_id],
                conflicting_evidence_refs=[],
                limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED],
                claim_id=None,
                reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
            )
        )

    return PathResolutionResult(resolutions=resolutions, claims=claims)


# ---------------------------------------------------------------------------------------------
# Path C - qualified OTel Pod-UID -> I2 owner-chain -> exact Service resolver linkage (spec §9)
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedPodRow:
    """One current I2 `KUBERNETES_POD` entity matched by its real, API-server-assigned
    `captured_resource_uid` (spec §9.5). Only ever produced by a `CAPTURED_RESOURCE` contribution -
    `captured_resource_uid` is `None` for every `DECLARED_MANIFEST` one, so a query matching on it
    can never return a `DECLARED_MANIFEST` row; spec §9.5's own "Path C requires I2 evidence mode
    CAPTURED_RESOURCE" needs no separate check here."""

    pod_id: str
    pod_name: str
    pod_namespace: str
    cluster_uid: str
    captured_at: str | None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkloadOwnershipRow:
    """One current I2 `WORKLOAD_OWNS_POD` claim naming a given Pod as its object (spec §9.5)."""

    workload_id: str
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeIdentityObservationRow:
    """One persisted `RuntimeIdentityObservation` row (spec §9.4), read back as a plain dict-backed
    row rather than the Pydantic model it was written as - a Neo4j read is never re-validated on
    the way out, so every field is honestly nullable here even though the write-side model
    guarantees some of them non-null in practice (e.g. `environment`, which slice 2's own
    extraction already filters non-null before persistence - see spec §21.3's "deployment.
    environment.name absent" required case, exercised only via a hand-built fake row for exactly
    this reason)."""

    id: str
    service_name: str
    service_namespace: str | None
    service_version: str | None
    environment: str | None
    k8s_pod_uid: str | None
    k8s_pod_name: str | None
    k8s_namespace_name: str | None
    k8s_cluster_uid: str | None
    k8s_deployment_name: str | None
    k8s_statefulset_name: str | None
    k8s_daemonset_name: str | None
    last_seen: datetime | None
    # v0.5.0 I3 slice 5b (PR #222 Copilot review finding): the four fields a synthetic Path C
    # `EvidenceRecord` needs to carry the observation's *real* metadata (spec §16.1) instead of
    # fabricating it from `last_seen` alone - `resolve_path_c` itself never reads these, only
    # `deployment_reconciliation._path_c_evidence_records`/`_bucket_context_free_observations` do.
    first_seen: datetime | None = None
    observation_count: int | None = None
    normalization_rule_id: str | None = None
    normalization_rule_version: int | None = None
    conflicting_consistency_attributes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeclaredServiceIdentity:
    """A `Service` node's identity, returned only when it is currently *declared* (spec §9.2's
    "existing declared AIP Service" gate - see `deployment_repository.read_declared_service_identity`)."""

    service_id: str
    name: str
    namespace: str | None
    version: str | None


# spec §9.6: "k8s.deployment.name -> if resolved Workload kind = Deployment, exact equality with
# Workload name; otherwise contradictory" (repeated identically for StatefulSet/DaemonSet).
_WORKLOAD_KIND_CONSISTENCY_ATTR = {
    WorkloadKind.DEPLOYMENT: "k8s_deployment_name",
    WorkloadKind.STATEFULSET: "k8s_statefulset_name",
    WorkloadKind.DAEMONSET: "k8s_daemonset_name",
}


def _parse_rfc3339(value: str | None) -> datetime | None:
    """No RFC 3339 parser already exists elsewhere in this codebase for this purpose - small and
    local. `None` for a missing or unparsable value; the caller treats both as "absent" (spec
    §9.7's `capturedAt`-absent case)."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _resolve_declared_service_id(
    *,
    obs: RuntimeIdentityObservationRow,
    declared_service_candidates: Sequence[DeclaredServiceCandidate],
    service_aliases: dict[str, str],
    lookup_declared_service: Callable[[str], DeclaredServiceIdentity | None],
) -> DeclaredServiceIdentity | None:
    """Spec §9.2: reuses `app.telemetry.service_resolver.resolve_service` (never reimplemented) for
    its exact namespace+name / unique-name / configured-alias tiering, then independently
    re-verifies any `DECLARED` result against the same `owner_source_ids`-based authoritative check
    `deployment_repository.read_service_name` already applies for Path A/B. This second check is
    load-bearing: `resolve_service`'s own `DiscoveryStatus.DECLARED` only means "some `:Service`
    node matches by name/namespace/alias" - including a stale `OBSERVED_ONLY` stub minted by an
    earlier telemetry batch, since it never inspects `owner_source_ids`. A `resolve_service` result
    that would mint (`OBSERVED_ONLY`) is never even re-checked - spec §9.2: "A resolver result that
    would mint or reuse an OBSERVED_ONLY Service is not a successful I3 identity path." Pure and
    side-effect-free either way: `resolve_service` never writes to Neo4j on its own (only
    `app.telemetry.aggregator._persist_batch_tx` mints a stub, and this function never calls it).
    """
    resolution = resolve_service(
        list(declared_service_candidates),
        service_name=obs.service_name,
        service_namespace=obs.service_namespace,
        aliases=service_aliases,
    )
    if resolution.discovery_status is not DiscoveryStatus.DECLARED:
        return None
    return lookup_declared_service(resolution.service_id)


def _consistency_attributes_agree(
    *,
    obs: RuntimeIdentityObservationRow,
    pod: CapturedPodRow,
    workload: CurrentKubernetesWorkload,
    identity: DeclaredServiceIdentity,
) -> bool:
    """Spec §9.6: every *present* optional consistency attribute must agree with the already-
    resolved identities; a missing one is never itself a limitation. §9.4's own instruction treats
    a non-empty `conflicting_consistency_attributes` (a contradiction already detected during
    slice 2's own bucket merge) identically to a directly observed contradiction here."""
    if obs.conflicting_consistency_attributes:
        return False
    if (
        identity.namespace is not None
        and obs.service_namespace is not None
        and obs.service_namespace != identity.namespace
    ):
        return False
    if (
        obs.service_version is not None
        and identity.version is not None
        and obs.service_version != identity.version
    ):
        return False
    # k8s.namespace.name is checked against the Pod's own namespace, not a separately-fetched
    # Workload namespace: I2's own owner-chain resolution only ever matches an owner in the same
    # namespace, so Pod and Workload namespace are guaranteed equal by construction.
    if obs.k8s_namespace_name is not None and obs.k8s_namespace_name != pod.pod_namespace:
        return False
    if obs.k8s_cluster_uid is not None and obs.k8s_cluster_uid != pod.cluster_uid:
        return False
    if obs.k8s_pod_name is not None and obs.k8s_pod_name != pod.pod_name:
        return False
    resolved_kind = _WORKLOAD_KIND_BY_RAW[workload.workload_kind]
    for kind, attr_name in _WORKLOAD_KIND_CONSISTENCY_ATTR.items():
        value = getattr(obs, attr_name)
        if value is None:
            continue
        if kind is not resolved_kind:
            # A non-null attribute naming a kind other than the one actually resolved is
            # unconditionally contradictory, regardless of its own value (spec §9.6, stated
            # identically for all three attributes).
            return False
        if value != workload.name:
            return False
    return True


def _observation_context_limitation(
    *,
    obs: RuntimeIdentityObservationRow,
    pod: CapturedPodRow,
    observation_context: ObservationContextRef,
) -> LimitationCode | None:
    """Spec §9.7's exact applicability rule, in its own literal order. `None` means applicable."""
    if not obs.environment:
        return LimitationCode.DEPLOYMENT_EVIDENCE_INCOMPLETE
    if obs.environment != observation_context.environment:
        return LimitationCode.DEPLOYMENT_ENVIRONMENT_MISMATCH
    if obs.last_seen is None or not (
        observation_context.window_start <= obs.last_seen <= observation_context.window_end
    ):
        return LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH
    captured_at = _parse_rfc3339(pod.captured_at)
    if captured_at is None or not (
        observation_context.window_start <= captured_at <= observation_context.window_end
    ):
        return LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH
    return None


@dataclass(frozen=True)
class _WorkloadScopedOutcome:
    """One observation's per-observation Path C outcome once its Pod UID has resolved to exactly
    one current Workload (spec §13.1: it joins that Workload's group from this point on,
    regardless of what happens next)."""

    workload: CurrentKubernetesWorkload
    outcome: str  # "candidate" | "conflict" | "unresolved"
    candidate_service_id: str | None
    candidate_service_name: str | None
    limitation_code: LimitationCode | None
    evidence_refs: tuple[str, ...]


def _standalone_otel_resolution(
    *,
    observation_id: str,
    status: DeploymentResolutionStatus,
    limitation_code: LimitationCode,
    evidence_refs: Sequence[str],
    snapshot_id: str,
    context_id: str,
) -> DeploymentResolution:
    """Spec §13.1's third group-key branch: an observation whose Pod UID never resolves to exactly
    one current Workload gets its own `"otel:<observation-id>"` group (§9.5's unknown/stale/
    ambiguous Pod UID and unresolved/ambiguous owner-chain cases).

    `observation_id` is unioned into the returned evidence unconditionally (PR #220 review finding):
    §13.1 names the group key itself after "the OTel runtime-identity evidence id," and §13.5
    requires a non-resolved outcome to retain its own evidence - every standalone group's *only*
    universally-available evidence is the observation that produced it, so this must never depend
    on a caller remembering to include it in `evidence_refs`.
    """
    group_key = compute_deployment_group_key(otel_observation_id=observation_id)
    resolution_id = compute_deployment_resolution_id(
        snapshot_id=snapshot_id, context_id=context_id, group_key=group_key
    )
    return DeploymentResolution(
        resolution_id=resolution_id,
        workload=None,
        status=status,
        service_id=None,
        candidate_service_ids=[],
        supporting_methods=[],
        supporting_evidence_refs=sorted({*evidence_refs, observation_id}),
        conflicting_evidence_refs=[],
        limitation_codes=[limitation_code],
        claim_id=None,
        reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
        reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
    )


def _evaluate_observation(
    *,
    obs: RuntimeIdentityObservationRow,
    lookup_pods_by_uid: Callable[[str], Sequence[CapturedPodRow]],
    lookup_workload_ids_owning_pod: Callable[[str], Sequence[WorkloadOwnershipRow]],
    resolve_workload: Callable[[str], CurrentKubernetesWorkload | None],
    declared_service_candidates: Sequence[DeclaredServiceCandidate],
    service_aliases: dict[str, str],
    lookup_declared_service: Callable[[str], DeclaredServiceIdentity | None],
    observation_context: ObservationContextRef,
    snapshot_id: str,
    context_id: str,
) -> DeploymentResolution | _WorkloadScopedOutcome:
    """Spec §9.1->9.7's full per-observation pipeline: Pod-UID lookup, owner-chain linkage,
    observation-context/temporal compatibility, exact Service resolution, consistency checks - in
    that order, stopping at the first outcome that's already determined. Observation-context
    applicability is checked before Service/consistency (PR #220 review, round 2) specifically so a
    non-applicable observation can never be misclassified as a Service/Workload contradiction."""
    if not obs.k8s_pod_uid:
        # §9.1: "service.name alone is insufficient" / no Pod UID at all to look up.
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.UNRESOLVED,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED,
            evidence_refs=(),
            snapshot_id=snapshot_id,
            context_id=context_id,
        )

    pods = lookup_pods_by_uid(obs.k8s_pod_uid)
    if len(pods) == 0:
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.UNRESOLVED,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED,
            evidence_refs=(),
            snapshot_id=snapshot_id,
            context_id=context_id,
        )
    if len(pods) > 1:
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.AMBIGUOUS,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_AMBIGUOUS,
            evidence_refs=[ref for pod in pods for ref in pod.evidence_refs],
            snapshot_id=snapshot_id,
            context_id=context_id,
        )
    [pod] = pods

    owners = lookup_workload_ids_owning_pod(pod.pod_id)
    if len(owners) == 0:
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.UNRESOLVED,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED,
            evidence_refs=pod.evidence_refs,
            snapshot_id=snapshot_id,
            context_id=context_id,
        )
    if len(owners) > 1:
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.AMBIGUOUS,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_AMBIGUOUS,
            evidence_refs=[
                *pod.evidence_refs,
                *(ref for owner in owners for ref in owner.evidence_refs),
            ],
            snapshot_id=snapshot_id,
            context_id=context_id,
        )
    [owner] = owners

    workload = resolve_workload(owner.workload_id)
    if workload is None:
        # Defensive only: a live WORKLOAD_OWNS_POD claim naming a non-live Workload shouldn't occur
        # given the importer's shared-ownership deletion semantics (both expire together).
        return _standalone_otel_resolution(
            observation_id=obs.id,
            status=DeploymentResolutionStatus.UNRESOLVED,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED,
            evidence_refs=[*pod.evidence_refs, *owner.evidence_refs],
            snapshot_id=snapshot_id,
            context_id=context_id,
        )

    # Workload-scoped from here on (spec §13.1) - every subsequent outcome joins this Workload's
    # "workload:<id>" group, regardless of whether Service resolution/consistency/temporal checks
    # succeed. The observation's own id is itself evidence (§13.1 calls it "OTel runtime-identity
    # evidence id") even though `RuntimeIdentityObservation` isn't `:Evidence`-labeled/publicly
    # reachable until slice 5's gate - see the plan's own flagged note on this.
    base_evidence = (*pod.evidence_refs, *owner.evidence_refs, obs.id)

    # PR #220 review (round 2): observation-context/temporal applicability is checked BEFORE
    # Service resolution/consistency, not after. §9.7 is explicit that a non-applicable observation
    # (wrong environment, outside the window) "is not a contradictory Service<->Workload identity
    # claim" - it must never be allowed to reach the consistency check and risk being misclassified
    # as CONFLICT (or, once the repository read became an unfiltered full scan, silently support a
    # RESOLVED_OBSERVED claim as if it had actually agreed). `capturedAt` only needs `pod`, already
    # available at this point, so this reordering costs nothing.
    limitation = _observation_context_limitation(
        obs=obs, pod=pod, observation_context=observation_context
    )
    if limitation is not None:
        return _WorkloadScopedOutcome(
            workload=workload,
            outcome="unresolved",
            candidate_service_id=None,
            candidate_service_name=None,
            limitation_code=limitation,
            evidence_refs=base_evidence,
        )

    identity = _resolve_declared_service_id(
        obs=obs,
        declared_service_candidates=declared_service_candidates,
        service_aliases=service_aliases,
        lookup_declared_service=lookup_declared_service,
    )
    if identity is None:
        return _WorkloadScopedOutcome(
            workload=workload,
            outcome="unresolved",
            candidate_service_id=None,
            candidate_service_name=None,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED,
            evidence_refs=base_evidence,
        )

    if not _consistency_attributes_agree(obs=obs, pod=pod, workload=workload, identity=identity):
        return _WorkloadScopedOutcome(
            workload=workload,
            outcome="conflict",
            candidate_service_id=identity.service_id,
            candidate_service_name=identity.name,
            limitation_code=LimitationCode.DEPLOYMENT_IDENTITY_CONFLICT,
            evidence_refs=base_evidence,
        )

    return _WorkloadScopedOutcome(
        workload=workload,
        outcome="candidate",
        candidate_service_id=identity.service_id,
        candidate_service_name=identity.name,
        limitation_code=None,
        evidence_refs=base_evidence,
    )


def resolve_path_c(
    *,
    observations: Sequence[RuntimeIdentityObservationRow],
    observation_context: ObservationContextRef,
    lookup_pods_by_uid: Callable[[str], Sequence[CapturedPodRow]],
    lookup_workload_ids_owning_pod: Callable[[str], Sequence[WorkloadOwnershipRow]],
    resolve_workload: Callable[[str], CurrentKubernetesWorkload | None],
    declared_service_candidates: Sequence[DeclaredServiceCandidate],
    service_aliases: dict[str, str],
    lookup_declared_service: Callable[[str], DeclaredServiceIdentity | None],
    snapshot_id: str,
    context_id: str,
) -> PathResolutionResult:
    """Spec §9: for every persisted runtime identity observation, resolve its Pod UID through I2's
    owner chain to a current Workload (`_evaluate_observation`), then reduce per Workload group
    (spec §10.5: multiple distinct declared Services satisfying one Path C runtime identity is
    `AMBIGUOUS`, never `CONFLICT` - deliberately different from Path A/B's own multi-value
    `CONFLICT` branch). An observation that never resolves to a Workload at all gets its own
    `"otel:<observation-id>"` group immediately (`_evaluate_observation` already returns a
    standalone `DeploymentResolution` for those cases). `resolve_workload` is the exact same
    callable type Path B already takes (`deployment_repository.read_current_kubernetes_workload`).
    """
    resolutions: list[DeploymentResolution] = []
    claims: list[DeploymentClaim] = []
    scoped: dict[str, list[_WorkloadScopedOutcome]] = defaultdict(list)

    for obs in observations:
        outcome = _evaluate_observation(
            obs=obs,
            lookup_pods_by_uid=lookup_pods_by_uid,
            lookup_workload_ids_owning_pod=lookup_workload_ids_owning_pod,
            resolve_workload=resolve_workload,
            declared_service_candidates=declared_service_candidates,
            service_aliases=service_aliases,
            lookup_declared_service=lookup_declared_service,
            observation_context=observation_context,
            snapshot_id=snapshot_id,
            context_id=context_id,
        )
        if isinstance(outcome, DeploymentResolution):
            resolutions.append(outcome)
        else:
            scoped[outcome.workload.workload_id].append(outcome)

    for workload_id in sorted(scoped):
        group = scoped[workload_id]
        workload_ref = _workload_ref(group[0].workload)
        group_key = compute_deployment_group_key(workload_id=workload_id)
        resolution_id = compute_deployment_resolution_id(
            snapshot_id=snapshot_id, context_id=context_id, group_key=group_key
        )
        # PR #220 review (round 2): evidence for every outcome below except the terminal
        # all-unresolved case is built only from "applicable" outcomes (candidate/conflict - i.e.
        # observations that already passed §9.7's applicability check) - never from an "unresolved"
        # sibling in the same Workload group, which may be unresolved *because it wasn't applicable
        # at all* (wrong environment/window) and must not silently support or taint a claim it was
        # never actually part of. The full-group union is reserved for the one case where nothing
        # succeeded and there's nothing better to surface.
        all_evidence = sorted({ref for outcome in group for ref in outcome.evidence_refs})
        applicable = [outcome for outcome in group if outcome.outcome in ("candidate", "conflict")]
        applicable_evidence = sorted(
            {ref for outcome in applicable for ref in outcome.evidence_refs}
        )

        conflicting = [outcome for outcome in group if outcome.outcome == "conflict"]
        if conflicting:
            # §13.3: `candidate_service_ids` names every Service id "named or exactly resolved by
            # applicable paths in that group" - not only the ones that directly conflicted. A clean
            # candidate sibling (e.g. Service B) must still appear here even though the overall
            # status is CONFLICT because of a *different* observation's own contradiction (e.g.
            # Service A) - §13.4's cross-Service-projection visibility depends on it (PR #220
            # review, round 3).
            candidate_ids = sorted(
                {o.candidate_service_id for o in applicable if o.candidate_service_id is not None}
            )
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.CONFLICT,
                    service_id=None,
                    candidate_service_ids=candidate_ids,
                    supporting_methods=[],
                    supporting_evidence_refs=[],
                    conflicting_evidence_refs=applicable_evidence,
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_CONFLICT],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
            continue

        candidate_names = {
            o.candidate_service_id: o.candidate_service_name
            for o in group
            if o.outcome == "candidate" and o.candidate_service_id is not None
        }
        candidate_ids = sorted(candidate_names)

        if len(candidate_ids) > 1:
            # §10.5: multiple distinct declared Services satisfying one Path C runtime identity is
            # always AMBIGUOUS, never CONFLICT.
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.AMBIGUOUS,
                    service_id=None,
                    candidate_service_ids=candidate_ids,
                    supporting_methods=[],
                    supporting_evidence_refs=applicable_evidence,
                    conflicting_evidence_refs=[],
                    limitation_codes=[LimitationCode.DEPLOYMENT_IDENTITY_AMBIGUOUS],
                    claim_id=None,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
            continue

        if len(candidate_ids) == 1:
            [service_id] = candidate_ids
            service_name = candidate_names[service_id]
            # every "candidate" outcome carries its DeclaredServiceIdentity's (non-null) name
            assert service_name is not None
            claim = _resolved_claim(
                service_id=service_id,
                service_name=service_name,
                workload_ref=workload_ref,
                method=DeploymentResolutionMethod.RESOLVED_OBSERVED,
                evidence_refs=applicable_evidence,
            )
            claims.append(claim)
            resolutions.append(
                DeploymentResolution(
                    resolution_id=resolution_id,
                    workload=workload_ref,
                    status=DeploymentResolutionStatus.RESOLVED_OBSERVED,
                    service_id=service_id,
                    candidate_service_ids=[service_id],
                    supporting_methods=[DeploymentResolutionMethod.RESOLVED_OBSERVED],
                    supporting_evidence_refs=applicable_evidence,
                    conflicting_evidence_refs=[],
                    limitation_codes=[],
                    claim_id=claim.claim_id,
                    reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                    reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
                )
            )
            continue

        # No candidate and no conflict: every group member is workload-scoped but non-applicable
        # or Service-identity-unresolved. Nothing succeeded, so the full group's evidence (not just
        # "applicable_evidence", which is empty here by construction) is surfaced rather than hidden.
        limitation_codes = sorted(
            {o.limitation_code for o in group if o.limitation_code is not None},
            key=lambda code: code.value,
        )
        resolutions.append(
            DeploymentResolution(
                resolution_id=resolution_id,
                workload=workload_ref,
                status=DeploymentResolutionStatus.UNRESOLVED,
                service_id=None,
                candidate_service_ids=[],
                supporting_methods=[],
                supporting_evidence_refs=all_evidence,
                conflicting_evidence_refs=[],
                limitation_codes=limitation_codes,
                claim_id=None,
                reconciliation_rule_id=DEPLOYMENT_RECONCILIATION_RULE_ID,
                reconciliation_rule_version=_RECONCILIATION_RULE_VERSION,
            )
        )

    return PathResolutionResult(resolutions=resolutions, claims=claims)
