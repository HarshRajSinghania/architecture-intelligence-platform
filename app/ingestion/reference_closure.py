"""Per-source `$ref` resolution cache, transitive reference-closure enforcement, and the semantic-input
digest projection built from it (I1 spec §8.1), shared by the OpenAPI and AsyncAPI adapters."""

from pathlib import Path

from app.canonical.model import ArchitectureModel
from app.sources.identity import (
    normalize_relative_posix_path,
    normalized_document_and_reference_projection_bytes,
)
from app.sources.model import DiagnosticCode, IngestionDiagnostic, IngestionResult, LoadedSource
from app.sources.reference_resolution import (
    ReferenceResolutionError,
    ResolutionCache,
    new_resolution_cache,
    walk_transitive_closure,
)
from app.sources.registry import AdapterOutcome


def build_resolution_cache(loaded: LoadedSource) -> tuple[ResolutionCache, str]:
    """Builds the per-source `ResolutionCache` used for every `$ref` this source's adapter resolves
    (schema/message/payload definitions alike), plus the root document's own normalized relative
    path - the key both the cache and every `resolve_and_read`/`resolve_and_normalize_schema` call
    for this source key off.

    `loaded.source_root` is empty only for a `LoadedSource` built directly by a unit test with no
    real filesystem backing (see its own docstring) - there, no cross-file resolution is reachable
    anyway (only fragment-only `#/...` refs are), so the root's own locator string stands in for its
    relative path: self-consistent for cache keying, even though it isn't a real relative-to-root
    path.
    """
    locator = loaded.descriptor.locator
    if loaded.source_root:
        root_relative_path = normalize_relative_posix_path(
            str(Path(locator).relative_to(Path(loaded.source_root)))
        )
    else:
        root_relative_path = normalize_relative_posix_path(locator)

    source_root = Path(loaded.source_root) if loaded.source_root else Path(locator).parent
    root_bytes = Path(locator).read_bytes() if loaded.source_root else b""
    cache = new_resolution_cache(
        source_root,
        root_relative_path=root_relative_path,
        root_document=loaded.document,
        root_bytes=root_bytes,
    )
    return cache, root_relative_path


_REFERENCE_ERROR_RESULT = {
    DiagnosticCode.REMOTE_REFERENCE_UNSUPPORTED: IngestionResult.REJECTED_UNSUPPORTED,
    DiagnosticCode.REFERENCE_CYCLE_UNSUPPORTED: IngestionResult.REJECTED_UNSUPPORTED,
    DiagnosticCode.REFERENCE_LIMIT_EXCEEDED: IngestionResult.REJECTED_UNSUPPORTED,
    DiagnosticCode.REFERENCE_INVALID: IngestionResult.REJECTED_INVALID,
}


def rejected_outcome_for_reference_error(
    exc: ReferenceResolutionError, *, source_pointer: str
) -> AdapterOutcome:
    """§8.1's construct-outcome table: any `$ref` resolution failure anywhere in a schema/message/
    payload tree rejects the *whole source* - "Whole-source rejection occurs only for ... reference
    cycle/limit, invalid structure/reference..." - never just the one affected relation.
    """
    return AdapterOutcome(
        result=_REFERENCE_ERROR_RESULT[exc.code],
        model=ArchitectureModel(),
        diagnostics=(
            IngestionDiagnostic(code=exc.code, message=exc.message, source_pointer=source_pointer),
        ),
        semantic_input_digest=None,
    )


def enforce_reference_closure(
    document: dict, *, root_relative_path: str, cache: ResolutionCache, source_pointer: str
) -> AdapterOutcome | None:
    """§8's authoritative depth/file-count/byte-budget and cross-file-cycle enforcement. The
    discoverer's own `walk_transitive_closure` call (`filesystem_discoverer._best_effort_closure_
    digest`) is deliberately best-effort/non-fatal - it exists only to compute the provenance
    digest early. THIS call, made by the adapter itself before any per-construct schema resolution,
    is the actual enforcement: without it, a reference chain whose per-hop resolution individually
    succeeds (e.g. 20 single-`$ref` hops, each resolving one file at a time) would never trip any
    limit, since no single `resolve_and_normalize_schema` call for one construct ever counts total
    depth/files/bytes across the *whole* closure - only a closure-wide walk can. Returns `None` on
    success, or the whole-source rejection to return immediately from `map()` on failure.
    """
    try:
        walk_transitive_closure(document, root_relative_path=root_relative_path, cache=cache)
    except ReferenceResolutionError as exc:
        return rejected_outcome_for_reference_error(exc, source_pointer=source_pointer)
    return None


def semantic_input_digest_bytes(cache: ResolutionCache) -> bytes:
    """I1 spec §5.3's "normalized document/reference projection": every document this source's
    resolution touched - the root plus its whole resolved closure - ordered by normalized relative
    path. Must be called only after the source's full closure has already been loaded into `cache`
    (i.e. after `enforce_reference_closure` has run) - otherwise a referenced-file-only edit would
    be invisible to the resulting `semantic_input_digest` and the revision fence would never see it.
    """
    return normalized_document_and_reference_projection_bytes(cache.documents)
