from collections.abc import Iterator

from jsonschema import Draft202012Validator

from app.sources.reference_resolution import parse_ref_uri

OPENAPI_SCHEMA = {
    "type": "object",
    "required": ["openapi", "info", "paths"],
    "properties": {
        "openapi": {"type": "string"},
        "info": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
        "paths": {"type": "object"},
    },
}

ASYNCAPI_SCHEMA = {
    "type": "object",
    # "channels" is intentionally not required: I1 spec §9 - "A document with no channels is
    # accepted as a Service-only source."
    "required": ["asyncapi", "info"],
    "properties": {
        "asyncapi": {"type": "string"},
        "info": {
            "type": "object",
            "required": ["title"],
            "properties": {"title": {"type": "string"}},
        },
        "channels": {"type": "object"},
    },
}

MANIFEST_SCHEMA = {
    "type": "object",
    "required": ["service"],
    "properties": {
        "service": {"type": "string"},
        "calls": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["service", "operationId"],
                "properties": {"service": {"type": "string"}, "operationId": {"type": "string"}},
            },
        },
    },
}


class SourceValidationError(ValueError):
    def __init__(self, source_file: str, errors: list[str]):
        self.source_file = source_file
        self.errors = errors
        super().__init__(f"{source_file}: {'; '.join(errors)}")


def _structural_errors(document: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        error.message
        for error in sorted(validator.iter_errors(document), key=lambda e: list(e.path))
    ]


def _iter_refs(node: object) -> Iterator[str]:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            yield ref
        for value in node.values():
            yield from _iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_refs(item)


def _ref_resolves(ref: str, document: dict) -> bool:
    node: object = document
    try:
        for part in ref.lstrip("#/").split("/"):
            token = part.replace("~1", "/").replace("~0", "~")
            # A JSON-pointer walk over an untyped document: a non-indexable node is a dangling
            # $ref, reported by the TypeError catch below, which pyright can't see.
            node = node[token]  # pyright: ignore[reportIndexIssue]
    except (KeyError, TypeError, IndexError):
        return False
    return True


def _dangling_ref_errors(document: dict) -> list[str]:
    """Same-document (`#/...`) dangling-`$ref` checking only, cheap and pre-disk. A relative-file
    reference (a non-empty path, no scheme/authority) is deliberately NOT flagged here as of PR3b -
    this validator has no notion of the approved source root or sibling files, and `_ref_resolves`
    only ever looks inside `document`, so it cannot correctly evaluate a cross-file `$ref` at all
    (it would incorrectly flag every legitimate one as dangling). Existence, containment, cycles,
    and limits for a relative-file reference are resolved entirely by
    `app.sources.reference_resolution` later, inside the adapter's own `map()`. A remote (scheme- or
    authority-qualified) reference is NOT flagged here either - see `find_remote_reference` - since
    I1 spec §8.1 makes it `REJECTED_UNSUPPORTED`, a materially different qualification category
    from the generic structural `REJECTED_INVALID` every error in this function raises via
    `SourceValidationError`, so it cannot share this function's single error-list-and-raise shape.
    """
    errors = []
    for ref in _iter_refs(document):
        parsed = parse_ref_uri(ref)
        if (
            not parsed.scheme
            and not parsed.authority
            and not parsed.path
            and not _ref_resolves(ref, document)
        ):
            errors.append(f"dangling $ref: {ref}")
    return errors


def find_remote_reference(document: dict) -> str | None:
    """I1 spec §8.1: "remote/non-local reference -> REJECTED_UNSUPPORTED for the whole source" -
    kept as its own pre-check (called from each adapter's `map()`, mirroring
    `check_supported_dialect_version`) rather than folded into `_dangling_ref_errors`, because it
    must produce `REJECTED_UNSUPPORTED` + `REMOTE_REFERENCE_UNSUPPORTED`, not the generic
    `REJECTED_INVALID` every `_dangling_ref_errors` case raises via `SourceValidationError`.
    Returns the first remote (non-empty URI scheme or authority) `$ref` string found, or `None`.
    """
    for ref in _iter_refs(document):
        parsed = parse_ref_uri(ref)
        if parsed.scheme or parsed.authority:
            return ref
    return None


def check_supported_dialect_version(
    document: dict, *, dialect_key: str, accepted_versions: frozenset[str]
) -> str | None:
    """I1 spec §8/§9's exact-version enforcement: "accept exactly OpenAPI 3.0.3/3.1.0/3.1.2... any
    other version is REJECTED_UNSUPPORTED" / "accept exactly AsyncAPI 2.6.0... all other versions...
    are REJECTED_UNSUPPORTED". Returns `None` on success, or an error message on a version that
    doesn't exactly match. Kept as its own pre-check (called from each adapter's `map()`, not
    folded into `validate_openapi_document`/`validate_asyncapi_document`) because it must produce
    `REJECTED_UNSUPPORTED`, a materially different qualification category from the generic
    structural `REJECTED_INVALID` every other error in this module raises via `SourceValidationError`
    - and it must run after `supports()` already claimed the document (an unsupported-version
    OpenAPI document is still unambiguously "an OpenAPI document" and must get this specific
    diagnostic, not silently fall through to "no adapter claims this").
    """
    version = document.get(dialect_key)
    if not isinstance(version, str) or version not in accepted_versions:
        return f"unsupported {dialect_key} version: {version!r} (accepted: {sorted(accepted_versions)})"
    return None


def validate_openapi_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, OPENAPI_SCHEMA) + _dangling_ref_errors(document)
    if errors:
        raise SourceValidationError(source_file, errors)


def validate_asyncapi_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, ASYNCAPI_SCHEMA) + _dangling_ref_errors(document)
    if errors:
        raise SourceValidationError(source_file, errors)


def validate_manifest_document(document: dict, *, source_file: str) -> None:
    errors = _structural_errors(document, MANIFEST_SCHEMA)
    if errors:
        raise SourceValidationError(source_file, errors)
