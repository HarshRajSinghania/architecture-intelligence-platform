"""I1 spec §7's orchestrator: discover -> inventory -> classify -> load -> validate -> normalize ->
map -> merge -> canonical validation -> reconciliation plan -> atomic commit.

Everything through "canonical validation" happens here, entirely in memory, with zero Neo4j I/O -
matching PR #1/#2's discipline of pure functions over explicit inputs. "Reconciliation plan" and
"atomic commit" are `app.graph.importer`'s job (this increment's part 9): it calls
`run_filesystem_discovery` to get a `DiscoveryRunResult`, then uses `app.sources.replay`/
`app.sources.claim_reconciliation`/`app.sources.commit_gate` against real committed graph state to
decide what (if anything) to write.

This module replaces `app.ingestion.pipeline`, which is deleted in this same change: its two
responsibilities - `merge_models` (kept, moved here) and hard-coded per-source-kind dispatch
(replaced by the registry) - are both superseded.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from app.canonical.merge import merge_models
from app.canonical.model import (
    ArchitectureModel,
    relation_key,
)
from app.common.jcs import sort_entries_by_canonical_bytes
from app.ingestion.asyncapi_adapter import AsyncApiSourceAdapter
from app.ingestion.filesystem_discoverer import FilesystemSourceDiscoverer
from app.ingestion.kubernetes_adapter import KubernetesSourceAdapter
from app.ingestion.kubernetes_discoverer import KubernetesSourceDiscoverer
from app.ingestion.manifest_adapter import ManifestSourceAdapter
from app.ingestion.openapi_adapter import OpenApiSourceAdapter
from app.sources.claim_conflicts import (
    detect_infrastructure_entity_content_conflicts,
    detect_shared_claim_content_conflicts,
    detect_subscription_topic_binding_conflicts,
)
from app.sources.commit_gate import classify_inventory_status, run_is_eligible_to_commit
from app.sources.identity import mapping_context_digest as compute_mapping_context_digest
from app.sources.inventory import (
    InventoryStatus,
    SourceInventorySnapshot,
    inventory_capture_id,
    inventory_revision,
)
from app.sources.manifest_bindings import (
    BindingIndex,
    build_binding_index,
    parse_architecture_identity_bindings,
)
from app.sources.migration_mappings import (
    EMPTY_SHARED_IDENTITY_INDEX,
    IdentityMappingEntry,
    MigrationMappingsDocument,
    SharedIdentityMappingIndex,
    SubscriptionMapping,
)
from app.sources.model import (
    NOT_SUPPLIED,
    DiagnosticCode,
    DiscoveryScopeId,
    FilesystemSourceConfig,
    IngestionDiagnostic,
    IngestionResult,
    KubernetesSourceConfig,
    LoadedSource,
    NotSupplied,
    SourceDescriptor,
)
from app.sources.registry import (
    AdapterOutcome,
    DiscoveryOutcome,
    ServiceIdentityResolver,
    SharedIdentityResolver,
    SourceAdapterRegistry,
    SourceDiscoverer,
)
from app.sources.service_identity import (
    PointerBinding,
    ServiceIdentityPath,
    resolve_service_identity,
)
from app.sources.tombstones import Tombstone
from app.validation.canonical_validation import (
    CanonicalValidationIssue,
    canonical_validation_issues,
)

_DEFAULT_ADAPTERS = (
    OpenApiSourceAdapter(),
    AsyncApiSourceAdapter(),
    ManifestSourceAdapter(),
    KubernetesSourceAdapter(),
)


def default_registry() -> SourceAdapterRegistry:
    return SourceAdapterRegistry(_DEFAULT_ADAPTERS)


def _is_identity_bindings_document(document: dict) -> bool:
    return document.get("kind") == "ArchitectureIdentityBindings"


class _RunServiceIdentityResolver:
    """One instance built per discovery run, closing over phase 1's completed `BindingIndex`. I1
    spec §4.1 path 2 (versioned configured source-to-Service mapping) has no config surface in 3a,
    so `configured_mappings` is always empty here.
    """

    def __init__(self, manifest_bindings: Sequence[PointerBinding]):
        self._manifest_bindings = tuple(manifest_bindings)

    def resolve(self, *, source_instance_id: str, construct_pointer: str, extension_value):
        return resolve_service_identity(
            source_instance_id=source_instance_id,
            construct_pointer=construct_pointer,
            extension_value=extension_value,
            configured_mappings=(),
            manifest_bindings=self._manifest_bindings,
        )


class _RunSharedIdentityResolver:
    """One instance built per discovery run, closing over every configured migration-mapping file's
    merged `SharedIdentityMappingIndex`. Handed to every adapter the same way
    `_RunServiceIdentityResolver` is - adapters never see the index or its source files directly.
    """

    def __init__(self, index: SharedIdentityMappingIndex):
        self._index = index

    def schema_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self._index.schema_id_for(
            source_instance_id=source_instance_id, document_path=document_path, pointer=pointer
        )

    def message_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self._index.message_id_for(
            source_instance_id=source_instance_id, document_path=document_path, pointer=pointer
        )

    def queue_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self._index.queue_id_for(
            source_instance_id=source_instance_id, document_path=document_path, pointer=pointer
        )

    def topic_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self._index.topic_id_for(
            source_instance_id=source_instance_id, document_path=document_path, pointer=pointer
        )

    def subscription_mapping_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> SubscriptionMapping | None:
        return self._index.subscription_mapping_for(
            source_instance_id=source_instance_id, document_path=document_path, pointer=pointer
        )


def _binding_index_to_pointer_bindings(binding_index: BindingIndex) -> tuple[PointerBinding, ...]:
    return tuple(
        PointerBinding(
            source_instance_id=entry.source_instance_id,
            pointer_prefix=entry.pointer_prefix,
            service_id=entry.service_id,
            path=ServiceIdentityPath.MANIFEST_BINDING,
        )
        for entry in binding_index.entries
    )


# I1 spec §5.1.1's fixed artifact id for the bundled examples/ migration file - any *other*
# configured migration document is a general shared-identity mapping instead, per the
# classification rule in `_classify_shared_identity_entries`'s docstring below.
BUNDLED_MIGRATION_ARTIFACT_ID = "aip-v0.5.0-bundled-example-identities-v1"


def _mapping_entry_context(
    document: MigrationMappingsDocument, entry: IdentityMappingEntry, *, id_field: str
) -> dict[str, str]:
    # v0.5.0 I4 spec §7.3: a subscriptionMappings entry's Topic binding and Subscription name are
    # part of its identity payload, so they enter the digest alongside its Subscription id.
    subscription_binding = (
        {"topicId": entry.bound_topic_id, "subscriptionName": entry.subscription_name}
        if entry.bound_topic_id is not None
        else {}
    )
    return {
        "artifactId": document.artifact_id,
        "artifactRevision": document.artifact_revision,
        # §5.3: "Each mapping entry retains its stable artifact identity, revision, content digest,
        # attribution, normalized source pointers, targets, and semantic options." contentDigest is
        # the SHA-256 of this artifact file's own exact raw bytes (MigrationMappingsDocument.
        # content_digest, computed once per file by load_migration_mappings). attribution is the
        # configured file's own *basename*, not document.locator's full path - §5.3 elsewhere
        # requires "Capture times and physical checkout paths are excluded", and load_migration_
        # mappings sets locator to str(path) verbatim, which is the exact absolute (or otherwise
        # checkout-root-dependent) path when the caller configures one, exactly the kind of physical
        # path that MUST NOT enter a portable digest. The basename is still real attribution (which
        # configured file declared the mapping) without being checkout-root-dependent. There is no
        # per-artifact "semantic options" concept this mechanism exposes, so that part of §5.3's
        # list has nothing to project (mirroring configuredServiceMappings/destinationBrokerMappings
        # staying explicit empty arrays for categories with no configured instance).
        "contentDigest": document.content_digest,
        "attribution": Path(document.locator).name,
        "sourceInstanceId": entry.source_instance_id,
        # documentPath is part of this entry's own lookup identity (source_instance_id,
        # document_path, pointer) - omitting it here would mean moving an otherwise identical
        # mapping from one file to another (the same pointer, a different documentPath) changes
        # which canonical entity actually receives the mapped id, without changing this digest, so
        # the revision fence would never notice the resulting graph change.
        "documentPath": entry.document_path,
        "pointer": entry.pointer,
        id_field: entry.target_id,
        **subscription_binding,
    }


def _classify_shared_identity_entries(
    shared_identity_index: SharedIdentityMappingIndex,
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """§5.3 names `bundledMigrationMappings` as one context category and `sharedSchemaMappings`/
    `sharedMessageMappings`/`sharedQueueMappings` as separate ones - a distinction the spec
    text doesn't otherwise define, so this module draws it explicitly (flagged for review): any
    loaded migration document whose artifact id is the fixed §5.1.1 bundled-example constant
    contributes all of its entries (every kind alike) to the one `bundledMigrationMappings` list;
    every other configured document's entries are split by kind into the five `shared*Mappings`
    categories instead (schema, message, queue, and - since v0.5.0 I4 spec §7.3 - topic and
    subscription), since that general mechanism has no single-artifact identity to fold entries
    under.
    """
    bundled: list[dict] = []
    shared_schema: list[dict] = []
    shared_message: list[dict] = []
    shared_queue: list[dict] = []
    shared_topic: list[dict] = []
    shared_subscription: list[dict] = []
    for document in shared_identity_index.documents:
        is_bundled = document.artifact_id == BUNDLED_MIGRATION_ARTIFACT_ID
        for entry in document.schema_mappings:
            item = _mapping_entry_context(document, entry, id_field="schemaId")
            (bundled if is_bundled else shared_schema).append(item)
        for entry in document.message_mappings:
            item = _mapping_entry_context(document, entry, id_field="messageId")
            (bundled if is_bundled else shared_message).append(item)
        for entry in document.queue_mappings:
            item = _mapping_entry_context(document, entry, id_field="queueId")
            (bundled if is_bundled else shared_queue).append(item)
        for entry in document.topic_mappings:
            item = _mapping_entry_context(document, entry, id_field="topicId")
            (bundled if is_bundled else shared_topic).append(item)
        for entry in document.subscription_mappings:
            item = _mapping_entry_context(document, entry, id_field="subscriptionId")
            (bundled if is_bundled else shared_subscription).append(item)
    return (
        bundled,
        shared_schema,
        shared_message,
        shared_queue,
        shared_topic,
        shared_subscription,
    )


def _compute_mapping_context_digest(
    binding_index: BindingIndex,
    registry: SourceAdapterRegistry,
    shared_identity_index: SharedIdentityMappingIndex,
) -> str:
    """I1 spec §5.3: the context's input is "the complete canonical index of configured and
    manifest Service bindings, shared Schema/Message mappings, Queue/destination and broker/server/
    namespace mappings, bundled migration mappings, and all active adapter, normalization, and
    mapping-rule identities/versions." `configuredServiceMappings`/`destinationBrokerMappings`
    remain explicit empty arrays - no configured instance of either exists or is needed yet
    ("Explicit empty arrays represent absent mapping categories" - §5.3). v0.5.0 I4 spec §7.3 adds
    `sharedTopicMappings`/`sharedSubscriptionMappings` under the same always-present rule, so every
    pre-I4 context digest changes once (a one-time same-scope re-evaluation, not a new identity).
    """
    (
        bundled,
        shared_schema,
        shared_message,
        shared_queue,
        shared_topic,
        shared_subscription,
    ) = _classify_shared_identity_entries(shared_identity_index)
    context = {
        "manifestBindings": sort_entries_by_canonical_bytes(
            [
                {
                    "sourceInstanceId": entry.source_instance_id,
                    "pointerPrefix": entry.pointer_prefix,
                    "serviceId": entry.service_id,
                }
                for entry in binding_index.entries
            ]
        ),
        "configuredServiceMappings": [],
        "sharedSchemaMappings": sort_entries_by_canonical_bytes(shared_schema),
        "sharedMessageMappings": sort_entries_by_canonical_bytes(shared_message),
        "sharedQueueMappings": sort_entries_by_canonical_bytes(shared_queue),
        "sharedTopicMappings": sort_entries_by_canonical_bytes(shared_topic),
        "sharedSubscriptionMappings": sort_entries_by_canonical_bytes(shared_subscription),
        "destinationBrokerMappings": [],
        "bundledMigrationMappings": sort_entries_by_canonical_bytes(bundled),
        "adapters": sort_entries_by_canonical_bytes(
            [
                {
                    "adapterIdentity": adapter.adapter_identity,
                    "mappingRuleVersion": adapter.mapping_rule_version,
                }
                for adapter in registry.adapters
            ]
        ),
    }
    return compute_mapping_context_digest(context)


@dataclass(frozen=True)
class SourceRunOutcome:
    descriptor_locator: str
    outcome: AdapterOutcome
    # The source's descriptor as mapped (enriched with the claiming adapter's identity), so the I1
    # §10 import report can name each source's adapter and dialect. `None` only for callers that
    # construct an outcome without one.
    descriptor: SourceDescriptor | None = None


def _rejected_conflict(run_outcome: SourceRunOutcome) -> SourceRunOutcome:
    """I2 Draft 0.2 §10: `K8S_RESOURCE_CONFLICT` -> "REJECTED_CONFLICT; no commit". Rewrites one
    source's own result while preserving everything else it produced (diagnostics, digest, and the
    model it mapped - none of which commits, since the run is not commit-eligible).
    """
    return replace(
        run_outcome,
        outcome=replace(run_outcome.outcome, result=IngestionResult.REJECTED_CONFLICT),
    )


_MODEL_ENTITY_FIELDS = (
    "services",
    "operations",
    "queues",
    "messages",
    "schemas",
    "provenance",
    "topics",
    "subscriptions",
    "pubsub_declarations",
    "subscription_dead_letter_configurations",
    "infrastructure_entities",
    "infrastructure_contributions",
    "infrastructure_claims",
)


def _model_element_ids(model: ArchitectureModel) -> frozenset[str]:
    """Every entity id and relation element id a source's model emits - the vocabulary of
    `CanonicalValidationIssue.element_ids`."""
    return frozenset(
        {entity.id for field in _MODEL_ENTITY_FIELDS for entity in getattr(model, field)}
        | {relation_key(relation) for relation in model.relations}
    )


_REJECTABLE_RESULTS = (IngestionResult.ACCEPTED, IngestionResult.ACCEPTED_WITH_LIMITATIONS)


def _reject_canonically_invalid(
    source_outcomes: dict[str, SourceRunOutcome], issues: Sequence[CanonicalValidationIssue]
) -> tuple[dict[str, SourceRunOutcome], list[IngestionDiagnostic], list[CanonicalValidationIssue]]:
    """Attributes each canonical-validation issue to every source that emitted one of its
    implicated elements. Such a source gets one `CANONICAL_MODEL_INVALID` diagnostic per issue
    (pointing at the lowest implicated element it emitted) and, unless it was already rejected,
    becomes REJECTED_INVALID; its mapped model is kept, since nothing commits. Returns the rewritten
    outcomes, the new diagnostics (per-source and run-level), and the unattributed issues."""
    elements = {
        source_instance_id: _model_element_ids(run_outcome.outcome.model)
        for source_instance_id, run_outcome in source_outcomes.items()
    }
    per_source: dict[str, list[IngestionDiagnostic]] = {}
    unattributed: list[CanonicalValidationIssue] = []
    for issue in issues:
        implicated = set(issue.element_ids)
        attributed = False
        for source_instance_id in sorted(source_outcomes):
            emitted = implicated & elements[source_instance_id]
            if not emitted:
                continue
            attributed = True
            per_source.setdefault(source_instance_id, []).append(
                IngestionDiagnostic(
                    code=DiagnosticCode.CANONICAL_MODEL_INVALID,
                    message=issue.message,
                    source_pointer=min(emitted),
                    source_instance_id=source_instance_id,
                )
            )
        if not attributed:
            unattributed.append(issue)

    rewritten = dict(source_outcomes)
    for source_instance_id, diagnostics in per_source.items():
        run_outcome = rewritten[source_instance_id]
        outcome = run_outcome.outcome
        rewritten[source_instance_id] = replace(
            run_outcome,
            outcome=replace(
                outcome,
                result=(
                    IngestionResult.REJECTED_INVALID
                    if outcome.result in _REJECTABLE_RESULTS
                    else outcome.result
                ),
                diagnostics=(*outcome.diagnostics, *diagnostics),
            ),
        )

    new_diagnostics = [d for sid in sorted(per_source) for d in per_source[sid]]
    new_diagnostics.extend(
        IngestionDiagnostic(
            code=DiagnosticCode.CANONICAL_MODEL_INVALID,
            message=issue.message,
            source_pointer=min(issue.element_ids) if issue.element_ids else None,
        )
        for issue in unattributed
    )
    return rewritten, new_diagnostics, unattributed


@dataclass(frozen=True)
class DiscoveryRunResult:
    inventory_status: InventoryStatus
    commit_eligible: bool
    discovery_scope_id: str | None
    scope_definition_digest: str | None
    merged_model: ArchitectureModel
    source_outcomes: dict[str, SourceRunOutcome]
    diagnostics: tuple[IngestionDiagnostic, ...]
    # I2 Draft 0.2 §3 prerequisite slice, item 3: "every discovery attempt constructs a real
    # SourceInventorySnapshot." `None` only when `discovery_scope_id`/`scope_definition_digest`
    # themselves could not be computed (the configured root doesn't exist at all) - a snapshot
    # cannot meaningfully identify the inventory it describes without a scope id, mirroring
    # `DiscoveryOutcome.discovery_scope_id`'s own documented "scope itself unknown" meaning.
    inventory_snapshot: SourceInventorySnapshot | None = None
    # I2 Draft 0.2 §4.2 (slice 2b-ii): a pure pass-through of `DiscoveryOutcome`'s own field of the
    # same name - see that field's own docstring. `run_discovery()` never inspects or modifies this
    # value itself, only forwards it to whatever calls `import_discovery_run`.
    expected_prior_inventory_revision: str | None | NotSupplied = NOT_SUPPLIED


def _build_inventory_snapshot(
    *,
    discoverer_identity: str,
    registry: SourceAdapterRegistry,
    discovery_scope_id: str | None,
    scope_definition_digest: str | None,
    status: InventoryStatus,
    source_outcomes: Mapping[str, SourceRunOutcome],
    diagnostics: Sequence[IngestionDiagnostic],
    tombstones: Sequence[Tombstone],
) -> SourceInventorySnapshot | None:
    if discovery_scope_id is None or scope_definition_digest is None:
        return None

    # A caller (e.g. app.api.import_api, which loads every configured tombstone once and reuses
    # the same list for every configured source) may pass tombstones targeting other discovery
    # scopes. Only tombstones actually declared against THIS scope may affect its own inventory
    # revision/event-id chain - otherwise an unrelated scope's tombstone would spuriously churn
    # this scope's revision (a real bug found in review). `validate_tombstone_against_committed_
    # inventory` would reject an out-of-scope tombstone anyway, but it must never be allowed to
    # even enter this scope's semantic hash in the first place.
    in_scope_tombstones = tuple(t for t in tombstones if t.discovery_scope_id == discovery_scope_id)

    discovered_source_ids = tuple(sorted(source_outcomes.keys()))
    revision = inventory_revision(
        discovery_scope_id=DiscoveryScopeId(discovery_scope_id),
        scope_definition_digest=scope_definition_digest,
        source_instance_ids=discovered_source_ids,
        tombstones=in_scope_tombstones,
        status=status,
    )
    capture_time = datetime.now(UTC).isoformat()
    capture_id = inventory_capture_id(
        inventory_revision=revision,
        # No single "provider revision" exists at the multi-source run level - each source's own
        # `declared_provider_revision` already lives on its `SourceDescriptor`.
        normalized_provider_revision=None,
        capture_time=capture_time,
    )
    return SourceInventorySnapshot(
        inventory_revision=revision,
        inventory_capture_id=capture_id,
        # inventory_event_id is left unset here: chaining it requires the previously persisted
        # event id, which this module never reads (I1 spec discipline: "entirely in memory, with
        # zero Neo4j I/O"). `app.graph.importer` completes the chain at commit time.
        discovery_scope_id=discovery_scope_id,
        scope_definition_digest=scope_definition_digest,
        discoverer_identity=discoverer_identity,
        adapter_identities=tuple(sorted(a.adapter_identity for a in registry.adapters)),
        mapping_rule_identities=tuple(sorted(a.mapping_rule_version for a in registry.adapters)),
        status=status,
        discovered_source_ids=discovered_source_ids,
        tombstones=in_scope_tombstones,
        capture_time=capture_time,
        diagnostics=tuple(diagnostics),
    )


def _run_result(
    discoverer: SourceDiscoverer,
    registry: SourceAdapterRegistry,
    discovery_outcome: DiscoveryOutcome,
    tombstones: Sequence[Tombstone],
    *,
    status: InventoryStatus,
    commit_eligible: bool,
    merged_model: ArchitectureModel,
    source_outcomes: dict[str, SourceRunOutcome],
    diagnostics: Sequence[IngestionDiagnostic],
) -> DiscoveryRunResult:
    """Every `run_discovery` return path's result, with its inventory snapshot built from the same
    status, source outcomes and diagnostics."""
    return DiscoveryRunResult(
        inventory_status=status,
        commit_eligible=commit_eligible,
        discovery_scope_id=discovery_outcome.discovery_scope_id,
        scope_definition_digest=discovery_outcome.scope_definition_digest,
        merged_model=merged_model,
        source_outcomes=source_outcomes,
        diagnostics=tuple(diagnostics),
        inventory_snapshot=_build_inventory_snapshot(
            discoverer_identity=discoverer.discoverer_identity,
            registry=registry,
            discovery_scope_id=discovery_outcome.discovery_scope_id,
            scope_definition_digest=discovery_outcome.scope_definition_digest,
            status=status,
            source_outcomes=source_outcomes,
            diagnostics=diagnostics,
            tombstones=tombstones,
        ),
        expected_prior_inventory_revision=discovery_outcome.expected_prior_inventory_revision,
    )


def _bind_identity_manifests(
    loaded_sources: Sequence[LoadedSource], run_diagnostics: list[IngestionDiagnostic]
) -> tuple[BindingIndex, bool]:
    """Phase 1: discover and validate every ArchitectureIdentityBindings manifest before any
    OpenAPI/AsyncAPI document is mapped (I1 spec §4.2's two-phase evaluation order). Appends to
    `run_diagnostics`; returns the binding index and whether phase 1 failed - judged over every run
    diagnostic so far, the discoverer's own included."""
    binding_documents = []
    known_source_instance_ids = {s.descriptor.source_instance_id for s in loaded_sources}
    for loaded in loaded_sources:
        if not _is_identity_bindings_document(loaded.document):
            continue
        parsed, diagnostics = parse_architecture_identity_bindings(
            loaded.document, locator=loaded.descriptor.locator
        )
        run_diagnostics.extend(diagnostics)
        if parsed is not None:
            binding_documents.append(parsed)

    binding_index, binding_index_diagnostics = build_binding_index(
        binding_documents, known_source_instance_ids=known_source_instance_ids
    )
    run_diagnostics.extend(binding_index_diagnostics)

    phase1_failed = bool(binding_index_diagnostics) or any(
        d.code
        in (
            DiagnosticCode.MANIFEST_BINDING_SHAPE_INVALID,
            DiagnosticCode.MANIFEST_BINDING_POINTER_INVALID,
            DiagnosticCode.SERVICE_IDENTITY_INVALID,
        )
        for d in run_diagnostics
    )
    return binding_index, phase1_failed


def _map_sources(
    mappable_sources: Sequence[LoadedSource],
    registry: SourceAdapterRegistry,
    *,
    resolver: ServiceIdentityResolver,
    shared_identity_resolver: SharedIdentityResolver,
    mapping_context_digest: str,
    run_diagnostics: list[IngestionDiagnostic],
) -> dict[str, SourceRunOutcome]:
    """Maps every non-manifest source with the adapter that claims it, one dependency phase at a
    time (a later phase sees the earlier phases' merged model), then gives every unclaimed source a
    REJECTED_UNSUPPORTED outcome. Appends each outcome's diagnostics to `run_diagnostics`."""
    source_outcomes: dict[str, SourceRunOutcome] = {}
    phase_upstream_model = ArchitectureModel()

    for phase in registry.phases():
        phase_models: list[ArchitectureModel] = []
        for loaded in mappable_sources:
            source_instance_id = loaded.descriptor.source_instance_id
            if source_instance_id in source_outcomes:
                continue  # already resolved in an earlier phase iteration (shouldn't happen)

            adapter = registry.adapter_for(loaded)
            if adapter is None:
                continue  # handled once, after all phases (no adapter ever claims it)
            if adapter.dependency_phase != phase:
                continue

            enriched = loaded.model_copy(
                update={
                    "descriptor": loaded.descriptor.model_copy(
                        update={
                            "adapter_identity": adapter.adapter_identity,
                            "mapping_rule_id": adapter.adapter_identity,
                            "mapping_rule_version": adapter.mapping_rule_version,
                        }
                    )
                }
            )
            outcome = adapter.map(
                enriched,
                service_identity=resolver,
                shared_identity=shared_identity_resolver,
                upstream_model=phase_upstream_model,
                mapping_context_digest=mapping_context_digest,
            )
            source_outcomes[source_instance_id] = SourceRunOutcome(
                descriptor_locator=loaded.descriptor.locator,
                outcome=outcome,
                descriptor=enriched.descriptor,
            )
            # A matched adapter's own diagnostics (e.g. why it rejected this source) must be
            # visible at the run level too - `import_discovery_run`'s not-commit-eligible early
            # return discards `source_outcomes` entirely, so without this, a rejected source's own
            # reason would be invisible past discovery. A real gap found while wiring the
            # Kubernetes discoverer/adapter (I2 Draft 0.2 slice 2b-i): no prior source kind's tests
            # exercised a matched-but-rejected source through the full import pipeline.
            run_diagnostics.extend(outcome.diagnostics)
            phase_models.append(outcome.model)

        phase_upstream_model = merge_models([phase_upstream_model, *phase_models])

    unmatched_diagnostics = []
    for loaded in mappable_sources:
        source_instance_id = loaded.descriptor.source_instance_id
        if source_instance_id in source_outcomes:
            continue
        diagnostic = IngestionDiagnostic(
            code=DiagnosticCode.DOCUMENT_PARSE_INVALID,
            message=f"no registered adapter claims {loaded.descriptor.locator!r}",
            source_pointer=loaded.descriptor.locator,
            source_instance_id=source_instance_id,
        )
        unmatched_diagnostics.append(diagnostic)
        source_outcomes[source_instance_id] = SourceRunOutcome(
            descriptor_locator=loaded.descriptor.locator,
            descriptor=loaded.descriptor,
            outcome=AdapterOutcome(
                result=IngestionResult.REJECTED_UNSUPPORTED,
                model=ArchitectureModel(),
                diagnostics=(diagnostic,),
                semantic_input_digest=None,
            ),
        )
    run_diagnostics.extend(unmatched_diagnostics)
    return source_outcomes


def _content_conflicts(
    source_outcomes: Mapping[str, SourceRunOutcome], source_models: Sequence[ArchitectureModel]
) -> tuple[tuple[IngestionDiagnostic, ...], frozenset[str] | set[str]]:
    """Cross-source content conflicts and the sources that caused one.

    §8.1/§9.1: "Two current owners explicitly mapped to one shared Schema ID with different
    canonical hashes are REJECTED_CONFLICT" (and the Message equivalent) - only visible once every
    source's own claims are collected together, so this runs on the pre-merge per-source model
    list, before merge_models' own first-wins dedup could discard the disagreement. I2 Draft 0.2
    §7.1's equivalent rule for infrastructure entity contributions is checked the same way, at the
    same point, even though nothing populates infrastructure_contributions yet."""
    infrastructure_conflicts = detect_infrastructure_entity_content_conflicts(source_models)
    # v0.5.0 I4 §6.2: a Subscription bound to two different Topics across sources.
    subscription_conflicts = detect_subscription_topic_binding_conflicts(
        {sid: run_outcome.outcome.model for sid, run_outcome in source_outcomes.items()}
    )
    conflicted_source_instance_ids = (
        infrastructure_conflicts.conflicted_source_instance_ids
        | subscription_conflicts.conflicted_source_instance_ids
    )
    content_conflicts = tuple(
        sorted(
            detect_shared_claim_content_conflicts(source_models)
            + infrastructure_conflicts.diagnostics
            + subscription_conflicts.diagnostics,
            key=lambda d: (d.code, d.source_pointer or ""),
        )
    )
    return content_conflicts, conflicted_source_instance_ids


def run_discovery(
    discoverer: SourceDiscoverer,
    *,
    registry: SourceAdapterRegistry | None = None,
    migration_mappings: SharedIdentityMappingIndex | None = None,
    tombstones: Sequence[Tombstone] = (),
) -> DiscoveryRunResult:
    """I2 Draft 0.2 §3 prerequisite slice, items 1/3: the source-neutral discovery entry point -
    accepts any configured `SourceDiscoverer`, with no source-kind branch inside this function.
    `run_filesystem_discovery` below is now a thin compatibility wrapper over this function so every
    existing filesystem caller/test keeps working unchanged.
    """
    registry = registry or default_registry()
    shared_identity_index = migration_mappings or EMPTY_SHARED_IDENTITY_INDEX
    discovery_outcome = discoverer.discover()

    def result(**fields) -> DiscoveryRunResult:
        return _run_result(discoverer, registry, discovery_outcome, tombstones, **fields)

    if not discovery_outcome.enumeration_complete:
        status = classify_inventory_status(source_results=(), discoverer_enumeration_complete=False)
        return result(
            status=status,
            commit_eligible=run_is_eligible_to_commit(status),
            merged_model=ArchitectureModel(),
            source_outcomes={},
            diagnostics=discovery_outcome.diagnostics,
        )

    # Canonical order (by source_instance_id) so permuting discovery order can never change the
    # result - I1 spec §4.2's permutation-independence requirement.
    loaded_sources = tuple(
        sorted(discovery_outcome.loaded_sources, key=lambda s: s.descriptor.source_instance_id)
    )
    run_diagnostics: list[IngestionDiagnostic] = list(discovery_outcome.diagnostics)

    binding_index, phase1_failed = _bind_identity_manifests(loaded_sources, run_diagnostics)
    if phase1_failed:
        status = classify_inventory_status(source_results=(), discoverer_enumeration_complete=False)
        return result(
            status=status,
            commit_eligible=run_is_eligible_to_commit(status),
            merged_model=ArchitectureModel(),
            source_outcomes={},
            diagnostics=run_diagnostics,
        )

    source_outcomes = _map_sources(
        [
            loaded
            for loaded in loaded_sources
            if not _is_identity_bindings_document(loaded.document)
        ],
        registry,
        resolver=_RunServiceIdentityResolver(_binding_index_to_pointer_bindings(binding_index)),
        shared_identity_resolver=_RunSharedIdentityResolver(shared_identity_index),
        mapping_context_digest=_compute_mapping_context_digest(
            binding_index, registry, shared_identity_index
        ),
        run_diagnostics=run_diagnostics,
    )
    source_models = [outcome.outcome.model for outcome in source_outcomes.values()]

    content_conflicts, conflicted_source_instance_ids = _content_conflicts(
        source_outcomes, source_models
    )
    if content_conflicts:
        run_diagnostics.extend(content_conflicts)
        # §10: `K8S_RESOURCE_CONFLICT`'s outcome is "REJECTED_CONFLICT; no commit" - a source
        # result, not only a run-level status. Every source whose contribution disagreed carries
        # that result, rather than staying reported as ACCEPTED in a run it caused to reject.
        source_outcomes = {
            source_instance_id: (
                _rejected_conflict(run_outcome)
                if source_instance_id in conflicted_source_instance_ids
                else run_outcome
            )
            for source_instance_id, run_outcome in source_outcomes.items()
        }
        return result(
            status=InventoryStatus.PARTIAL,
            commit_eligible=False,
            merged_model=ArchitectureModel(),
            source_outcomes=source_outcomes,
            diagnostics=run_diagnostics,
        )

    merged_model = merge_models(source_models)

    # I1 §7: canonical validation precedes the reconciliation plan. v0.5.0 I5 finding F1: a
    # violation used to escape the import as an exception (an HTTP 500) with no per-source result.
    # Each issue is attributed to the sources whose emitted elements it implicates; those sources
    # are REJECTED_INVALID and the run is PARTIAL. An issue no source can be attributed to makes the
    # run FAILED. Either way nothing commits, and every source keeps exactly one result (I1 §10).
    validation_issues = canonical_validation_issues(merged_model)
    if validation_issues:
        source_outcomes, validation_diagnostics, unattributed = _reject_canonically_invalid(
            source_outcomes, validation_issues
        )
        run_diagnostics.extend(validation_diagnostics)
        return result(
            status=InventoryStatus.FAILED if unattributed else InventoryStatus.PARTIAL,
            commit_eligible=False,
            merged_model=ArchitectureModel(),
            source_outcomes=source_outcomes,
            diagnostics=run_diagnostics,
        )

    status = classify_inventory_status(
        source_results=[o.outcome.result for o in source_outcomes.values()],
        discoverer_enumeration_complete=True,
    )
    return result(
        status=status,
        commit_eligible=run_is_eligible_to_commit(status),
        merged_model=merged_model,
        source_outcomes=source_outcomes,
        diagnostics=run_diagnostics,
    )


def run_filesystem_discovery(
    config: FilesystemSourceConfig,
    *,
    registry: SourceAdapterRegistry | None = None,
    migration_mappings: SharedIdentityMappingIndex | None = None,
    tombstones: Sequence[Tombstone] = (),
) -> DiscoveryRunResult:
    """Thin compatibility wrapper over `run_discovery` for the filesystem source kind - every
    existing caller/test keeps working unchanged."""
    return run_discovery(
        FilesystemSourceDiscoverer(config),
        registry=registry,
        migration_mappings=migration_mappings,
        tombstones=tombstones,
    )


def run_kubernetes_discovery(
    config: KubernetesSourceConfig,
    *,
    registry: SourceAdapterRegistry | None = None,
    migration_mappings: SharedIdentityMappingIndex | None = None,
    tombstones: Sequence[Tombstone] = (),
) -> DiscoveryRunResult:
    """Thin wrapper over `run_discovery` for the Kubernetes source kind, mirroring
    `run_filesystem_discovery`'s exact shape (I2 Draft 0.2 slice 2b-i)."""
    return run_discovery(
        KubernetesSourceDiscoverer(config),
        registry=registry,
        migration_mappings=migration_mappings,
        tombstones=tombstones,
    )
