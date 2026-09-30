from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.canonical.model import ArchitectureModel
from app.sources.model import (
    NOT_SUPPLIED,
    IngestionDiagnostic,
    IngestionResult,
    LoadedSource,
    NotSupplied,
    SourceKind,
    SubscriptionMapping,
)
from app.sources.service_identity import ServiceIdentityResolution


class ServiceIdentityResolver(Protocol):
    """I1 spec §4.1's per-construct Service-identity resolution, exposed to adapters as an injected
    closure rather than a pre-resolved value: resolution is per-construct (a document root vs. a
    deeper `x-aip-service-id` vs. a manifest binding at a pointer prefix), and only the adapter
    walking its own document knows its constructs' pointers. The orchestrator builds one resolver
    per discovery run, closing over phase-1's completed `BindingIndex` and any configured mappings,
    and hands the same resolver to every adapter - adapters never see the `BindingIndex` directly.
    """

    def resolve(
        self, *, source_instance_id: str, construct_pointer: str, extension_value: str | None
    ) -> ServiceIdentityResolution: ...


class SharedIdentityResolver(Protocol):
    """I1 spec §5.1.1/§8.1/§9/§9.1's explicit shared-identity/migration mapping mechanism, exposed
    to adapters the same way `ServiceIdentityResolver` is: an injected lookup, not a pre-resolved
    value, since only the adapter walking its own document knows a construct's exact resolved
    location. `None` means no configured mapping applies to that exact `(source_instance_id,
    document_path, pointer)` triple - the adapter falls back to its own owner-scoped default
    identity formula. `document_path` is the normalized relative path of the document the pointer
    resolved into (§8.1/§9.1: "the normalized definition source pointer is the normalized relative
    document path plus decoded RFC 6901 pointer") - required alongside `pointer` because one
    SourceInstanceId's own bounded multi-file `$ref` closure can resolve the same relative pointer
    inside two different files.
    """

    def schema_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None: ...
    def message_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None: ...
    def queue_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None: ...
    # v0.5.0 I4 spec §7.3: a Channel pointer's configured full Topic id, and a subscribe-operation
    # pointer's configured (Topic binding, Subscription name, Subscription id).
    def topic_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None: ...
    def subscription_mapping_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> SubscriptionMapping | None: ...


@dataclass(frozen=True)
class AdapterOutcome:
    """I1 spec §10: "Each source receives exactly one result." Adapters return this instead of
    raising for source/construct-level problems, so the orchestrator's inventory/commit-gate/
    reconciliation stages have a structured outcome to reason about rather than a stack unwind.
    `semantic_input_digest` is `None` only when `result` never reached a normalized projection to
    hash (e.g. a shape so invalid that no document/reference projection could be built).
    """

    result: IngestionResult
    model: ArchitectureModel
    diagnostics: tuple[IngestionDiagnostic, ...]
    semantic_input_digest: str | None


class SourceAdapter(Protocol):
    """I1 spec §4/§7: a registered adapter, not a hard-coded per-source-kind branch. "Adapters MUST
    NOT write directly to the graph or call another adapter's mapping logic" - `map()` may only
    read `upstream_model`, never mutate it; `dependency_phase` is the sole, generic mechanism for a
    later-phase adapter (e.g. the Architecture Manifest adapter) to see an earlier phase's merged
    result, without the orchestrator branching on source kind.
    """

    adapter_identity: str
    mapping_rule_version: str
    dependency_phase: int

    def supports(self, loaded: LoadedSource) -> bool: ...

    def map(
        self,
        loaded: LoadedSource,
        *,
        service_identity: ServiceIdentityResolver,
        shared_identity: SharedIdentityResolver,
        upstream_model: ArchitectureModel,
        mapping_context_digest: str,
    ) -> AdapterOutcome: ...


@dataclass(frozen=True)
class DiscoveryOutcome:
    """I1 spec §6: a discovery run's raw enumeration, before any per-source load/validate/map
    result is known. `enumeration_complete=False` means the discoverer itself could not produce a
    trustworthy source list (missing root, auth failure, timeout, truncation, pagination error -
    §6's own list of preserve-prior-state triggers) - see
    `app.sources.commit_gate.classify_inventory_status`.

    `discovery_scope_id`/`scope_definition_digest` are carried at this level (not only inside each
    `LoadedSource.descriptor`) so a caller can still identify the scope when zero sources were
    found - a legitimately empty scope must be distinguishable from "we don't know what scope this
    was." I2 Draft 0.2 §3/§8 requires a snapshot for every discovery attempt, including a failed
    one, so a discoverer SHOULD compute and return both fields whenever they are pure functions of
    its own *configured* values (never requiring the underlying source to actually be reachable) -
    `FilesystemSourceDiscoverer` does this even for a missing root, since both formulas are
    computed only from configured id/path strings (a real bug found in review: it used to return
    `None` for exactly this case, discarding a computable scope). `None` remains legitimate only for
    a discoverer kind whose scope identity genuinely cannot be established without successful
    acquisition.
    """

    loaded_sources: tuple[LoadedSource, ...]
    enumeration_complete: bool
    diagnostics: tuple[IngestionDiagnostic, ...]
    discovery_scope_id: str | None = None
    scope_definition_digest: str | None = None
    expected_prior_inventory_revision: str | None | NotSupplied = NOT_SUPPLIED
    """I2 Draft 0.2 §4.2 (slice 2b-ii): a discoverer that can extract a declared predecessor
    expectation from its own trusted, accepted input sets this to that value (`None` legitimately
    means "expect no prior committed inventory"); `NOT_SUPPLIED` (the default) means no predecessor
    check should be performed - every discoverer kind's behavior before this field existed, and
    still `FilesystemSourceDiscoverer`'s only behavior."""


class SourceDiscoverer(Protocol):
    source_kind: SourceKind
    discoverer_identity: str

    def discover(self) -> DiscoveryOutcome: ...


class AmbiguousAdapterRegistrationError(ValueError):
    """Raised when more than one registered adapter claims `supports()` for the same `LoadedSource`
    - a registration bug (adapters should partition document shapes disjointly), never a per-source
    runtime outcome a discovery run could legitimately produce.
    """


class SourceAdapterRegistry:
    """I1 spec §7: "The orchestrator MUST NOT contain a hard-coded branch per source kind." Adapters
    declare `supports()`/`map()` and are registered rather than branched on.
    """

    def __init__(self, adapters: Sequence[SourceAdapter]):
        self._adapters = tuple(adapters)

    @property
    def adapters(self) -> tuple[SourceAdapter, ...]:
        return self._adapters

    def adapter_for(self, loaded: LoadedSource) -> SourceAdapter | None:
        matches = [adapter for adapter in self._adapters if adapter.supports(loaded)]
        if len(matches) > 1:
            raise AmbiguousAdapterRegistrationError(
                f"{len(matches)} registered adapters claim to support "
                f"{loaded.descriptor.locator!r}: {[a.adapter_identity for a in matches]!r}"
            )
        return matches[0] if matches else None

    def phases(self) -> tuple[int, ...]:
        return tuple(sorted({adapter.dependency_phase for adapter in self._adapters}))

    def adapters_in_phase(self, phase: int) -> tuple[SourceAdapter, ...]:
        return tuple(adapter for adapter in self._adapters if adapter.dependency_phase == phase)
