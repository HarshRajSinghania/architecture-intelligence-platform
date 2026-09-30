"""I1 spec §10 import report (v0.5.0 I5 finding F2): the versioned public shape of
`POST /api/import` and `POST /api/import/service/{serviceId}`.

The report is additive. The pre-existing `import_id`, `committed` and `sources` keys keep their
exact meaning (`sources` is the per-source reconciliation stats of the configured runs), and
`report_version` plus `runs` carry what I1 §10 requires the report to include: the discovered
sources and inventories (every source's own result, including the rejected sources of a run that
did not commit, and the inventory status and revision), each source's adapter, dialect and
identities, its emitted counts, its canonical committed effects by claim identity, removals with
their effects, tombstone
decisions, and diagnostics. Unsupported constructs, unresolved references and conflicts are
reported as diagnostic codes. A run that does not commit has no planned mutations (I1 §6), so its
effects are null.

`runs` is the deterministic semantic projection of I1 §10: it carries no capture ids, timestamps
or byte-level content digests, and every list in it is sorted. Diagnostics are public only as a
stable `code`, the `source_instance_id`, and a sanitized `source_pointer`. Diagnostic messages are
never exposed, because they can contain absolute host paths and snippets of rejected input (the I2
§5 sanitization rule); the server log keeps them.

Every value the report copies from operator input or from a diagnostic is sanitized to null rather
than validated, so building the report can never fail after a run has already committed.

The committed JSON Schema (`schemas/import/v0.5/import-report.schema.json`) is generated from these
models by `app.ingestion.import_report_schema` and pinned by a test.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.common.locators import sanitize_source_locator
from app.sources.import_stats import (
    ClaimEffectSet,
    EmittedCounts,
    ImportRunStats,
    SourceClaimEffects,
    SourceImportStats,
    SourceRunResult,
)
from app.sources.inventory import InventoryStatus
from app.sources.model import DiagnosticCode, IngestionDiagnostic, IngestionResult
from app.sources.tombstones import TombstoneRejectionReason

ReportVersion = Literal["aip-import-report/1"]
REPORT_VERSION = get_args(ReportVersion)[0]

RunKind = Literal["filesystem", "kubernetes"]

# Formats of the identities AIP itself computes (I1 §5.1, §6). Character classes only: the patterns
# must also compile under pydantic-core's regex engine, so no lookaround. Operator-supplied values
# (a tombstone's target and revision) are deliberately not constrained, so a malformed tombstone
# can never turn the report itself into an error.
_SOURCE_ID = r"^urn:aip:source:(filesystem|kubernetes):[0-9a-f]{64}$"
_SCOPE_ID = r"^urn:aip:discovery-scope:[0-9a-f]{64}$"
_INVENTORY_REVISION = r"^urn:aip:inventory-revision:[0-9a-f]{64}$"
_DIGEST = r"^[0-9a-f]{64}$"
# A public locator is relative: never absolute, never a Windows path, never a URL query/fragment.
_RELATIVE_LOCATOR = r"^[^/\\?#][^\\?#]*$"
# A document's declared dialect version (`openapi: 3.1.0`, `asyncapi: 2.6.0`). It is document
# content, so anything outside this short token form is reported as null.
_DIALECT_VERSION = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,63}$"

_SOURCE_ID_RE = re.compile(_SOURCE_ID)
_DIALECT_VERSION_RE = re.compile(_DIALECT_VERSION)

SourceId = Annotated[str, Field(pattern=_SOURCE_ID)]
NonNegative = Annotated[int, Field(ge=0)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ReportDiagnostic(_Frozen):
    code: DiagnosticCode
    source_instance_id: SourceId | None
    source_pointer: str | None


class ReportEmittedCounts(_Frozen):
    """What the source's adapter mapped, before reconciliation (I1 §10 "emitted counts")."""

    services: NonNegative
    operations: NonNegative
    schemas: NonNegative
    messages: NonNegative
    queues: NonNegative
    topics: NonNegative
    subscriptions: NonNegative
    relations: NonNegative
    infrastructure_entities: NonNegative
    infrastructure_claims: NonNegative


def _sorted_unique(values: list[str], name: str) -> None:
    if values != sorted(set(values)):
        raise ValueError(f"{name} must be unique and sorted")


class ReportEffectSet(_Frozen):
    """One category of canonical effects, by stable identity. Public canonical facts are listed
    (node ids and `TYPE:source:target` relation keys); internal-only facts (Kubernetes
    infrastructure, Pub/Sub carriers, Evidence) are only counted, because I2 §9 keeps them out of
    every public payload."""

    node_ids: Annotated[list[str], Field(json_schema_extra={"uniqueItems": True})]
    relation_keys: Annotated[list[str], Field(json_schema_extra={"uniqueItems": True})]
    internal_count: NonNegative

    @model_validator(mode="after")
    def _sorted(self) -> ReportEffectSet:
        _sorted_unique(self.node_ids, "node_ids")
        _sorted_unique(self.relation_keys, "relation_keys")
        return self

    @property
    def is_empty(self) -> bool:
        return not (self.node_ids or self.relation_keys or self.internal_count)


class ReportEffects(_Frozen):
    """The canonical committed effects of one source's reconciliation (I1 §10), from its claim
    reconciliation plan: claims it newly owns (`added`), retained claims it changed (`changed`),
    dropped claims no other source will own after the run (`expired`), and dropped claims that
    survive for another owner (`ownership_removed`). Each set is attributed to this source alone
    and does not depend on the order in which the run's sources are reconciled. An unchanged
    replay has four empty sets and does not advance the graph revision. Null in a run that did not
    commit: such a run changes nothing (I1 §6)."""

    graph_revision_advanced: bool
    added: ReportEffectSet
    changed: ReportEffectSet
    expired: ReportEffectSet
    ownership_removed: ReportEffectSet


class ReportSourceResult(_Frozen):
    source_instance_id: SourceId
    source_kind: RunKind
    locator: Annotated[str, Field(pattern=_RELATIVE_LOCATOR)] | None
    result: IngestionResult
    adapter_identity: str | None
    mapping_rule_version: str | None
    dialect_version: Annotated[str, Field(pattern=_DIALECT_VERSION)] | None
    semantic_input_digest: Annotated[str, Field(pattern=_DIGEST)] | None
    service_ids: Annotated[list[str], Field(json_schema_extra={"uniqueItems": True})]
    emitted: ReportEmittedCounts
    effects: ReportEffects | None
    diagnostics: list[ReportDiagnostic]

    @model_validator(mode="after")
    def _sorted_service_ids(self) -> ReportSourceResult:
        _sorted_unique(self.service_ids, "service_ids")
        return self


class ReportRemoval(_Frozen):
    """One previously committed source removed by an authorized removal, with its effects (only
    `expired` and `ownership_removed` can be non-empty)."""

    source_instance_id: SourceId
    effects: ReportEffects

    @model_validator(mode="after")
    def _removal_only_removes(self) -> ReportRemoval:
        if not (self.effects.added.is_empty and self.effects.changed.is_empty):
            raise ValueError("a removal adds and changes nothing")
        return self


class ReportTombstoneDecision(_Frozen):
    target_source_instance_id: str
    tombstone_revision: str
    accepted: bool
    reason: TombstoneRejectionReason | None


class ReportRun(_Frozen):
    kind: RunKind
    configured_source_id: str
    discovery_scope_id: Annotated[str, Field(pattern=_SCOPE_ID)] | None
    scope_definition_digest: Annotated[str, Field(pattern=_DIGEST)] | None
    inventory_status: InventoryStatus
    committed: bool
    inventory_revision: Annotated[str, Field(pattern=_INVENTORY_REVISION)] | None
    source_results: list[ReportSourceResult]
    removals: list[ReportRemoval]
    tombstones: list[ReportTombstoneDecision]
    diagnostics: list[ReportDiagnostic]

    @model_validator(mode="after")
    def _consistent(self) -> ReportRun:
        # Ordering guarantees a JSON Schema cannot express: the run is the deterministic semantic
        # projection of I1 §10, so every list has one order.
        removed = [r.source_instance_id for r in self.removals]
        if removed != sorted(set(removed)):
            raise ValueError("removals must be unique and sorted by source_instance_id")
        ids = [r.source_instance_id for r in self.source_results]
        if ids != sorted(set(ids)):
            raise ValueError("source_results must be unique and sorted by source_instance_id")
        # I1 §6: only a committed run has effects or removals.
        if self.committed:
            if any(r.effects is None for r in self.source_results):
                raise ValueError("every source of a committed run has effects")
        elif self.removals or any(r.effects is not None for r in self.source_results):
            raise ValueError("a run that did not commit has no effects and no removals")
        return self


class ReportSourceStats(_Frozen):
    """The pre-existing `sources` entry shape (`SourceImportStats`), unchanged."""

    source_instance_id: SourceId
    locator: str
    result: IngestionResult
    nodes_written: int
    relations_written: int
    nodes_expired: int
    relations_expired: int
    graph_revision_advanced: bool


class ImportReport(_Frozen):
    """The full `POST /api/import` response."""

    import_id: str
    committed: bool
    sources: dict[str, ReportSourceStats]
    report_version: ReportVersion
    runs: list[ReportRun]


class ServiceImportReport(ImportReport):
    """The full `POST /api/import/service/{serviceId}` response."""

    service_id: str


@dataclass(frozen=True)
class ConfiguredRun:
    """One configured source's discovery run, as the import endpoint executed it."""

    kind: RunKind
    configured_source_id: str
    root: Path
    stats: ImportRunStats


def _root_forms(root: Path) -> tuple[str, ...]:
    forms = {str(root), os.path.abspath(root)}
    try:
        forms.add(str(root.resolve()))
    except OSError:
        pass
    return tuple(sorted((form for form in forms if form), key=len, reverse=True))


def _relative_to_root(value: str, root_forms: Sequence[str]) -> str | None:
    """`value` as a relative POSIX path when it is the configured root or lies under it, else
    None. `.` stands for the root itself."""
    for root in root_forms:
        if value == root:
            return "."
        prefix = root.rstrip("/") + "/"
        if value.startswith(prefix):
            relative = PurePosixPath(value[len(prefix) :]).as_posix()
            return sanitize_source_locator(relative)
    return None


def sanitize_locator(locator: str | None, *, root: Path) -> str | None:
    """A public locator: relative to the configured root, or an already relative POSIX path, or
    None. Never an absolute host path."""
    if locator is None:
        return None
    relative = _relative_to_root(locator, _root_forms(root))
    if relative is not None:
        return relative
    return sanitize_source_locator(locator)


# The diagnostic codes whose pointer is always an RFC 6901 JSON Pointer into a document, or an
# entity or resource id - never a host file path. Every emitting site of these codes was checked,
# and `tests/unit/test_import_report.py` re-checks them by scanning the source. Any other code may
# carry a file locator (a tombstone or mapping file, a discovered document), so its pointer is
# public only as a path relative to the configured root.
DOCUMENT_POINTER_CODES = frozenset(
    {
        DiagnosticCode.AMBIGUOUS,
        DiagnosticCode.MANIFEST_BINDING_POINTER_INVALID,
        DiagnosticCode.MANIFEST_BINDING_UNKNOWN_SOURCE,
        DiagnosticCode.MANIFEST_CALL_SOURCE_UNRESOLVED,
        DiagnosticCode.MANIFEST_CALL_TARGET_UNRESOLVED,
        DiagnosticCode.MIGRATION_MAPPING_CONFLICT,
        DiagnosticCode.MIGRATION_MAPPING_TARGET_INVALID,
        DiagnosticCode.QUEUE_EVIDENCE_MISSING,
        DiagnosticCode.QUEUE_IDENTITY_CONFLICT,
        DiagnosticCode.QUEUE_KIND_CONFLICT,
        DiagnosticCode.SERVICE_IDENTITY_CONFLICT,
        DiagnosticCode.SERVICE_IDENTITY_INVALID,
        DiagnosticCode.SERVICE_IDENTITY_UNRESOLVED,
        DiagnosticCode.SERVICE_WORKLOAD_MAPPING_TARGET_INVALID,
        DiagnosticCode.SUBSCRIPTION_IDENTITY_CONFLICT,
        DiagnosticCode.SUBSCRIPTION_IDENTITY_MISSING,
        DiagnosticCode.TOPIC_IDENTITY_CONFLICT,
    }
)

# Absolute forms on any platform: a Windows drive path (`C:\x`, `C:/x`) or a UNC or backslash
# path. POSIX absolute paths are handled by the leading `/` rule in `sanitize_pointer`.
_WINDOWS_ABSOLUTE = re.compile(r"^([A-Za-z]:[\\/]|[\\/]{2}|\\)")


def sanitize_pointer(pointer: str | None, *, code: DiagnosticCode, root: Path) -> str | None:
    """A public diagnostic pointer, decided syntactically (never by what exists on this host).

    Diagnostic pointers are heterogeneous: RFC 6901 JSON Pointers, entity or resource ids, and
    file locators. A JSON Pointer and an absolute POSIX path share the same form (`/a/b`), so a
    value's own text cannot tell them apart; the diagnostic code does. In order:
    1. the configured root, or a path under it, becomes relative to it (`.` for the root itself);
    2. a Windows absolute or UNC path, any backslash, a URL, or a `..` segment becomes null;
    3. a value starting with `/` is kept only for a `DOCUMENT_POINTER_CODES` code, and is null
       otherwise, whether or not such a path exists;
    4. anything else (a relative locator, an id, a resource pointer) is kept."""
    if pointer is None:
        return None
    relative = _relative_to_root(pointer, _root_forms(root))
    if relative is not None:
        return relative
    if (
        _WINDOWS_ABSOLUTE.match(pointer)
        or "\\" in pointer
        or "://" in pointer
        or ".." in pointer.split("/")
    ):
        return None
    if pointer.startswith("/") and code not in DOCUMENT_POINTER_CODES:
        return None
    return pointer


def _public_source_id(value: str | None) -> str | None:
    """A diagnostic's source id, or null when it is not a well-formed AIP source id: a rejected
    tombstone's diagnostic carries its operator-supplied target, which may be malformed."""
    if value is None or _SOURCE_ID_RE.fullmatch(value) is None:
        return None
    return value


def _public_dialect_version(value: str | None) -> str | None:
    if value is None or _DIALECT_VERSION_RE.fullmatch(value) is None:
        return None
    return value


def _diagnostic(diagnostic: IngestionDiagnostic, *, root: Path) -> ReportDiagnostic:
    return ReportDiagnostic(
        code=diagnostic.code,
        source_instance_id=_public_source_id(diagnostic.source_instance_id),
        source_pointer=sanitize_pointer(diagnostic.source_pointer, code=diagnostic.code, root=root),
    )


def _sorted_diagnostics(
    diagnostics: Sequence[IngestionDiagnostic], *, root: Path
) -> list[ReportDiagnostic]:
    rendered = {
        _diagnostic(diagnostic, root=root).model_dump_json(): _diagnostic(diagnostic, root=root)
        for diagnostic in diagnostics
    }
    return sorted(
        rendered.values(),
        key=lambda d: (d.code.value, d.source_instance_id or "", d.source_pointer or ""),
    )


def _emitted(counts: EmittedCounts | None) -> ReportEmittedCounts:
    if counts is None:
        return ReportEmittedCounts(**dict.fromkeys(ReportEmittedCounts.model_fields, 0))
    return ReportEmittedCounts(**asdict(counts))


def _effect_set(effects: ClaimEffectSet) -> ReportEffectSet:
    return ReportEffectSet(
        node_ids=sorted(set(effects.public_node_ids)),
        relation_keys=sorted(set(effects.relation_keys)),
        internal_count=effects.internal_count,
    )


def _effects(stats: SourceImportStats | None) -> ReportEffects | None:
    if stats is None or stats.effects is None:
        return None
    return _report_effects(stats, stats.effects)


def _report_effects(stats: SourceImportStats, effects: SourceClaimEffects) -> ReportEffects:
    return ReportEffects(
        graph_revision_advanced=stats.graph_revision_advanced,
        added=_effect_set(effects.added),
        changed=_effect_set(effects.changed),
        expired=_effect_set(effects.expired),
        ownership_removed=_effect_set(effects.ownership_removed),
    )


def _source_result(
    source_result: SourceRunResult, *, kind: RunKind, stats: ImportRunStats, root: Path
) -> ReportSourceResult:
    return ReportSourceResult(
        source_instance_id=source_result.source_instance_id,
        source_kind=kind,
        locator=sanitize_locator(source_result.locator, root=root),
        result=source_result.result,
        adapter_identity=source_result.adapter_identity,
        mapping_rule_version=source_result.mapping_rule_version,
        dialect_version=_public_dialect_version(source_result.dialect_version),
        semantic_input_digest=source_result.semantic_input_digest,
        service_ids=sorted(set(source_result.service_ids)),
        emitted=_emitted(source_result.emitted),
        effects=(
            _effects(stats.per_source.get(source_result.source_instance_id))
            if stats.committed
            else None
        ),
        diagnostics=_sorted_diagnostics(source_result.diagnostics, root=root),
    )


def build_run(configured: ConfiguredRun) -> ReportRun:
    stats = configured.stats
    root = configured.root
    return ReportRun(
        kind=configured.kind,
        configured_source_id=configured.configured_source_id,
        discovery_scope_id=stats.discovery_scope_id,
        scope_definition_digest=stats.scope_definition_digest,
        inventory_status=stats.inventory_status,
        committed=stats.committed,
        inventory_revision=stats.inventory_revision,
        source_results=[
            _source_result(source_result, kind=configured.kind, stats=stats, root=root)
            for source_result in sorted(stats.source_results, key=lambda r: r.source_instance_id)
        ],
        removals=sorted(
            (
                ReportRemoval(
                    source_instance_id=removal.source_instance_id,
                    effects=_report_effects(removal, removal.effects),
                )
                for removal in stats.removal_stats
                if removal.effects is not None
            ),
            key=lambda r: r.source_instance_id,
        ),
        tombstones=sorted(
            (
                ReportTombstoneDecision(
                    target_source_instance_id=decision.target_source_instance_id,
                    tombstone_revision=decision.tombstone_revision,
                    accepted=decision.accepted,
                    reason=(
                        TombstoneRejectionReason(decision.reason)
                        if decision.reason is not None
                        else None
                    ),
                )
                for decision in stats.tombstone_decisions
            ),
            key=lambda t: (t.target_source_instance_id, t.tombstone_revision),
        ),
        diagnostics=_sorted_diagnostics(stats.diagnostics, root=root),
    )


def _source_stats(stats: SourceImportStats) -> ReportSourceStats:
    return ReportSourceStats(
        source_instance_id=stats.source_instance_id,
        locator=stats.locator,
        result=stats.result,
        nodes_written=stats.nodes_written,
        relations_written=stats.relations_written,
        nodes_expired=stats.nodes_expired,
        relations_expired=stats.relations_expired,
        graph_revision_advanced=stats.graph_revision_advanced,
    )


def build_import_report(import_id: str, runs: Sequence[ConfiguredRun]) -> ImportReport:
    """The `POST /api/import` response. `sources` keeps its pre-v1 construction exactly: the
    per-source stats of every run, merged in run order."""
    combined: dict[str, SourceImportStats] = {}
    for configured in runs:
        combined.update(configured.stats.per_source)
    return ImportReport(
        import_id=import_id,
        committed=all(configured.stats.committed for configured in runs),
        sources={sid: _source_stats(stats) for sid, stats in combined.items()},
        report_version=REPORT_VERSION,
        runs=sorted(
            (build_run(configured) for configured in runs),
            key=lambda run: (run.kind, run.configured_source_id),
        ),
    )
