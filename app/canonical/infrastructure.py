"""I2 Draft 0.2 §7.1/§7.2's frozen infrastructure entity/contribution/claim schemas - the Canonical
Model's capacity to carry Kubernetes infrastructure facts (v0.5.0 I2's §3 prerequisite slice, item
6). No adapter populates these yet: that begins at I2 §12 slice 2 (envelope/identity) and slice 3
(the first real Kubernetes adapter). A separate module from `app.canonical.model`, mirroring how
`app.provenance.model` is already its own module - these are a distinct fact category
(infrastructure, not application) from Service/Operation/Queue/Message/Schema/Relation.

§7's invariants are enforced here rather than left to the eventual adapter's good behavior: an
adapter that emits an unsorted evidence list, a `WORKLOAD_EXISTS` claim with an object, or
Service-only fields on a Pod has a real bug, and this repo rejects rather than silently repairing
("unsupported > falsely supported"). Cross-entity referential integrity (do these ids actually
resolve?) belongs to `app.validation.canonical_validation`, which sees the whole merged model.

Field names and shapes here are this PR's own choice where the spec gives only a prose bullet list,
not a schema - §7.1 explicitly delegates this: "The exact Python classes, package layout, graph
labels, and persistence encoding are implementation decisions. They MUST preserve these logical
fields, contribution boundaries, and conflict outcomes."
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.common.encoding import length_delimited, sha256_hex, utf8


class InfrastructureEntityKind(StrEnum):
    """I2 Draft 0.2 §7.1: "I2 adds exactly four internal canonical infrastructure entity kinds.
    They are distinct from all existing application entities." No fifth kind may be added without a
    reviewed specification amendment.
    """

    KUBERNETES_WORKLOAD = "KUBERNETES_WORKLOAD"
    KUBERNETES_POD = "KUBERNETES_POD"
    KUBERNETES_NETWORK_SERVICE = "KUBERNETES_NETWORK_SERVICE"
    KUBERNETES_INGRESS = "KUBERNETES_INGRESS"


class InfrastructureClaimKind(StrEnum):
    """I2 Draft 0.2 §7.2's four canonical infrastructure claim kinds. `WORKLOAD_EXISTS` is unary
    (its `InfrastructureClaim.object_id` is always `None`); the other three are binary.
    """

    WORKLOAD_EXISTS = "WORKLOAD_EXISTS"
    WORKLOAD_OWNS_POD = "WORKLOAD_OWNS_POD"
    NETWORK_SERVICE_SELECTS_WORKLOAD = "NETWORK_SERVICE_SELECTS_WORKLOAD"
    INGRESS_ROUTES_TO_NETWORK_SERVICE = "INGRESS_ROUTES_TO_NETWORK_SERVICE"


KUBERNETES_SOURCE_TYPE = "KUBERNETES"
"""The `Provenance.source_type` a Kubernetes source stamps on its own evidence.

Deliberately not a member of `app.provenance.model.SourceType`: that enum types the *frozen* public
v0.4 evidence schema, and I2 Draft 0.2 §9 (as amended) keeps Kubernetes evidence off every public
surface, so no public payload can ever carry this value - widening the public enum would change a
frozen schema to admit something unreachable. `app.architecture_intelligence.repository` and
`app.api.evidence` filter on exactly this value.
"""

UNARY_CLAIM_KINDS = frozenset({InfrastructureClaimKind.WORKLOAD_EXISTS})
"""I2 Draft 0.2 §7.2: "`WORKLOAD_EXISTS` is a first-class unary claim whose `object_id` is null.
Implementations MUST NOT invent a sentinel entity or self-edge to force it through a binary-relation
representation. The other three claim kinds are binary." """


class KubernetesEvidenceMode(StrEnum):
    """I2 Draft 0.2 §4.1: "Each configured Kubernetes source has exactly one immutable evidence
    mode." Distinct from `app.provenance.model.EvidenceType`'s generic `DECLARED`/`OBSERVED` split -
    both Kubernetes modes are declared-or-captured *infrastructure* evidence, never `OBSERVED` in
    the OTel runtime-observation sense (§4.1: "no claim of API presence or execution" /
    "presence in that bounded capture, not current liveness").
    """

    DECLARED_MANIFEST = "DECLARED_MANIFEST"
    CAPTURED_RESOURCE = "CAPTURED_RESOURCE"


class InfrastructurePort(BaseModel):
    """I2 Draft 0.2 §7.1: `KUBERNETES_NETWORK_SERVICE`'s "sorted list of ports
    (name-or-null, protocol, port)"."""

    name: str | None = None
    protocol: str = Field(min_length=1)
    port: int

    @property
    def sort_key(self) -> tuple[str, str, int]:
        """The §7.1 "sorted list of ports" ordering. A null name orders as the empty string: real
        Kubernetes port names are never empty when present, so this can't collide with a genuine
        name, and it avoids Python's `None`-vs-`str` comparison error entirely.
        """
        return (self.name or "", self.protocol, self.port)


def _check_evidence_refs(evidence_refs: list[str]) -> list[str]:
    """I2 Draft 0.2 §7.2: "Evidence references are non-empty, sorted, duplicate-free, and resolve
    within the selected snapshot." The first three are checkable on one object and enforced here;
    "resolve" needs the whole merged model and is enforced by
    `app.validation.canonical_validation.validate_canonical_model`.

    Rejects rather than normalizes: an adapter emitting unsorted or duplicated evidence has a real
    determinism bug, and silently sorting it here would hide exactly the defect this invariant
    exists to catch.
    """
    if not evidence_refs:
        raise ValueError("evidence_refs must be non-empty (§7.2)")
    if any(not ref for ref in evidence_refs):
        raise ValueError(f"evidence_refs must not contain empty ids: {evidence_refs!r}")
    if len(set(evidence_refs)) != len(evidence_refs):
        raise ValueError(f"evidence_refs must be duplicate-free (§7.2): {evidence_refs!r}")
    if list(evidence_refs) != sorted(evidence_refs):
        raise ValueError(f"evidence_refs must be sorted (§7.2): {evidence_refs!r}")
    return evidence_refs


class InfrastructureEntity(BaseModel):
    """I2 Draft 0.2 §7.1: "Each entity's common logical fields are exactly: id, entity_kind,
    cluster_uid, api_group, resource_kind, namespace, name." `namespace` is the empty string only
    for a cluster-scoped resource, and `api_group` is the empty string for the core API group (§6) -
    which is why those two alone may be empty. `service_type`/`ports` are §7.1's "Additional
    semantic fields" for `KUBERNETES_NETWORK_SERVICE` and MUST NOT be set for any other kind.
    """

    id: str = Field(min_length=1)
    entity_kind: InfrastructureEntityKind
    cluster_uid: str = Field(min_length=1)
    api_group: str
    resource_kind: str = Field(min_length=1)
    namespace: str
    name: str = Field(min_length=1)
    service_type: str | None = None
    ports: list[InfrastructurePort] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_kind_specific_fields(self) -> "InfrastructureEntity":
        is_network_service = self.entity_kind is InfrastructureEntityKind.KUBERNETES_NETWORK_SERVICE
        if not is_network_service and (self.service_type is not None or self.ports):
            raise ValueError(
                "service_type/ports are KUBERNETES_NETWORK_SERVICE-only fields (§7.1), but "
                f"entity {self.id!r} has entity_kind {self.entity_kind.value}"
            )
        port_keys = [port.sort_key for port in self.ports]
        if port_keys != sorted(port_keys):
            raise ValueError(f"ports must be sorted (§7.1) for entity {self.id!r}")
        return self


class InfrastructureContribution(BaseModel):
    """I2 Draft 0.2 §7.1: "Every source-owned entity contribution carries: entity_id,
    source_instance_id, evidence_mode, resource_semantic_digest, evidence_refs, mapping_rule_id,
    mapping_rule_version." `resource_semantic_digest` is an opaque, already-computed digest string
    here - computing it from real Kubernetes resource content is the adapter's job (I2 §12 slice 3),
    not this Canonical Model layer's.

    `captured_resource_uid` is additive (I2 §12 slice 3a review round): §7.1 also states "Two
    current captured contributions that bind the same logical resource to different UIDs are
    likewise incompatible incarnations" - a conflict rule independent of `resource_semantic_digest`
    equality, since §7.1's own digest definition explicitly excludes capture-only UID. `None` for a
    `DECLARED_MANIFEST` contribution, or a `CAPTURED_RESOURCE` one this adapter version predates.

    `service_id_annotation` is additive (I2 §12 slice 6), mirroring `captured_resource_uid`'s own
    precedent: §9 requires the I3 handoff to include "the retained explicit Service-ID annotation as
    unqualified input," but the `architecture-intelligence.io/service-id` annotation value (§5) was
    previously folded only into the opaque `resource_semantic_digest` hash and never itself
    persisted anywhere queryable - a hash cannot be reversed to recover it. `None` for every entity
    kind but `KUBERNETES_WORKLOAD` (§5 retains this annotation only "on supported Workloads"), and
    for a Workload with no such annotation set. I2 never evaluates this value into an AIP Service
    identity (§9: "I2 never evaluates the annotation into an AIP Service identity") - it is retained
    verbatim as unqualified input for I3 to interpret, not acted on here.

    `captured_at` is additive (v0.5.0 I3 slice 4), mirroring the same two precedents above: I3 spec
    §9.7 requires checking "the current I2 CAPTURED_RESOURCE envelope capturedAt" against an
    observation window, but the envelope's own `metadata.capturedAt` (already parsed and validated
    by `app.sources.kubernetes_envelope.KubernetesSourceSnapshotMetadata`) was previously discarded
    after envelope validation and never persisted anywhere queryable. One envelope produces one
    `capturedAt` value shared by every contribution from that source/capture, so this is a per-
    source-snapshot value, not a per-resource one. `None` only for a contribution written by a
    pre-slice-4 adapter version.
    """

    entity_id: str = Field(min_length=1)
    source_instance_id: str = Field(min_length=1)
    evidence_mode: KubernetesEvidenceMode
    resource_semantic_digest: str = Field(min_length=1)
    captured_resource_uid: str | None = None
    service_id_annotation: str | None = None
    captured_at: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    mapping_rule_id: str = Field(min_length=1)
    mapping_rule_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_evidence(self) -> "InfrastructureContribution":
        _check_evidence_refs(self.evidence_refs)
        return self

    @property
    def id(self) -> str:
        """A per-(entity, source) identity, so a contribution is a first-class owned claim that the
        importer's existing node-ownership/reconciliation machinery can diff and expire like any
        other canonical fact. Not a spec-named formula - §7.1 delegates persistence encoding - but
        length-delimited like every other identity hash in this codebase, so two different
        (entity_id, source_instance_id) pairs can never collide.
        """
        key = length_delimited(utf8(self.entity_id), utf8(self.source_instance_id))
        return f"urn:aip:infra-contribution:{sha256_hex(key)}"


class InfrastructureClaim(BaseModel):
    """I2 Draft 0.2 §7.2: "All claims carry kind, subject_id, optional object_id, evidence_refs, and
    mapping_rule_id/version." `WORKLOAD_EXISTS` MUST NOT invent a sentinel entity or self-edge to
    force it through a binary-relation representation - `object_id=None` represents it directly,
    and the three binary kinds MUST carry a real object.
    """

    kind: InfrastructureClaimKind
    subject_id: str = Field(min_length=1)
    object_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    mapping_rule_id: str = Field(min_length=1)
    mapping_rule_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_arity_and_evidence(self) -> "InfrastructureClaim":
        if self.kind in UNARY_CLAIM_KINDS:
            if self.object_id is not None:
                raise ValueError(
                    f"{self.kind.value} is a unary claim and MUST NOT carry an object_id (§7.2), "
                    f"got {self.object_id!r}"
                )
        elif not self.object_id:
            raise ValueError(
                f"{self.kind.value} is a binary claim and requires an object_id (§7.2)"
            )
        _check_evidence_refs(self.evidence_refs)
        return self

    @property
    def id(self) -> str:
        """I2 Draft 0.2 §7.2: "Claim identity is the hash of kind, subject, and object (empty for a
        unary claim)." """
        key = length_delimited(
            utf8(self.kind.value), utf8(self.subject_id), utf8(self.object_id or "")
        )
        return f"urn:aip:infra-claim:{sha256_hex(key)}"
