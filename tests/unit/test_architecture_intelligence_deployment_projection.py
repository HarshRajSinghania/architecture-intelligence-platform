from datetime import UTC, datetime

import pytest

from app.architecture_intelligence.contracts import (
    DEPLOYMENT_RECONCILIATION_RULE_ID,
    DeploymentResolutionMethod,
    DeploymentResolutionStatus,
    LimitationCode,
    WorkloadKind,
)
from app.architecture_intelligence.deployment_projection import (
    CapturedPodRow,
    CurrentKubernetesWorkload,
    DeclaredServiceIdentity,
    RuntimeIdentityObservationRow,
    WorkloadContribution,
    WorkloadOwnershipRow,
    compute_deployment_claim_id,
    compute_deployment_group_key,
    compute_deployment_resolution_id,
    compute_service_workload_mapping_evidence_id,
    resolve_path_a,
    resolve_path_b,
    resolve_path_c,
)
from app.architecture_intelligence.observation_context import build_observation_context_ref
from app.sources.service_workload_mapping import (
    ServiceWorkloadMappingDocument,
    ServiceWorkloadMappingEntry,
)
from app.telemetry.service_resolver import DeclaredServiceCandidate

SNAPSHOT_ID = "aip:snapshot:v1:" + "a" * 64
CONTEXT_ID = "aip:observation-context:v1:" + "b" * 64


def _workload(
    workload_id="workload:deploy-1",
    kind="Deployment",
    namespace="checkout",
    name="checkout",
    contributions=(),
):
    return CurrentKubernetesWorkload(
        workload_id=workload_id,
        workload_kind=kind,
        namespace=namespace,
        name=name,
        contributions=contributions,
    )


def _service_lookup(services: dict[str, str]):
    return lambda service_id: services.get(service_id)


# ---------------------------------------------------------------------------------------------
# Id/key formula unit tests
# ---------------------------------------------------------------------------------------------


def test_compute_deployment_claim_id_is_deterministic_and_excludes_evidence_method():
    claim_id_1 = compute_deployment_claim_id(service_id="service:checkout", workload_id="w1")
    claim_id_2 = compute_deployment_claim_id(service_id="service:checkout", workload_id="w1")
    assert claim_id_1 == claim_id_2
    assert claim_id_1.startswith("aip:claim:v1:")


def test_compute_deployment_claim_id_differs_by_service_or_workload():
    base = compute_deployment_claim_id(service_id="service:checkout", workload_id="w1")
    different_service = compute_deployment_claim_id(service_id="service:other", workload_id="w1")
    different_workload = compute_deployment_claim_id(
        service_id="service:checkout", workload_id="w2"
    )
    assert len({base, different_service, different_workload}) == 3


def test_compute_deployment_group_key_workload_branch():
    assert compute_deployment_group_key(workload_id="w1") == "workload:w1"


def test_compute_deployment_group_key_rejects_both_branches_given_together():
    # PR #215 review (Copilot): the docstring says exactly one branch must be given - assert that's
    # now enforced rather than silently preferring workload_id.
    with pytest.raises(ValueError):
        compute_deployment_group_key(
            workload_id="w1", mapping_artifact_id="a", mapping_artifact_revision="b", mapping_id="c"
        )


def test_compute_deployment_group_key_rejects_neither_branch_given():
    with pytest.raises(ValueError):
        compute_deployment_group_key()


def test_compute_deployment_group_key_mapping_branch_distinct_tuples():
    # §21.2: distinct tuples ("a", "b:c", "d") and ("a:b", "c", "d") must produce distinct keys -
    # exercises the canonical-JSON (not delimiter-concatenation) requirement directly.
    key_1 = compute_deployment_group_key(
        mapping_artifact_id="a", mapping_artifact_revision="b:c", mapping_id="d"
    )
    key_2 = compute_deployment_group_key(
        mapping_artifact_id="a:b", mapping_artifact_revision="c", mapping_id="d"
    )
    assert key_1 != key_2


def test_compute_deployment_resolution_id_deterministic_and_context_sensitive():
    key = compute_deployment_group_key(workload_id="w1")
    id_1 = compute_deployment_resolution_id(
        snapshot_id=SNAPSHOT_ID, context_id=CONTEXT_ID, group_key=key
    )
    id_2 = compute_deployment_resolution_id(
        snapshot_id=SNAPSHOT_ID, context_id=CONTEXT_ID, group_key=key
    )
    assert id_1 == id_2
    assert id_1.startswith("aip:deployment-resolution:v1:")
    other_snapshot = compute_deployment_resolution_id(
        snapshot_id="aip:snapshot:v1:" + "c" * 64, context_id=CONTEXT_ID, group_key=key
    )
    assert other_snapshot != id_1
    # §21.7: resolution_id must also change when only observation_context.context_id changes.
    other_context = compute_deployment_resolution_id(
        snapshot_id=SNAPSHOT_ID, context_id="aip:observation-context:v1:" + "d" * 64, group_key=key
    )
    assert other_context != id_1
    assert other_context != other_snapshot


def test_compute_service_workload_mapping_evidence_id_distinct_delimiter_tuples():
    id_1 = compute_service_workload_mapping_evidence_id(
        artifact_id="a", artifact_revision="b:c", content_digest="d", mapping_id="e"
    )
    id_2 = compute_service_workload_mapping_evidence_id(
        artifact_id="a:b", artifact_revision="c", content_digest="d", mapping_id="e"
    )
    assert id_1 != id_2
    assert id_1.startswith("urn:aip:service-workload-mapping-evidence:v1:")


def test_compute_service_workload_mapping_evidence_id_changes_with_content_digest():
    # §21.2: "mapping-content change changes reconciliation context/snapshot" - the digest-changes
    # -> evidence-id-changes primitive.
    id_1 = compute_service_workload_mapping_evidence_id(
        artifact_id="a", artifact_revision="rev", content_digest="digest-1", mapping_id="m"
    )
    id_2 = compute_service_workload_mapping_evidence_id(
        artifact_id="a", artifact_revision="rev", content_digest="digest-2", mapping_id="m"
    )
    assert id_1 != id_2


# ---------------------------------------------------------------------------------------------
# Path A (spec §21.1)
# ---------------------------------------------------------------------------------------------


def test_path_a_valid_annotation_for_each_supported_kind():
    workloads = [
        _workload(
            workload_id="w-deploy",
            kind="Deployment",
            contributions=(
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev1",)),
            ),
        ),
        _workload(
            workload_id="w-sts",
            kind="StatefulSet",
            contributions=(
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev2",)),
            ),
        ),
        _workload(
            workload_id="w-ds",
            kind="DaemonSet",
            contributions=(
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev3",)),
            ),
        ),
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert len(result.resolutions) == 3
    assert len(result.claims) == 3
    for resolution in result.resolutions:
        assert resolution.status == DeploymentResolutionStatus.RESOLVED_EXPLICIT
        assert resolution.service_id == "service:checkout"
        assert resolution.supporting_methods == [DeploymentResolutionMethod.RESOLVED_EXPLICIT]
        assert resolution.reconciliation_rule_id == DEPLOYMENT_RECONCILIATION_RULE_ID
    assert {r.workload.workload_kind for r in result.resolutions} == {
        WorkloadKind.DEPLOYMENT,
        WorkloadKind.STATEFULSET,
        WorkloadKind.DAEMONSET,
    }


def test_path_a_missing_annotation_produces_no_resolution():
    workloads = [
        _workload(contributions=(WorkloadContribution(annotation=None, evidence_refs=("ev1",)),))
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert result.resolutions == []
    assert result.claims == []


def test_path_a_annotation_naming_a_missing_service_is_unresolved():
    workloads = [
        _workload(
            contributions=(
                WorkloadContribution(annotation="service:ghost", evidence_refs=("ev1",)),
            )
        )
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.service_id is None
    assert resolution.candidate_service_ids == ["service:ghost"]
    assert resolution.claim_id is None
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED]
    assert result.claims == []


def test_path_a_two_contributions_same_annotation_agree():
    workloads = [
        _workload(
            contributions=(
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev1",)),
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev2",)),
            )
        )
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_EXPLICIT
    assert resolution.supporting_evidence_refs == ["ev1", "ev2"]


def test_path_a_two_contributions_different_annotations_conflict():
    workloads = [
        _workload(
            contributions=(
                WorkloadContribution(annotation="service:checkout", evidence_refs=("ev1",)),
                WorkloadContribution(annotation="service:other", evidence_refs=("ev2",)),
            )
        )
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup(
            {"service:checkout": "checkout", "service:other": "other"}
        ),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT
    assert resolution.candidate_service_ids == ["service:checkout", "service:other"]
    assert resolution.conflicting_evidence_refs == ["ev1", "ev2"]
    assert resolution.claim_id is None
    assert result.claims == []


def test_path_a_annotation_exact_case_requirement():
    # A differently-cased annotation is a distinct string, never folded to match.
    workloads = [
        _workload(
            contributions=(
                WorkloadContribution(annotation="service:Checkout", evidence_refs=("ev1",)),
            )
        )
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.candidate_service_ids == ["service:Checkout"]


def test_path_a_annotation_similarity_only_is_never_fuzzy_matched():
    workloads = [
        _workload(
            contributions=(
                WorkloadContribution(annotation="service:checkout-v2", evidence_refs=("ev1",)),
            )
        )
    ]
    result = resolve_path_a(
        workloads=workloads,
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.candidate_service_ids == ["service:checkout-v2"]


# ---------------------------------------------------------------------------------------------
# Path B (spec §21.2)
# ---------------------------------------------------------------------------------------------

CURRENT_SOURCE = ("checkout-cluster", "599e90a5-7ab8-426f-807f-92a65dcc8822")


def _mapping_document(
    entries, artifact_id="v0.5.0-service-workload-identities", revision="v1", digest="digest-1"
):
    return ServiceWorkloadMappingDocument(
        artifact_id=artifact_id,
        artifact_revision=revision,
        locator="mappings.yaml",
        content_digest=digest,
        entries=tuple(entries),
    )


def _mapping_entry(
    mapping_id="checkout-runtime",
    service_id="service:checkout",
    kubernetes_source_id="checkout-cluster",
    cluster_uid="599e90a5-7ab8-426f-807f-92a65dcc8822",
    api_group="apps",
    workload_kind="Deployment",
    namespace="checkout",
    name="checkout",
):
    return ServiceWorkloadMappingEntry(
        mapping_id=mapping_id,
        service_id=service_id,
        kubernetes_source_id=kubernetes_source_id,
        cluster_uid=cluster_uid,
        api_group=api_group,
        workload_kind=workload_kind,
        namespace=namespace,
        name=name,
    )


def _workload_resolver(workloads_by_entity_id: dict[str, CurrentKubernetesWorkload]):
    return lambda entity_id: workloads_by_entity_id.get(entity_id)


def test_path_b_valid_mapping_for_each_supported_kind():
    entries = [
        _mapping_entry(mapping_id="a", workload_kind="Deployment", name="deploy"),
        _mapping_entry(mapping_id="b", workload_kind="StatefulSet", name="sts"),
        _mapping_entry(mapping_id="c", workload_kind="DaemonSet", name="ds"),
    ]
    document = _mapping_document(entries)

    from app.sources.identity import kubernetes_logical_resource_id

    workloads_by_entity_id = {}
    for entry in entries:
        entity_id = kubernetes_logical_resource_id(
            cluster_uid=entry.cluster_uid,
            api_group=entry.api_group,
            kind=entry.workload_kind,
            namespace=entry.namespace,
            name=entry.name,
        )
        workloads_by_entity_id[entity_id] = _workload(
            workload_id=entity_id,
            kind=entry.workload_kind,
            namespace=entry.namespace,
            name=entry.name,
        )

    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver(workloads_by_entity_id),
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert len(result.resolutions) == 3
    assert len(result.claims) == 3
    for resolution in result.resolutions:
        assert resolution.status == DeploymentResolutionStatus.RESOLVED_CONFIGURED
        assert resolution.supporting_methods == [DeploymentResolutionMethod.RESOLVED_CONFIGURED]


def test_path_b_mapping_entry_ordering_has_no_effect_on_resolution():
    """§21.7 determinism: reordering `document.entries` must not change `resolve_path_b`'s output -
    the function already sorts by workload_id/mapping_id internally (see its own docstring), so this
    proves that in practice rather than by inspection alone."""
    entries = [
        _mapping_entry(mapping_id="a", name="checkout", service_id="service:checkout"),
        _mapping_entry(mapping_id="b", name="billing", service_id="service:billing"),
        _mapping_entry(mapping_id="c", name="ghost", service_id="service:ghost"),
    ]

    from app.sources.identity import kubernetes_logical_resource_id

    workloads_by_entity_id = {}
    for entry in entries[:2]:
        entity_id = kubernetes_logical_resource_id(
            cluster_uid=entry.cluster_uid,
            api_group=entry.api_group,
            kind=entry.workload_kind,
            namespace=entry.namespace,
            name=entry.name,
        )
        workloads_by_entity_id[entity_id] = _workload(
            workload_id=entity_id, namespace=entry.namespace, name=entry.name
        )

    def _run(ordered_entries):
        return resolve_path_b(
            document=_mapping_document(ordered_entries),
            configured_kubernetes_sources=[CURRENT_SOURCE],
            resolve_workload=_workload_resolver(workloads_by_entity_id),
            lookup_service_name=_service_lookup(
                {"service:checkout": "checkout", "service:billing": "billing"}
            ),
            snapshot_id=SNAPSHOT_ID,
            context_id=CONTEXT_ID,
        )

    forward = _run(entries)
    reversed_result = _run(list(reversed(entries)))
    assert forward == reversed_result
    assert len(forward.resolutions) == 3


def test_path_b_mapping_to_missing_service_is_unresolved():
    entry = _mapping_entry()
    document = _mapping_document([entry])

    from app.sources.identity import kubernetes_logical_resource_id

    entity_id = kubernetes_logical_resource_id(
        cluster_uid=entry.cluster_uid,
        api_group=entry.api_group,
        kind=entry.workload_kind,
        namespace=entry.namespace,
        name=entry.name,
    )
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver({entity_id: _workload(workload_id=entity_id)}),
        lookup_service_name=_service_lookup({}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is not None
    assert resolution.candidate_service_ids == ["service:checkout"]
    assert result.claims == []


def test_path_b_mapping_to_missing_workload_is_unresolved_with_null_workload():
    document = _mapping_document([_mapping_entry()])
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver({}),
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None
    assert result.claims == []


def test_path_b_wrong_configured_kubernetes_source_id_is_unresolved_with_null_workload():
    document = _mapping_document([_mapping_entry(kubernetes_source_id="other-cluster")])
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=lambda entity_id: (_ for _ in ()).throw(
            AssertionError("resolve_workload must not be called for a non-current source")
        ),
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None


def test_path_b_wrong_cluster_uid_is_unresolved_with_null_workload():
    document = _mapping_document([_mapping_entry(cluster_uid="a-different-cluster-uid")])
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=lambda entity_id: (_ for _ in ()).throw(
            AssertionError("resolve_workload must not be called for a non-current source")
        ),
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None


def test_path_b_same_names_different_namespaces_are_independent():
    from app.sources.identity import kubernetes_logical_resource_id

    entry_a = _mapping_entry(mapping_id="a", namespace="ns-a", service_id="service:a")
    entry_b = _mapping_entry(mapping_id="b", namespace="ns-b", service_id="service:b")
    document = _mapping_document([entry_a, entry_b])

    workloads = {}
    for entry in (entry_a, entry_b):
        entity_id = kubernetes_logical_resource_id(
            cluster_uid=entry.cluster_uid,
            api_group=entry.api_group,
            kind=entry.workload_kind,
            namespace=entry.namespace,
            name=entry.name,
        )
        workloads[entity_id] = _workload(workload_id=entity_id, namespace=entry.namespace)

    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver(workloads),
        lookup_service_name=_service_lookup({"service:a": "a", "service:b": "b"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert len(result.resolutions) == 2
    assert {r.status for r in result.resolutions} == {
        DeploymentResolutionStatus.RESOLVED_CONFIGURED
    }
    assert {r.service_id for r in result.resolutions} == {"service:a", "service:b"}


def test_path_b_same_names_different_clusters_are_independent():
    from app.sources.identity import kubernetes_logical_resource_id

    entry_a = _mapping_entry(
        mapping_id="a",
        kubernetes_source_id="cluster-a",
        cluster_uid="00000000-0000-0000-0000-000000000001",
        service_id="service:a",
    )
    entry_b = _mapping_entry(
        mapping_id="b",
        kubernetes_source_id="cluster-b",
        cluster_uid="00000000-0000-0000-0000-000000000002",
        service_id="service:b",
    )
    document = _mapping_document([entry_a, entry_b])

    workloads = {}
    for entry in (entry_a, entry_b):
        entity_id = kubernetes_logical_resource_id(
            cluster_uid=entry.cluster_uid,
            api_group=entry.api_group,
            kind=entry.workload_kind,
            namespace=entry.namespace,
            name=entry.name,
        )
        workloads[entity_id] = _workload(workload_id=entity_id)

    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[
            ("cluster-a", "00000000-0000-0000-0000-000000000001"),
            ("cluster-b", "00000000-0000-0000-0000-000000000002"),
        ],
        resolve_workload=_workload_resolver(workloads),
        lookup_service_name=_service_lookup({"service:a": "a", "service:b": "b"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert len(result.resolutions) == 2
    assert {r.service_id for r in result.resolutions} == {"service:a", "service:b"}


def test_path_b_two_mappings_same_workload_different_services_conflict():
    from app.sources.identity import kubernetes_logical_resource_id

    entry_a = _mapping_entry(mapping_id="a", service_id="service:checkout")
    entry_b = _mapping_entry(mapping_id="b", service_id="service:other")
    document = _mapping_document([entry_a, entry_b])

    entity_id = kubernetes_logical_resource_id(
        cluster_uid=entry_a.cluster_uid,
        api_group=entry_a.api_group,
        kind=entry_a.workload_kind,
        namespace=entry_a.namespace,
        name=entry_a.name,
    )
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver({entity_id: _workload(workload_id=entity_id)}),
        lookup_service_name=_service_lookup(
            {"service:checkout": "checkout", "service:other": "other"}
        ),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT
    assert resolution.candidate_service_ids == ["service:checkout", "service:other"]
    assert result.claims == []


def test_path_b_evidence_id_reflects_artifact_identity_and_mapping_id():
    from app.sources.identity import kubernetes_logical_resource_id

    entry = _mapping_entry()
    document = _mapping_document([entry], artifact_id="art-1", revision="rev-1", digest="digest-1")
    entity_id = kubernetes_logical_resource_id(
        cluster_uid=entry.cluster_uid,
        api_group=entry.api_group,
        kind=entry.workload_kind,
        namespace=entry.namespace,
        name=entry.name,
    )
    result = resolve_path_b(
        document=document,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=_workload_resolver({entity_id: _workload(workload_id=entity_id)}),
        lookup_service_name=_service_lookup({"service:checkout": "checkout"}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    [resolution] = result.resolutions
    expected_evidence_id = compute_service_workload_mapping_evidence_id(
        artifact_id="art-1",
        artifact_revision="rev-1",
        content_digest="digest-1",
        mapping_id="checkout-runtime",
    )
    assert resolution.supporting_evidence_refs == [expected_evidence_id]


def test_path_b_with_no_configured_artifact_produces_nothing():
    # spec §8.1: "Path B uses one local, versioned mapping artifact" - `document=None` (no artifact
    # configured) must produce no resolutions/claims at all, not an empty-but-present group.
    result = resolve_path_b(
        document=None,
        configured_kubernetes_sources=[CURRENT_SOURCE],
        resolve_workload=lambda entity_id: (_ for _ in ()).throw(
            AssertionError("resolve_workload must not be called with no configured artifact")
        ),
        lookup_service_name=_service_lookup({}),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )
    assert result.resolutions == []
    assert result.claims == []


# ---------------------------------------------------------------------------------------------
# compute_deployment_group_key - the new "otel:" branch
# ---------------------------------------------------------------------------------------------


def test_compute_deployment_group_key_otel_branch():
    assert compute_deployment_group_key(otel_observation_id="obs-1") == "otel:obs-1"


def test_compute_deployment_group_key_rejects_workload_and_otel_together():
    with pytest.raises(ValueError):
        compute_deployment_group_key(workload_id="w1", otel_observation_id="obs-1")


def test_compute_deployment_group_key_rejects_mapping_and_otel_together():
    with pytest.raises(ValueError):
        compute_deployment_group_key(
            mapping_artifact_id="a",
            mapping_artifact_revision="b",
            mapping_id="c",
            otel_observation_id="obs-1",
        )


# ---------------------------------------------------------------------------------------------
# Path C (spec §9, §10.5, §21.3)
# ---------------------------------------------------------------------------------------------

POD_UID = "pod-uid-1"
POD_ID = "pod:1"
WORKLOAD_ID = "workload:deploy-1"
SERVICE_ID = "service:checkout"

WINDOW_START = datetime(2026, 9, 19, 0, 0, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 9, 19, 23, 59, 59, tzinfo=UTC)
IN_WINDOW = datetime(2026, 9, 19, 12, 0, 0, tzinfo=UTC)
BEFORE_WINDOW = datetime(2026, 9, 18, 12, 0, 0, tzinfo=UTC)
AFTER_WINDOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)
IN_WINDOW_STR = "2026-09-19T12:00:00Z"
BEFORE_WINDOW_STR = "2026-09-18T12:00:00Z"
AFTER_WINDOW_STR = "2026-09-20T12:00:00Z"


def _observation_context(environment="prod"):
    return build_observation_context_ref(environment, WINDOW_START, WINDOW_END)


def _pod_row(**overrides):
    defaults = {
        "pod_id": POD_ID,
        "pod_name": "checkout-api-abc123",
        "pod_namespace": "checkout",
        "cluster_uid": "cluster-1",
        "captured_at": IN_WINDOW_STR,
        "evidence_refs": ("ev-pod",),
    }
    defaults.update(overrides)
    return CapturedPodRow(**defaults)


def _observation_row(**overrides):
    defaults = {
        "id": "runtime-identity:otel:prod:2026-09-19:abc123",
        "service_name": "checkout",
        "service_namespace": None,
        "service_version": None,
        "environment": "prod",
        "k8s_pod_uid": POD_UID,
        "k8s_pod_name": None,
        "k8s_namespace_name": None,
        "k8s_cluster_uid": None,
        "k8s_deployment_name": None,
        "k8s_statefulset_name": None,
        "k8s_daemonset_name": None,
        "last_seen": IN_WINDOW,
        "conflicting_consistency_attributes": (),
    }
    defaults.update(overrides)
    return RuntimeIdentityObservationRow(**defaults)


def _declared_candidate(id=SERVICE_ID, name="checkout", namespace=None):
    return DeclaredServiceCandidate(id, name, namespace)


def _default_declared_identities():
    return {
        SERVICE_ID: DeclaredServiceIdentity(
            service_id=SERVICE_ID, name="checkout", namespace=None, version=None
        )
    }


def _run_path_c(
    observations,
    *,
    pods_by_uid=None,
    owners_by_pod=None,
    workloads=None,
    declared_candidates=None,
    aliases=None,
    declared_identities=None,
    observation_context=None,
):
    pods_by_uid = pods_by_uid if pods_by_uid is not None else {POD_UID: [_pod_row()]}
    owners_by_pod = (
        owners_by_pod
        if owners_by_pod is not None
        else {POD_ID: [WorkloadOwnershipRow(workload_id=WORKLOAD_ID, evidence_refs=("ev-owns",))]}
    )
    workloads = (
        workloads
        if workloads is not None
        else {
            WORKLOAD_ID: _workload(workload_id=WORKLOAD_ID, kind="Deployment", name="checkout-api")
        }
    )
    declared_candidates = (
        declared_candidates if declared_candidates is not None else [_declared_candidate()]
    )
    declared_identities = (
        declared_identities if declared_identities is not None else _default_declared_identities()
    )
    aliases = aliases if aliases is not None else {}
    return resolve_path_c(
        observations=observations,
        observation_context=observation_context or _observation_context(),
        lookup_pods_by_uid=lambda uid: pods_by_uid.get(uid, []),
        lookup_workload_ids_owning_pod=lambda pod_id: owners_by_pod.get(pod_id, []),
        resolve_workload=lambda wid: workloads.get(wid),
        declared_service_candidates=declared_candidates,
        service_aliases=aliases,
        lookup_declared_service=lambda sid: declared_identities.get(sid),
        snapshot_id=SNAPSHOT_ID,
        context_id=CONTEXT_ID,
    )


def test_path_c_resolves_via_exact_namespace_and_name():
    result = _run_path_c(
        [_observation_row(service_namespace="checkout")],
        declared_candidates=[_declared_candidate(namespace="checkout")],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace="checkout", version=None
            )
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED
    assert resolution.service_id == SERVICE_ID
    assert resolution.supporting_methods == [DeploymentResolutionMethod.RESOLVED_OBSERVED]
    [claim] = result.claims
    assert claim.claim_id == resolution.claim_id


def test_path_c_resolves_via_unique_exact_name():
    result = _run_path_c([_observation_row()])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED
    assert resolution.service_id == SERVICE_ID


def test_path_c_resolves_via_configured_alias():
    result = _run_path_c(
        [_observation_row(service_name="checkout-svc")],
        declared_candidates=[],
        aliases={"checkout-svc": SERVICE_ID},
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED
    assert resolution.service_id == SERVICE_ID


def test_path_c_alias_target_missing_is_unresolved():
    result = _run_path_c(
        [_observation_row(service_name="unknown-svc")], declared_candidates=[], aliases={}
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is not None
    assert result.claims == []


def test_path_c_service_resolves_observed_only_is_unresolved():
    # The "critical trap": resolve_service's own tiering reports DECLARED (a :Service node with
    # this name exists), but the authoritative owner_source_ids re-check says it's not currently
    # declared (a stale OBSERVED_ONLY stub) - must not be treated as resolved.
    result = _run_path_c([_observation_row()], declared_identities={})
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is not None
    assert result.claims == []


def test_path_c_missing_pod_uid_is_unresolved_with_no_workload():
    observation = _observation_row(k8s_pod_uid=None)
    result = _run_path_c([observation])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_IDENTITY_UNRESOLVED]
    # PR #220 review: the standalone group's only universally-available evidence is the
    # observation itself (§13.1 names the group after "the OTel runtime-identity evidence id";
    # §13.5 requires a non-resolved outcome to retain its own evidence) - never dropped even when
    # there's no Pod/owner-chain evidence to union it with.
    assert resolution.supporting_evidence_refs == [observation.id]
    assert result.claims == []


def test_path_c_unknown_pod_uid_is_unresolved_with_no_workload():
    observation = _observation_row()
    result = _run_path_c([observation], pods_by_uid={})
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None
    assert resolution.supporting_evidence_refs == [observation.id]


def test_path_c_stale_pod_uid_is_unresolved_with_no_workload():
    # A replaced Pod's row is genuinely gone from the current graph - indistinguishable from an
    # unknown UID, which is correct (spec §21.5's Pod-replacement guarantee).
    observation = _observation_row()
    result = _run_path_c([observation], pods_by_uid={POD_UID: []})
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None
    assert resolution.supporting_evidence_refs == [observation.id]


def test_path_c_pod_uid_resolves_ambiguously():
    observation = _observation_row()
    result = _run_path_c(
        [observation],
        pods_by_uid={
            POD_UID: [
                _pod_row(pod_id="pod:1", evidence_refs=("ev-pod-1",)),
                _pod_row(pod_id="pod:2", evidence_refs=("ev-pod-2",)),
            ]
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.AMBIGUOUS
    assert resolution.workload is None
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_IDENTITY_AMBIGUOUS]
    assert resolution.supporting_evidence_refs == sorted(["ev-pod-1", "ev-pod-2", observation.id])


def test_path_c_owner_chain_unresolved():
    observation = _observation_row()
    result = _run_path_c([observation], owners_by_pod={})
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.workload is None
    assert resolution.supporting_evidence_refs == sorted(["ev-pod", observation.id])


def test_path_c_owner_chain_ambiguous():
    observation = _observation_row()
    result = _run_path_c(
        [observation],
        owners_by_pod={
            POD_ID: [
                WorkloadOwnershipRow(workload_id="workload:a"),
                WorkloadOwnershipRow(workload_id="workload:b"),
            ]
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.AMBIGUOUS
    assert resolution.workload is None
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_IDENTITY_AMBIGUOUS]
    assert resolution.supporting_evidence_refs == sorted(["ev-pod", observation.id])


@pytest.mark.parametrize(
    "field",
    ["k8s_namespace_name", "k8s_cluster_uid", "k8s_pod_name"],
)
def test_path_c_consistency_attribute_agrees(field):
    values = {
        "k8s_namespace_name": "checkout",
        "k8s_cluster_uid": "cluster-1",
        "k8s_pod_name": "checkout-api-abc123",
    }
    result = _run_path_c([_observation_row(**{field: values[field]})])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


@pytest.mark.parametrize(
    "field",
    ["k8s_namespace_name", "k8s_cluster_uid", "k8s_pod_name"],
)
def test_path_c_consistency_attribute_disagrees_is_conflict(field):
    result = _run_path_c([_observation_row(**{field: "something-else"})])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_IDENTITY_CONFLICT]
    assert result.claims == []


def test_path_c_workload_name_consistency_attribute_agrees():
    result = _run_path_c([_observation_row(k8s_deployment_name="checkout-api")])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


def test_path_c_workload_name_consistency_attribute_disagrees_same_kind():
    result = _run_path_c([_observation_row(k8s_deployment_name="something-else")])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT


def test_path_c_workload_name_consistency_attribute_disagrees_cross_kind():
    # A non-null attribute naming a *different* Workload kind than the one actually resolved is
    # unconditionally contradictory, regardless of its own value (spec §9.6).
    result = _run_path_c([_observation_row(k8s_statefulset_name="checkout-api")])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT


def test_path_c_service_version_agrees():
    result = _run_path_c(
        [_observation_row(service_version="v1")],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace=None, version="v1"
            )
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


def test_path_c_service_version_disagrees():
    result = _run_path_c(
        [_observation_row(service_version="v2")],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace=None, version="v1"
            )
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT


def test_path_c_service_version_only_one_side_present_is_not_a_limitation():
    result = _run_path_c(
        [_observation_row(service_version="v2")],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace=None, version=None
            )
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


def test_path_c_conflicting_consistency_attributes_from_merge_is_conflict():
    # §9.4: a non-empty conflicting_consistency_attributes (already flagged during slice 2's own
    # bucket merge) is treated identically to a directly observed contradiction.
    result = _run_path_c([_observation_row(conflicting_consistency_attributes=("k8s_pod_name",))])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT


def test_path_c_last_seen_inside_window():
    result = _run_path_c([_observation_row(last_seen=IN_WINDOW)])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


def test_path_c_last_seen_before_window():
    result = _run_path_c([_observation_row(last_seen=BEFORE_WINDOW)])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH]


def test_path_c_last_seen_after_window():
    result = _run_path_c([_observation_row(last_seen=AFTER_WINDOW)])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH]


def test_path_c_captured_at_inside_window():
    result = _run_path_c(
        [_observation_row()], pods_by_uid={POD_UID: [_pod_row(captured_at=IN_WINDOW_STR)]}
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED


def test_path_c_captured_at_before_window():
    result = _run_path_c(
        [_observation_row()], pods_by_uid={POD_UID: [_pod_row(captured_at=BEFORE_WINDOW_STR)]}
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH]


def test_path_c_captured_at_after_window():
    result = _run_path_c(
        [_observation_row()], pods_by_uid={POD_UID: [_pod_row(captured_at=AFTER_WINDOW_STR)]}
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH]


def test_path_c_captured_at_without_offset_is_temporal_mismatch():
    # Offset-less capturedAt parses to a naive datetime; comparing it with the
    # offset-aware observation window must not raise TypeError.
    result = _run_path_c(
        [_observation_row()],
        pods_by_uid={POD_UID: [_pod_row(captured_at="2026-09-19T12:00:00")]},
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_TEMPORAL_MISMATCH]


def test_path_c_environment_absent():
    result = _run_path_c([_observation_row(environment=None)])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_EVIDENCE_INCOMPLETE]


def test_path_c_environment_mismatch():
    result = _run_path_c([_observation_row(environment="staging")])
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.UNRESOLVED
    assert resolution.limitation_codes == [LimitationCode.DEPLOYMENT_ENVIRONMENT_MISMATCH]


def test_path_c_environment_exact_match():
    """§21.3's own literal required-case list names this as its own case, distinct from
    `..._absent`/`..._mismatch` above - every other positive Path C test happens to also use a
    matching environment implicitly, but this is the one that names and asserts it directly."""
    result = _run_path_c(
        [_observation_row(environment="prod")],
        observation_context=_observation_context(environment="prod"),
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED
    assert resolution.limitation_codes == []


def test_path_c_multiple_declared_services_is_ambiguous_not_conflict():
    # §10.5: multiple distinct declared Services satisfying one Path C runtime identity is always
    # AMBIGUOUS, never CONFLICT - two distinct Pod UIDs owner-chain-resolving to the SAME Workload,
    # but resolving via resolve_service to two different declared Service ids.
    other_service_id = "service:other"
    result = _run_path_c(
        [
            _observation_row(id="obs-1", k8s_pod_uid="pod-uid-1", service_name="checkout"),
            _observation_row(id="obs-2", k8s_pod_uid="pod-uid-2", service_name="other"),
        ],
        pods_by_uid={
            "pod-uid-1": [_pod_row(pod_id="pod:1")],
            "pod-uid-2": [_pod_row(pod_id="pod:2")],
        },
        owners_by_pod={
            "pod:1": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID)],
            "pod:2": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID)],
        },
        declared_candidates=[
            _declared_candidate(id=SERVICE_ID, name="checkout"),
            _declared_candidate(id=other_service_id, name="other"),
        ],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace=None, version=None
            ),
            other_service_id: DeclaredServiceIdentity(
                service_id=other_service_id, name="other", namespace=None, version=None
            ),
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.AMBIGUOUS
    assert resolution.candidate_service_ids == sorted([SERVICE_ID, other_service_id])
    assert result.claims == []


def test_path_c_non_applicable_observation_does_not_taint_a_resolved_sibling():
    # PR #220 review (round 2): obs A (prod, in-window) is a clean candidate for Workload W; obs B
    # for the SAME Workload is non-applicable (wrong environment) AND carries a directly
    # contradictory consistency attribute. B must never turn the group into CONFLICT, and its
    # evidence must never leak into A's own resolved claim.
    result = _run_path_c(
        [
            _observation_row(id="obs-a", k8s_pod_uid="pod-uid-a"),
            _observation_row(
                id="obs-b",
                k8s_pod_uid="pod-uid-b",
                environment="staging",
                k8s_pod_name="not-the-real-pod-name",
            ),
        ],
        pods_by_uid={
            "pod-uid-a": [_pod_row(pod_id="pod:a", evidence_refs=("ev-pod-a",))],
            "pod-uid-b": [_pod_row(pod_id="pod:b", evidence_refs=("ev-pod-b",))],
        },
        owners_by_pod={
            "pod:a": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID, evidence_refs=("ev-owns-a",))],
            "pod:b": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID, evidence_refs=("ev-owns-b",))],
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.RESOLVED_OBSERVED
    assert resolution.service_id == SERVICE_ID
    assert resolution.supporting_evidence_refs == sorted(["ev-pod-a", "ev-owns-a", "obs-a"])
    for tainted_ref in ("ev-pod-b", "ev-owns-b", "obs-b"):
        assert tainted_ref not in resolution.supporting_evidence_refs
    [claim] = result.claims
    assert claim.evidence_refs == sorted(["ev-pod-a", "ev-owns-a", "obs-a"])


def test_path_c_conflict_candidate_service_ids_include_every_applicable_service():
    # PR #220 review (round 3): §13.3 requires candidate_service_ids to name every Service id
    # "named or exactly resolved by applicable paths in that group," not only the ones that
    # directly conflicted. obs A (applicable, resolves Service A) has a contradictory consistency
    # attribute; obs B (applicable, resolves Service B) is a clean candidate. Overall status is
    # CONFLICT (A's contradiction), but B must still be visible in candidate_service_ids so a
    # Service-B-scoped projection can see the conflict too (§13.4).
    other_service_id = "service:other"
    result = _run_path_c(
        [
            _observation_row(
                id="obs-a",
                k8s_pod_uid="pod-uid-a",
                service_name="checkout",
                k8s_pod_name="not-the-real-pod-name",
            ),
            _observation_row(id="obs-b", k8s_pod_uid="pod-uid-b", service_name="other"),
        ],
        pods_by_uid={
            "pod-uid-a": [_pod_row(pod_id="pod:a")],
            "pod-uid-b": [_pod_row(pod_id="pod:b")],
        },
        owners_by_pod={
            "pod:a": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID)],
            "pod:b": [WorkloadOwnershipRow(workload_id=WORKLOAD_ID)],
        },
        declared_candidates=[
            _declared_candidate(id=SERVICE_ID, name="checkout"),
            _declared_candidate(id=other_service_id, name="other"),
        ],
        declared_identities={
            SERVICE_ID: DeclaredServiceIdentity(
                service_id=SERVICE_ID, name="checkout", namespace=None, version=None
            ),
            other_service_id: DeclaredServiceIdentity(
                service_id=other_service_id, name="other", namespace=None, version=None
            ),
        },
    )
    [resolution] = result.resolutions
    assert resolution.status == DeploymentResolutionStatus.CONFLICT
    assert resolution.candidate_service_ids == sorted([SERVICE_ID, other_service_id])
    assert result.claims == []
