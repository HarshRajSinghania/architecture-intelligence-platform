from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.canonical.infrastructure import KubernetesEvidenceMode

SourceInstanceId = NewType("SourceInstanceId", str)
DiscoveryScopeId = NewType("DiscoveryScopeId", str)


class NotSupplied:
    """A dedicated sentinel type, not a string constant, for an `expected_prior_inventory_revision`
    default - I2 Draft 0.2 §3 prerequisite slice, item 4. Distinguishes "caller supplied no
    expectation at all" (preserves prior behavior exactly - no predecessor check performed) from a
    legitimate explicit expectation of `None` (caller expects no prior committed inventory to exist
    yet). A plain `None` default could not make that distinction, and a string sentinel compared by
    identity (`is not`) would be fragile - string identity is a CPython interning implementation
    detail, not a language guarantee (a real finding from PR review).

    Originally file-private to `app.graph.importer` (where the predecessor-check transaction lives);
    relocated here (I2 Draft 0.2 slice 2b-ii) and made public because `app.sources.registry`'s
    `DiscoveryOutcome` and `app.ingestion.orchestrator`'s `DiscoveryRunResult` - both lower layers
    `app.graph.importer` already imports from - also need this type for their own
    `expected_prior_inventory_revision` fields; either importing it from `app.graph.importer` would
    reverse that dependency direction.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<not supplied>"


NOT_SUPPLIED = NotSupplied()


class SourceKind(StrEnum):
    FILESYSTEM = "filesystem"
    # I2 Draft 0.2 §6: "source_kind = kubernetes". Registration binding (comparing an envelope's
    # declared identity against a configured KubernetesSourceConfig) now exists (slice 2b-i), which
    # is the "unsupported > falsely supported" prerequisite the original reserved-comment here named.
    KUBERNETES = "kubernetes"


class FilesystemSourceConfig(BaseModel):
    """I1 spec §5.1's "configured filesystem-source id" plus the physical root it scans. A source's
    stable identity must be an explicit, operator-assigned id, never the directory path itself (I1
    §6: "stable target identity MUST NOT be an absolute checkout path, resolved physical directory,
    mount point, or other mutable root location").

    A pure domain contract (not a settings-loading concern) so `app/ingestion/` and `app/graph/`
    can depend on it directly without depending on `app.settings`; `app.settings.SourcesConfig`
    reuses this same type as its field shape.

    `scope_id` and `stable_target_identity` default from `id` when omitted, which is sufficient for
    the common one-directory-one-scope case; a deployment scanning multiple physically distinct
    roots under one logical scope can override `scope_id` to group them.
    """

    id: str
    root: Path
    scope_id: str | None = None
    stable_target_identity: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _reject_bare_entry(cls, value: object) -> object:
        if not isinstance(value, dict):
            # Must be ValueError, not TypeError: pydantic only wraps ValueError/AssertionError
            # raised inside a validator into a ValidationError - a TypeError would propagate
            # uncaught instead of surfacing as a normal config-validation failure.
            raise ValueError(  # noqa: TRY004
                "sources.directories entries must be objects with 'id' and 'root' fields "
                f"(got {value!r}) - a bare directory path can no longer serve as a source's "
                "stable identity; add an explicit 'id' (e.g. {'id': "
                "'aip-bundled-examples-v0.5', 'root': <path>})"
            )
        return value

    @property
    def resolved_scope_id(self) -> str:
        return self.scope_id or self.id

    @property
    def resolved_stable_target_identity(self) -> str:
        return self.stable_target_identity or f"urn:aip:logical-root:{self.id}"


class KubernetesSourceConfig(BaseModel):
    """I2 Draft 0.2 §4.2's configured source registration: "binds the source/scope IDs, cluster
    UID, evidence mode, authorized snapshot producer, and authority record. Envelope values must
    match it." `root`/`envelope_relative_path` locate the frozen bundle on the local filesystem
    (§2's `OFFLINE_ONLY` scope - no live cluster access). Mirrors `FilesystemSourceConfig`'s own
    `scope_id`/`stable_target_identity` defaulting shape exactly.

    `cluster_uid` is the natural stable identity anchor for a Kubernetes source (§6: "an
    independently established cluster identity") - the same role `id` plays for
    `FilesystemSourceConfig.resolved_stable_target_identity`.
    """

    id: str
    root: Path
    envelope_relative_path: str
    configured_scope_id: str | None = None
    cluster_uid: str
    evidence_mode: KubernetesEvidenceMode
    authorized_producer: str
    authority_record: str
    stable_target_identity: str | None = None

    @property
    def resolved_scope_id(self) -> str:
        return self.configured_scope_id or self.id

    @property
    def resolved_stable_target_identity(self) -> str:
        return self.stable_target_identity or f"urn:aip:k8s-cluster:{self.cluster_uid}"


class IngestionResult(StrEnum):
    """I1 spec §10: "Each source receives exactly one result." """

    ACCEPTED = "ACCEPTED"
    ACCEPTED_WITH_LIMITATIONS = "ACCEPTED_WITH_LIMITATIONS"
    REJECTED_INVALID = "REJECTED_INVALID"
    REJECTED_UNSUPPORTED = "REJECTED_UNSUPPORTED"
    REJECTED_CONFLICT = "REJECTED_CONFLICT"


class DiagnosticCode(StrEnum):
    # Named explicitly by the I1 spec (§4.1, §8, §8.1, §9).
    SERVICE_IDENTITY_UNRESOLVED = "SERVICE_IDENTITY_UNRESOLVED"
    SERVICE_IDENTITY_CONFLICT = "SERVICE_IDENTITY_CONFLICT"
    SERVICE_IDENTITY_INVALID = "SERVICE_IDENTITY_INVALID"
    REFERENCE_LIMIT_EXCEEDED = "REFERENCE_LIMIT_EXCEEDED"
    REFERENCE_CYCLE_UNSUPPORTED = "REFERENCE_CYCLE_UNSUPPORTED"
    SCHEMA_COMPOSITION_UNINTERPRETED = "SCHEMA_COMPOSITION_UNINTERPRETED"
    AMBIGUOUS = "AMBIGUOUS"
    # Not named by the spec text; introduced here for the ArchitectureIdentityBindings shape (§4.2),
    # which the spec describes only in prose. Flagged in the PR description for review.
    MANIFEST_BINDING_SHAPE_INVALID = "MANIFEST_BINDING_SHAPE_INVALID"
    MANIFEST_BINDING_POINTER_INVALID = "MANIFEST_BINDING_POINTER_INVALID"
    MANIFEST_BINDING_UNKNOWN_SOURCE = "MANIFEST_BINDING_UNKNOWN_SOURCE"
    # Not named by the spec text; introduced here for §6's tombstone-staleness rejection reasons.
    TOMBSTONE_STALE = "TOMBSTONE_STALE"
    TOMBSTONE_SCOPE_MISMATCH = "TOMBSTONE_SCOPE_MISMATCH"
    # Not named by the spec text; introduced here for filesystem-discovery-level failures (I1 §6's
    # "missing roots, incomplete checkouts ... MUST preserve the prior inventory" list) and
    # malformed source documents encountered before an adapter can even attempt to map them.
    SOURCE_ROOT_UNAVAILABLE = "SOURCE_ROOT_UNAVAILABLE"
    DOCUMENT_PARSE_INVALID = "DOCUMENT_PARSE_INVALID"
    # v0.5.0 I5 finding F5: a candidate filename placed directly in the configured root (not inside
    # a service subdirectory) is never enumerated. Informational only - the file stays unloaded and
    # neither enumeration completeness nor any source's result changes.
    SOURCE_CANDIDATE_OUTSIDE_SERVICE_DIRECTORY = "SOURCE_CANDIDATE_OUTSIDE_SERVICE_DIRECTORY"
    # Not named by the spec text; introduced here for §9's AsyncAPI Queue kind/identity evidence
    # rules. AMBIGUOUS (above) already covers the multi-server broker/namespace-disagreement case.
    QUEUE_KIND_CONFLICT = "QUEUE_KIND_CONFLICT"
    QUEUE_IDENTITY_CONFLICT = "QUEUE_IDENTITY_CONFLICT"
    QUEUE_EVIDENCE_MISSING = "QUEUE_EVIDENCE_MISSING"
    # Not named by the spec text; introduced here for the Architecture Manifest CALLS-relation
    # adapter, distinct from the ArchitectureIdentityBindings manifest's own diagnostic codes above.
    MANIFEST_CALL_TARGET_UNRESOLVED = "MANIFEST_CALL_TARGET_UNRESOLVED"
    # v0.5.0 I5 finding F1: the manifest's own caller Service is not declared by any discovered
    # source. The manifest never mints a Service, so its CALLS would have no source entity.
    MANIFEST_CALL_SOURCE_UNRESOLVED = "MANIFEST_CALL_SOURCE_UNRESOLVED"
    # v0.5.0 I5 finding F1: the merged canonical model violates a canonical invariant (V1-V8) that
    # this source's emitted elements take part in. The source is REJECTED_INVALID and the run does
    # not commit, instead of the validation failure escaping the import.
    CANONICAL_MODEL_INVALID = "CANONICAL_MODEL_INVALID"
    # Not named by the spec text; introduced here for PR3b's bounded multi-file $ref resolution
    # (I1 spec §8.1/§9). REFERENCE_LIMIT_EXCEEDED/REFERENCE_CYCLE_UNSUPPORTED already existed above
    # (added ahead of their real use); these three cover the remaining §8.1 resolution-order
    # rejection cases the spec describes in prose without naming a code: a `$ref` with a non-empty
    # URI scheme/authority ("remote/non-local reference -> REJECTED_UNSUPPORTED for the whole
    # source"), and every other resolution-order failure - malformed percent-encoding, an absolute
    # decoded path, a traversal/symlink escape outside the approved source root, a missing/non-file
    # target, or a dangling JSON Pointer fragment ("invalid structure/reference" -> REJECTED_INVALID).
    REMOTE_REFERENCE_UNSUPPORTED = "REMOTE_REFERENCE_UNSUPPORTED"
    REFERENCE_INVALID = "REFERENCE_INVALID"
    # Not named by the spec text; introduced here for §8/§9's exact-version enforcement
    # ("any other version is REJECTED_UNSUPPORTED unless a reviewed amendment adds that exact
    # version and its conformance fixtures").
    UNSUPPORTED_DIALECT_VERSION = "UNSUPPORTED_DIALECT_VERSION"
    # Not named by the spec text; introduced here for PR4's explicit shared-identity/migration
    # mapping mechanism (§5.1.1/§8.1/§9/§9.1), mirroring the MANIFEST_BINDING_* codes' own
    # "shape, then pointer/target validity, then cross-entry conflict" split.
    MIGRATION_MAPPING_SHAPE_INVALID = "MIGRATION_MAPPING_SHAPE_INVALID"
    MIGRATION_MAPPING_TARGET_INVALID = "MIGRATION_MAPPING_TARGET_INVALID"
    MIGRATION_MAPPING_CONFLICT = "MIGRATION_MAPPING_CONFLICT"
    # §5.1.1: "Missing or modified migration configuration is diagnosed and MUST NOT fall back to a
    # directory slug or name-derived identity" - a configured migration path that can't be read at
    # all is its own distinct failure from a file that parses but has the wrong shape.
    MIGRATION_MAPPING_FILE_UNAVAILABLE = "MIGRATION_MAPPING_FILE_UNAVAILABLE"
    # Not named by the spec text; introduced here for the cross-source/within-source content-
    # conflict rule §8.1/§9.1 both state prose-only ("different hashes under an explicit shared ID
    # are REJECTED_CONFLICT"): two claims converging on the same owner-scoped or explicitly-mapped
    # Schema/Message id with disagreeing canonical content.
    SCHEMA_CONTENT_CONFLICT = "SCHEMA_CONTENT_CONFLICT"
    MESSAGE_CONTENT_CONFLICT = "MESSAGE_CONTENT_CONFLICT"
    # Not named by the spec text; introduced here for the I2 Draft 0.2 §3 prerequisite slice's
    # tombstone-file loading (app.sources.tombstones.load_tombstones), mirroring the
    # MIGRATION_MAPPING_FILE_UNAVAILABLE/MIGRATION_MAPPING_SHAPE_INVALID split above.
    TOMBSTONE_FILE_UNAVAILABLE = "TOMBSTONE_FILE_UNAVAILABLE"
    TOMBSTONE_SHAPE_INVALID = "TOMBSTONE_SHAPE_INVALID"
    # Not named by the spec text; introduced here for the I2 Draft 0.2 §3 prerequisite slice's
    # general (source-kind-neutral) transactional predecessor check - the mechanism
    # K8S_STALE_INVENTORY (below, slice 2b-ii) now layers onto rather than replaces.
    STALE_INVENTORY_PREDECESSOR = "STALE_INVENTORY_PREDECESSOR"
    # I2 Draft 0.2 §10's own named code, with its specified outcome ("REJECTED_CONFLICT for
    # incompatible duplicate identity/incarnation"), for §7.1's cross-source rule: "Different
    # semantic digests from simultaneously current sources are incompatible and reject the affected
    # discovery run as K8S_RESOURCE_CONFLICT; no source wins by precedence." Deliberately NOT a
    # generalized/renamed variant - the entity kinds this guards are themselves Kubernetes-specific
    # (KUBERNETES_WORKLOAD/POD/NETWORK_SERVICE/INGRESS), so the spec's own name is the honest one.
    K8S_RESOURCE_CONFLICT = "K8S_RESOURCE_CONFLICT"
    # I2 Draft 0.2 §10's own named codes, for slice 2a (envelope validation, bounds/security,
    # identity) - the remaining §10 codes (K8S_STALE_INVENTORY, K8S_RESOURCE_*, K8S_OWNER_*,
    # NO_QUALIFIED_POD_MATCH, K8S_BACKEND_UNRESOLVED) depend on predecessor-revision threading,
    # resource projection, or owner-chain resolution later slices implement.
    #
    # K8S_CLUSTER_IDENTITY_UNRESOLVED is now reachable (slice 2b-i):
    # KubernetesSourceDiscoverer's registration-binding check fires it for a cluster_uid mismatch
    # against the configured KubernetesSourceConfig specifically - every other registration-binding
    # mismatch (source/scope id, mode, producer, authority) is K8S_SNAPSHOT_INVALID instead (§10:
    # "shape, digest, or scope mismatch").
    K8S_CLUSTER_IDENTITY_UNRESOLVED = "K8S_CLUSTER_IDENTITY_UNRESOLVED"
    K8S_SNAPSHOT_INVALID = "K8S_SNAPSHOT_INVALID"
    K8S_SNAPSHOT_INCOMPLETE = "K8S_SNAPSHOT_INCOMPLETE"
    K8S_LIMIT_EXCEEDED = "K8S_LIMIT_EXCEEDED"
    # I2 Draft 0.2 §10's own named code ("REJECTED_CONFLICT; no commit"), for §4.2's predecessor
    # comparison (slice 2b-ii). Layered alongside the generic STALE_INVENTORY_PREDECESSOR (above)
    # by `import_kubernetes_source`, not raised by `_import_all_sources_tx` itself - that shared
    # transaction stays source-kind-neutral.
    K8S_STALE_INVENTORY = "K8S_STALE_INVENTORY"
    # I2 Draft 0.2 §10's own named code ("Omit object; ACCEPTED_WITH_LIMITATIONS"), for §5: "Other
    # controller kinds and API versions require an amendment; unsupported objects are omitted with
    # pointer diagnostics and ACCEPTED_WITH_LIMITATIONS" (slice 3a).
    K8S_RESOURCE_UNSUPPORTED = "K8S_RESOURCE_UNSUPPORTED"
    # Not named by the spec text; introduced here (slice 3a) for §5's remaining resource-shape
    # rejection reasons that don't already have a home: "Missing name, missing namespace for a
    # namespaced kind, malformed used fields... reject the source" and "a captured resource
    # requires UID and resourceVersion; absence rejects the capture." An out-of-scope namespace
    # instead reuses K8S_SNAPSHOT_INVALID (its own definition already names "scope mismatch");
    # conflicting duplicate resources reuse K8S_RESOURCE_CONFLICT (below, already spec-named).
    K8S_RESOURCE_INVALID = "K8S_RESOURCE_INVALID"
    # I2 Draft 0.2 §10's own named codes (slice 4a), for §7.3's owner-chain resolution: "Missing
    # owner, missing UID match, unsupported chain, or declaration-only input emits no ownership
    # claim and a limitation diagnostic" (K8S_OWNER_UNRESOLVED, ACCEPTED_WITH_LIMITATIONS); "Multiple
    # controller owners, cyclic references, or internally conflicting UID assignments reject the
    # source" (K8S_OWNER_INVALID, REJECTED_INVALID).
    K8S_OWNER_UNRESOLVED = "K8S_OWNER_UNRESOLVED"
    K8S_OWNER_INVALID = "K8S_OWNER_INVALID"
    # I2 Draft 0.2 §10's own named code (slice 4b), for §7.4's Service selection: "No matching Pod
    # means no relation with a NO_QUALIFIED_POD_MATCH limitation, not evidence that the Service has
    # no backend" - also reused for "unresolved matching Pods remain explicit limitations without
    # suppressing separately proven matches" (a matching Pod whose owner chain didn't resolve).
    NO_QUALIFIED_POD_MATCH = "NO_QUALIFIED_POD_MATCH"
    # I2 Draft 0.2 §10's own named code (slice 4c), for §7.5's Ingress backend resolution: "Missing
    # Service/port produces an unresolved diagnostic and no relation for that backend... Other
    # resolved backends may still emit claims" - also reused for a resource backend ("Resource
    # backends are unsupported") and an ambiguous (more than one matching) Service port.
    K8S_BACKEND_UNRESOLVED = "K8S_BACKEND_UNRESOLVED"
    # Not named by the spec text; introduced here for v0.5.0 I3 slice 3's §8.1 configured
    # Service<->Workload identity-mapping artifact, mirroring the MIGRATION_MAPPING_*/
    # MANIFEST_BINDING_* codes' own "shape, then target validity, then cross-entry conflict" split.
    SERVICE_WORKLOAD_MAPPING_FILE_UNAVAILABLE = "SERVICE_WORKLOAD_MAPPING_FILE_UNAVAILABLE"
    SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID = "SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID"
    SERVICE_WORKLOAD_MAPPING_TARGET_INVALID = "SERVICE_WORKLOAD_MAPPING_TARGET_INVALID"
    # A duplicate `mappingId` with differing content within one artifact - distinct from a literal
    # duplicate YAML mapping key (which `load_bounded_yaml_documents` already rejects as a shape
    # error) - since `mappingId` is part of both §13.1's group-key formula and §8.3's evidence
    # identity, a silent collision here would be a latent identity defect, not a benign duplicate.
    SERVICE_WORKLOAD_MAPPING_DUPLICATE_ID = "SERVICE_WORKLOAD_MAPPING_DUPLICATE_ID"
    # v0.5.0 I4 spec §8.4's own named codes - exactly these three, and no DESTINATION_KIND_UNSUPPORTED
    # member. Vocabulary only as of I4 slice 1; the AsyncAPI Topic/Subscription mapping that emits
    # them lands in slice 2. TOPIC_IDENTITY_CONFLICT: configured vs derived Topic id disagree.
    # SUBSCRIPTION_IDENTITY_CONFLICT: configured Subscription id, Topic binding, or Subscription name
    # disagrees with its declared/derived counterpart. SUBSCRIPTION_IDENTITY_MISSING: a Topic
    # subscribe operation with no explicit or configured Subscription identity.
    TOPIC_IDENTITY_CONFLICT = "TOPIC_IDENTITY_CONFLICT"
    SUBSCRIPTION_IDENTITY_CONFLICT = "SUBSCRIPTION_IDENTITY_CONFLICT"
    SUBSCRIPTION_IDENTITY_MISSING = "SUBSCRIPTION_IDENTITY_MISSING"


@dataclass(frozen=True)
class SubscriptionMapping:
    """The resolved payload of one `subscriptionMappings` entry (I4 spec §7.3)."""

    topic_id: str
    subscription_name: str
    subscription_id: str


class IngestionDiagnostic(BaseModel):
    code: DiagnosticCode
    message: str
    source_pointer: str | None = None
    source_instance_id: str | None = None


class KubernetesCaptureScope(BaseModel):
    """What a *accepted* Kubernetes envelope says about the capture it describes (v0.6.0 I2 decision
    record D5): the namespaces it declares complete, the cluster it is bound to, its declared
    revision and evidence mode, and its raw `capturedAt`. Carried on `SourceDescriptor` from the
    discoverer to the importer, which persists it on the source's `SourceState` so it can be read
    under the revision fence. Never set for a rejected envelope or a non-Kubernetes source."""

    model_config = ConfigDict(frozen=True)

    namespaces: tuple[str, ...]
    cluster_uid: str
    revision: str
    evidence_mode: str
    captured_at: str


class SourceDescriptor(BaseModel):
    """I1 spec §4's `SourceDescriptor` fields. Field names are this PR's own choice - the spec gives
    only a prose bullet list, not a schema - and are called out for review in the PR description.
    `source_inventory_snapshot_ref` is a placeholder `str | None` until a later increment defines the
    real `SourceInventorySnapshot`. `mapping_context_digest` was added by the I1 spec's Draft 0.2
    revision (§5.3) - see `app.sources.identity.mapping_context_digest`.
    """

    source_instance_id: str
    source_kind: SourceKind
    locator: str
    discovery_scope_id: str
    scope_definition_digest: str
    source_inventory_snapshot_ref: str | None = None
    declared_provider_revision: str | None = None
    content_sha256: str
    dependency_closure_digest: str | None = None
    semantic_input_digest: str
    mapping_context_digest: str
    declared_service_id: str | None = None
    document_dialect_version: str | None = None
    adapter_identity: str
    mapping_rule_id: str
    mapping_rule_version: str
    # v0.6.0 I2.2d: only the Kubernetes discoverer's accepted path sets this. It is in-memory
    # plumbing from the discoverer to the importer (`model_copy` keeps it), deliberately excluded
    # from serialization so no descriptor dump, discovery golden or report changes shape.
    capture_scope: KubernetesCaptureScope | None = Field(default=None, exclude=True)


@dataclass(frozen=True)
class KubernetesResourceEntry:
    """I2 Draft 0.2 §6: "source pointers remain provenance and are sorted when multiple files
    represent one object." Pairs a resource's own parsed content with the listed file it came
    from - a bare `dict` alone loses this, and a per-entity `Provenance.source_file` (slice 3) needs
    the *resource's own* pointer, not one shared envelope-wide locator. Lives here (not in
    `app.sources.kubernetes_envelope`, which constructs it) so `LoadedSource` below - a shared
    vocabulary type every source-kind's discoverer imports - can reference it without that module
    needing to import from `kubernetes_envelope` in the other direction.
    """

    source_pointer: str
    document: dict


class LoadedSource(BaseModel):
    descriptor: SourceDescriptor
    document: dict
    diagnostics: list[IngestionDiagnostic] = Field(default_factory=list)
    source_root: str = ""
    """The approved containment boundary a `$ref` may resolve within (I1 spec §8.1's "approved
    source root"), as an absolute or process-relative filesystem path string. Populated by the
    discoverer (the only component that knows the configured root); empty only for a `LoadedSource`
    built directly by a test with no real filesystem backing, since none of PR3b's cross-file
    resolution paths apply to it."""
    kubernetes_resources: tuple[KubernetesResourceEntry, ...] = ()
    """I2 Draft 0.2 §4.3's already-validated, flattened resource-object list (from
    `app.sources.kubernetes_envelope.validate_kubernetes_snapshot`), each paired with its own
    source file pointer - carried forward so a later Kubernetes adapter never needs to re-run
    bounded sanitized loading. Empty for every non-Kubernetes source, and for a Kubernetes source
    whose envelope itself failed validation."""
