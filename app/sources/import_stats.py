"""The result/statistics types of an import run (I1 §10). Plain frozen dataclasses with no graph or
Neo4j dependency, so the import report (`app.ingestion.import_report`) can consume them without
importing the graph writer. Re-exported from `app.graph.importer` for existing callers."""

from dataclasses import dataclass

from app.canonical.model import ArchitectureModel
from app.sources.inventory import InventoryStatus
from app.sources.model import IngestionDiagnostic, IngestionResult


@dataclass(frozen=True)
class ClaimEffectSet:
    """One category of a source's canonical reconciliation effects (I1 §10 "canonical planned/
    committed effects"), by stable claim identity. Public canonical facts are listed by id or
    relation key. Internal-only facts (Kubernetes infrastructure entities, contributions and claims,
    Pub/Sub carriers, and Evidence) are only counted: I2 §9 forbids exposing them."""

    public_node_ids: tuple[str, ...] = ()
    relation_keys: tuple[str, ...] = ()
    internal_count: int = 0

    @property
    def is_empty(self) -> bool:
        return not (self.public_node_ids or self.relation_keys or self.internal_count)


@dataclass(frozen=True)
class SourceClaimEffects:
    """What one source's reconciliation changed, from its claim-reconciliation plans and the
    before/after property snapshots that also decide `graph_revision_advanced`. An unchanged replay
    has empty effects, although the importer still executes idempotent MERGEs."""

    added: ClaimEffectSet = ClaimEffectSet()
    changed: ClaimEffectSet = ClaimEffectSet()
    expired: ClaimEffectSet = ClaimEffectSet()
    ownership_removed: ClaimEffectSet = ClaimEffectSet()

    @property
    def is_empty(self) -> bool:
        return all(
            category.is_empty
            for category in (self.added, self.changed, self.expired, self.ownership_removed)
        )


@dataclass(frozen=True)
class SourceImportStats:
    source_instance_id: str
    locator: str
    result: IngestionResult
    nodes_written: int
    relations_written: int
    nodes_expired: int
    relations_expired: int
    graph_revision_advanced: bool
    # `nodes_written`/`relations_written` count MERGE operations, which an unchanged replay also
    # executes; `effects` is the canonical effect set (None only where no reconciliation ran).
    effects: SourceClaimEffects | None = None


@dataclass(frozen=True)
class EmittedCounts:
    """What one source's adapter mapped (I1 §10 "emitted counts"), before any reconciliation."""

    services: int
    operations: int
    schemas: int
    messages: int
    queues: int
    topics: int
    subscriptions: int
    relations: int
    infrastructure_entities: int
    infrastructure_claims: int

    @classmethod
    def of(cls, model: ArchitectureModel) -> "EmittedCounts":
        return cls(
            services=len(model.services),
            operations=len(model.operations),
            schemas=len(model.schemas),
            messages=len(model.messages),
            queues=len(model.queues),
            topics=len(model.topics),
            subscriptions=len(model.subscriptions),
            relations=len(model.relations),
            infrastructure_entities=len(model.infrastructure_entities),
            infrastructure_claims=len(model.infrastructure_claims),
        )


@dataclass(frozen=True)
class SourceRunResult:
    """I1 spec §10: "Each source receives exactly one result" - one discovered source's own result
    and diagnostics for a discovery run, recorded whether or not the run committed (unlike
    `SourceImportStats`, which only exists for sources actually reconciled into the graph). v0.5.0
    I5 finding F2: a non-committing run previously dropped every per-source result."""

    source_instance_id: str
    locator: str
    result: IngestionResult
    diagnostics: tuple[IngestionDiagnostic, ...]
    # I1 §10's "dialects, identities, emitted counts": the claiming adapter (None when no adapter
    # claimed the source), the document's own declared dialect version, the adapter's semantic
    # input digest, the Service ids the source emits, and what the adapter mapped - recorded
    # whether or not the run commits.
    source_kind: str = ""
    adapter_identity: str | None = None
    mapping_rule_version: str | None = None
    dialect_version: str | None = None
    semantic_input_digest: str | None = None
    service_ids: tuple[str, ...] = ()
    emitted: EmittedCounts | None = None


@dataclass(frozen=True)
class TombstoneDecision:
    """I1 spec §10's report entry for one in-scope explicit tombstone evaluated by a committing run:
    whether it was accepted against the committed inventory, and the rejection reason if not."""

    target_source_instance_id: str
    tombstone_revision: str
    accepted: bool
    reason: str | None


@dataclass(frozen=True)
class ImportRunStats:
    inventory_status: InventoryStatus
    committed: bool
    per_source: dict[str, SourceImportStats]
    removed_source_instance_ids: tuple[str, ...]
    diagnostics: tuple[IngestionDiagnostic, ...]
    # v0.5.0 I5 finding F2 (I1 spec §10 import report) - defaulted so existing constructors keep
    # working. `source_results` holds every discovered source's own result on every return path,
    # committing or not; `inventory_revision` is the committed revision this run wrote (None when
    # the run did not commit).
    source_results: tuple[SourceRunResult, ...] = ()
    discovery_scope_id: str | None = None
    scope_definition_digest: str | None = None
    inventory_revision: str | None = None
    tombstone_decisions: tuple[TombstoneDecision, ...] = ()
    # The expirations each authorized removal committed, one per `removed_source_instance_ids`.
    removal_stats: tuple[SourceImportStats, ...] = ()
