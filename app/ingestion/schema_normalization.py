"""Schema normalization shared by the OpenAPI and AsyncAPI adapters: the RFC 8785-hashed canonical
projection of a schema tree (I1 spec §8.1), reference resolution into it, and display naming."""

from dataclasses import dataclass
from typing import Any

from app.common.jcs import canonical_sha256_hex, sort_by_canonical_hash
from app.sources.model import DiagnosticCode
from app.sources.reference_resolution import (
    DEFAULT_MAX_REFERENCE_DEPTH,
    ReferenceResolutionError,
    ResolutionCache,
    resolve_and_read,
)

# I1 spec §8.1: "The canonical projection excludes only description, summary, example, examples,
# and externalDocs." Applied at every level of a normalized schema tree (top-level and every
# nested/referenced construct), not just the top - I1 §8's "map supported inline, array, and
# nested schemas" bullet.
EXCLUDED_SCHEMA_FIELDS = frozenset(
    {"description", "summary", "example", "examples", "externalDocs"}
)


_COMPOSITION_KEYS = ("allOf", "oneOf", "anyOf")


# Keys whose VALUE is a map of arbitrary user-chosen names to sub-schemas - the map's own keys are
# names, never schema annotation keywords, and must never be run through EXCLUDED_SCHEMA_FIELDS
# filtering: a property or definition literally named "description" (or "example", etc.) is real
# schema content, not the schema-level `description` annotation that keyword otherwise denotes.
_NAMED_SCHEMA_MAP_KEYS = frozenset({"properties", "patternProperties", "definitions", "$defs"})


# I1 spec §8.1: "All validation/serialization keywords and every extension key are retained." An
# `x-...` vendor extension's value is arbitrary, opaque vendor data - not a schema construct at
# all - so it must never be run through EXCLUDED_SCHEMA_FIELDS filtering (a nested `description`
# key inside one is real data, not the schema-level annotation) or `$ref`/composition handling.
# Preserved byte-for-byte (already JSON-safe: normalize_non_json_scalars ran at parse time).
_EXTENSION_KEY_PREFIX = "x-"


def _normalize_schema_node(
    node: Any,
    *,
    containing_document_relative_path: str,
    cache: ResolutionCache,
    path_stack: tuple[tuple[str, tuple[str, ...]], ...],
    composition_seen: list[bool],
    depth: int,
    max_depth: int,
    is_named_schema_map: bool = False,
) -> Any:
    """§8.1: "Every admitted schema is converted to a JSON-compatible value, all local references
    are expanded" - recursively substitutes every `$ref` node with its fully-normalized resolved
    target (never leaving a `$ref` key in the output), strips the excluded fields at every level,
    and sorts `allOf`/`oneOf`/`anyOf` branch arrays by canonical hash once their branches are
    themselves normalized. `path_stack` carries (document path, pointer tokens) pairs for the
    current resolution chain only - a target already on this chain is a genuine cycle
    (`REFERENCE_CYCLE_UNSUPPORTED`); a target visited via a different, already-completed branch
    (a diamond) is not tracked here at all and is simply re-normalized, which is safe since this
    walk has no side effects to duplicate.

    `depth` counts every `$ref` hop actually expanded here - same-document (fragment-only) and
    cross-file alike, per ADR 0015's "a same-file chain A -> B -> C is 2 hops even though it
    touches only 1 file". This is the sole authoritative depth enforcement for a same-document (or
    mixed same-document/cross-file) chain: `app.sources.reference_resolution.walk_transitive_
    closure` (run separately, before this, via `enforce_reference_closure`) deliberately skips
    fragment-only refs entirely (it never recurses into that branch, so it has nothing to count),
    and only enforces file-count/byte budgets for the cross-file closure - depth for a chain that
    stays within one document is invisible to it by design.

    `is_named_schema_map` marks a dict reached via a `_NAMED_SCHEMA_MAP_KEYS` key (e.g.
    `properties`): its own keys are arbitrary names, so EXCLUDED_SCHEMA_FIELDS filtering and
    `$ref`/composition handling apply only to each VALUE (a real schema node), never to the map
    itself.
    """
    if isinstance(node, dict):
        if is_named_schema_map:
            return {
                name: _normalize_schema_node(
                    value,
                    containing_document_relative_path=containing_document_relative_path,
                    cache=cache,
                    path_stack=path_stack,
                    composition_seen=composition_seen,
                    depth=depth,
                    max_depth=max_depth,
                )
                for name, value in node.items()
            }

        ref = node.get("$ref")
        if isinstance(ref, str):
            resolved = resolve_and_read(
                containing_document_relative_path=containing_document_relative_path,
                ref=ref,
                cache=cache,
            )
            cycle_key = (resolved.normalized_relative_path, resolved.pointer_tokens)
            if cycle_key in path_stack:
                raise ReferenceResolutionError(
                    code=DiagnosticCode.REFERENCE_CYCLE_UNSUPPORTED,
                    message=f"reference cycle detected at {cycle_key!r}",
                )
            new_depth = depth + 1
            if new_depth > max_depth:
                raise ReferenceResolutionError(
                    code=DiagnosticCode.REFERENCE_LIMIT_EXCEEDED,
                    message=f"reference depth exceeds the maximum of {max_depth}",
                )
            return _normalize_schema_node(
                resolved.target_node,
                containing_document_relative_path=resolved.normalized_relative_path,
                cache=cache,
                path_stack=(*path_stack, cycle_key),
                composition_seen=composition_seen,
                depth=new_depth,
                max_depth=max_depth,
            )

        normalized = {}
        for key, value in node.items():
            if key in EXCLUDED_SCHEMA_FIELDS:
                continue
            if key.startswith(_EXTENSION_KEY_PREFIX):
                normalized[key] = value
                continue
            normalized[key] = _normalize_schema_node(
                value,
                containing_document_relative_path=containing_document_relative_path,
                cache=cache,
                path_stack=path_stack,
                composition_seen=composition_seen,
                depth=depth,
                max_depth=max_depth,
                is_named_schema_map=key in _NAMED_SCHEMA_MAP_KEYS,
            )
        for composition_key in _COMPOSITION_KEYS:
            branches = normalized.get(composition_key)
            if isinstance(branches, list):
                composition_seen.append(True)
                normalized[composition_key] = sort_by_canonical_hash(branches)
        return normalized

    if isinstance(node, list):
        return [
            _normalize_schema_node(
                item,
                containing_document_relative_path=containing_document_relative_path,
                cache=cache,
                path_stack=path_stack,
                composition_seen=composition_seen,
                depth=depth,
                max_depth=max_depth,
            )
            for item in node
        ]

    return node


@dataclass(frozen=True)
class NormalizedSchema:
    normalized_definition_document_path: str
    definition_pointer_tokens: tuple[str, ...]
    canonical_hash: str
    has_uninterpreted_composition: bool
    # The already-computed normalized JSON value `canonical_hash` was hashed from - exposed so a
    # caller (AsyncAPI's message_contract_digest) can build a further projection from the fully
    # *resolved* shape (with every $ref expanded) rather than a raw, possibly-still-`{"$ref": ...}`
    # node, so two sources whose payload $ref differs syntactically but resolves identically
    # correctly compare as equal contracts.
    normalized_value: Any


# `Schema.name`/`Message.name` (app.canonical.model) are required strings - a label only, never
# identity - so a `$ref` that resolves to an entire document with no fragment (e.g. `file.yaml`
# with no `#/...`) has empty `definition_pointer_tokens` and no meaningful "last path segment" to
# use as a name. This deterministic, synthetic placeholder fills that gap; angle brackets can never
# collide with a real YAML/JSON key or OpenAPI component name.
ANONYMOUS_SCHEMA_NAME = "<root>"


def schema_display_name(definition_pointer_tokens: tuple[str, ...]) -> str:
    return definition_pointer_tokens[-1] if definition_pointer_tokens else ANONYMOUS_SCHEMA_NAME


def resolve_and_normalize_schema(
    top_node: dict,
    *,
    own_document_relative_path: str,
    own_pointer_tokens: tuple[str, ...],
    cache: ResolutionCache,
    max_depth: int = DEFAULT_MAX_REFERENCE_DEPTH,
) -> NormalizedSchema:
    """§8.1's full per-construct identity + canonical-hash computation for one top-level schema
    slot (an operation's request/response media-type schema, or a message's payload). `top_node`
    may itself be a `$ref` (identity comes from the resolved target's own document path + pointer)
    or inline (identity is `own_pointer_tokens`, "its own stable request/response/media-type
    pointer"). Raises `ReferenceResolutionError` on any resolution failure anywhere in the tree
    (dangling/invalid/remote/cyclic/over-limit) - callers convert that into the appropriate
    whole-source `REJECTED_*` outcome, per §8.1's construct-outcome table.
    """
    composition_seen: list[bool] = []
    ref = top_node.get("$ref") if isinstance(top_node, dict) else None
    if isinstance(ref, str):
        resolved = resolve_and_read(
            containing_document_relative_path=own_document_relative_path, ref=ref, cache=cache
        )
        definition_document_path = resolved.normalized_relative_path
        definition_pointer_tokens = resolved.pointer_tokens
        normalized = _normalize_schema_node(
            resolved.target_node,
            containing_document_relative_path=resolved.normalized_relative_path,
            cache=cache,
            path_stack=((resolved.normalized_relative_path, resolved.pointer_tokens),),
            composition_seen=composition_seen,
            depth=1,  # the top slot's own $ref is already hop 1 from the root document
            max_depth=max_depth,
        )
    else:
        definition_document_path = own_document_relative_path
        definition_pointer_tokens = own_pointer_tokens
        normalized = _normalize_schema_node(
            top_node,
            containing_document_relative_path=own_document_relative_path,
            cache=cache,
            path_stack=((own_document_relative_path, own_pointer_tokens),),
            composition_seen=composition_seen,
            depth=0,
            max_depth=max_depth,
        )

    return NormalizedSchema(
        normalized_definition_document_path=definition_document_path,
        definition_pointer_tokens=definition_pointer_tokens,
        canonical_hash=canonical_sha256_hex(normalized),
        has_uninterpreted_composition=bool(composition_seen),
        normalized_value=normalized,
    )
