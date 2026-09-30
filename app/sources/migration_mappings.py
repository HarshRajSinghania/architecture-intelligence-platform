"""I1 spec §5.1.1/§8.1/§9/§9.1's explicit shared-identity mapping mechanism: a versioned artifact
binding exact `(SourceInstanceId, normalized definition document path, source pointer)` triples to
a full canonical Schema/Message/Queue ID (widened by v0.5.0 I4 spec §7.3 with Topic ids and
Topic-bound Subscription ids), so a source's owner-scoped default identity can be
deliberately overridden to preserve a prior (e.g. v0.4.2, pre-owner-scoped) canonical meaning, or to
merge two independent sources' claims onto one shared entity. The document path is part of the
lookup key, not folded into the pointer, because one SourceInstanceId's own bounded multi-file
`$ref` closure (PR3b) can resolve the identical relative pointer inside two different files.

Structurally mirrors `app.sources.manifest_bindings` (shape validation via `Draft202012Validator`,
frozen dataclasses, then a sorted-dedup-then-conflict-detection index build) - the same "shape, then
pointer/target validity, then cross-entry conflict" pipeline. The one deliberate difference: Service
bindings match by *pointer prefix* (`app.sources.pointers.pointer_prefix_matches`, since one binding
can cover a whole subtree of an operation's constructs); a Schema/Message/Queue migration mapping
matches by *exact* document path plus pointer (§8.1: "bind one or more *exact* `(SourceInstanceId,
source pointer)` pairs") - a schema/message/queue's own resolved definition location is always a
single, fully-resolved document+pointer pair, never a subtree.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.common.encoding import sha256_hex, unicode_nfc
from app.sources.identity import normalize_relative_posix_path
from app.sources.model import DiagnosticCode, IngestionDiagnostic, SubscriptionMapping
from app.sources.pointers import decode_pointer_tokens, is_well_formed_pointer

_MAPPING_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["sourceInstanceId", "documentPath", "pointer"],
    "properties": {
        "sourceInstanceId": {"type": "string", "minLength": 1},
        # §8.1/§9.1: "the normalized definition source pointer is the normalized relative document
        # path plus decoded RFC 6901 pointer" - required alongside `pointer`, not folded into it,
        # since a single SourceInstanceId's own bounded multi-file `$ref` closure (PR3b) can resolve
        # the same relative pointer inside two different files.
        "documentPath": {"type": "string", "minLength": 1},
        "pointer": {"type": "string"},
    },
}


def _entry_schema(*target_fields: str) -> dict:
    # v0.5.0 I4 spec §7.3: a `subscriptionMappings` entry carries three required target fields
    # (`topicId`, `subscriptionName`, `subscriptionId`), every other kind exactly one.
    schema = dict(_MAPPING_ENTRY_SCHEMA)
    schema["required"] = [*_MAPPING_ENTRY_SCHEMA["required"], *target_fields]
    schema["properties"] = {
        **_MAPPING_ENTRY_SCHEMA["properties"],
        **{name: {"type": "string", "minLength": 1} for name in target_fields},
    }
    return schema


# I1 spec §5.1.1: "The migration artifact SHALL bind ... to ... prior qualified Schema, Message,
# and Queue IDs." `kind`/`apiVersion` naming is this module's own choice (not spec-given, flagged
# for review), mirroring `ArchitectureIdentityBindings`'s own additionalProperties-false discipline.
_MIGRATION_MAPPINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["apiVersion", "kind", "metadata"],
    "properties": {
        "apiVersion": {"const": "aip.dev/v1"},
        "kind": {"const": "AipSharedIdentityMappings"},
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "revision"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "revision": {"type": "string", "minLength": 1},
            },
        },
        "schemaMappings": {"type": "array", "items": _entry_schema("schemaId")},
        "messageMappings": {"type": "array", "items": _entry_schema("messageId")},
        "queueMappings": {"type": "array", "items": _entry_schema("queueId")},
        # v0.5.0 I4 spec §7.3: the two widened arrays. A topicMappings entry's presence at a
        # Channel pointer is itself positive Topic-kind evidence (no generic `kind` field).
        "topicMappings": {"type": "array", "items": _entry_schema("topicId")},
        "subscriptionMappings": {
            "type": "array",
            "items": _entry_schema("topicId", "subscriptionName", "subscriptionId"),
        },
    },
}

_VALIDATOR = Draft202012Validator(_MIGRATION_MAPPINGS_SCHEMA)

_TARGET_ID_RE = {
    "schema": re.compile(r"^schema:\S+$"),
    "message": re.compile(r"^message:\S+$"),
    "queue": re.compile(r"^queue:\S+$"),
    "topic": re.compile(r"^topic:\S+$"),
    "subscription": re.compile(r"^subscription:\S+$"),
}

# (array name, target-id field, kind) for every mapping array, in document order.
_MAPPING_ARRAYS = (
    ("schemaMappings", "schemaId", "schema"),
    ("messageMappings", "messageId", "message"),
    ("queueMappings", "queueId", "queue"),
    ("topicMappings", "topicId", "topic"),
    ("subscriptionMappings", "subscriptionId", "subscription"),
)


@dataclass(frozen=True)
class IdentityMappingEntry:
    source_instance_id: str
    document_path: str
    pointer: str
    pointer_tokens: tuple[str, ...]
    target_id: str
    # v0.5.0 I4 spec §7.3: set only for a subscriptionMappings entry, whose `target_id` is the
    # full Subscription id and which additionally binds the exact canonical Topic id and the
    # explicit Subscription name (normalized to NFC without trimming/case folding).
    bound_topic_id: str | None = None
    subscription_name: str | None = None


@dataclass(frozen=True)
class MigrationMappingsDocument:
    artifact_id: str
    artifact_revision: str
    locator: str
    # §5.3: "Each mapping entry retains its stable artifact identity, revision, content digest,
    # attribution, normalized source pointers, targets, and semantic options." `content_digest` is
    # the SHA-256 of this artifact file's own exact raw bytes (mirroring §5.2's `content_sha256`
    # convention for source documents); `locator` above already serves as this artifact's
    # attribution (which configured file declared it) - both are threaded into the mapping-context
    # digest projection by `app.ingestion.orchestrator._mapping_entry_context`, not just carried
    # here inertly. There are no per-artifact "semantic options" this mechanism exposes (no
    # case-folding/wildcard/etc. configuration), so that part of §5.3's list has nothing to project.
    content_digest: str
    schema_mappings: tuple[IdentityMappingEntry, ...] = field(default_factory=tuple)
    message_mappings: tuple[IdentityMappingEntry, ...] = field(default_factory=tuple)
    queue_mappings: tuple[IdentityMappingEntry, ...] = field(default_factory=tuple)
    topic_mappings: tuple[IdentityMappingEntry, ...] = field(default_factory=tuple)
    subscription_mappings: tuple[IdentityMappingEntry, ...] = field(default_factory=tuple)


def _shape_errors(document: dict) -> list[str]:
    # jsonschema error paths mix str (property names) and int (array indices) elements - two
    # errors whose paths happen to disagree in type at the same position (e.g. one nested under an
    # array index, another under a differently-shaped branch) would raise TypeError from plain
    # `list` comparison. Stringifying each path element first keeps sorting deterministic without
    # requiring every element to be pairwise comparable.
    return [
        error.message
        for error in sorted(
            _VALIDATOR.iter_errors(document), key=lambda e: [str(p) for p in e.path]
        )
    ]


def _parse_entries(
    raw_entries: Sequence[dict], *, id_field: str, kind: str, locator: str, array_name: str
) -> tuple[tuple[IdentityMappingEntry, ...], list[IngestionDiagnostic]]:
    diagnostics: list[IngestionDiagnostic] = []
    entries: list[IdentityMappingEntry] = []
    for index, raw in enumerate(raw_entries):
        pointer = raw["pointer"]
        target_id = raw[id_field]
        source_pointer = f"/{array_name}/{index}"

        if not is_well_formed_pointer(pointer):
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_SHAPE_INVALID,
                    message=f"{array_name}[{index}]: malformed pointer {pointer!r}",
                    source_pointer=f"{source_pointer}/pointer",
                    source_instance_id=raw["sourceInstanceId"],
                )
            )
            continue
        if not _TARGET_ID_RE[kind].fullmatch(target_id):
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_TARGET_INVALID,
                    message=f"{array_name}[{index}]: {id_field} {target_id!r} is not a valid {kind} id",
                    source_pointer=f"{source_pointer}/{id_field}",
                    source_instance_id=raw["sourceInstanceId"],
                )
            )
            continue
        bound_topic_id = None
        subscription_name = None
        if kind == "subscription":
            bound_topic_id = raw["topicId"]
            if not _TARGET_ID_RE["topic"].fullmatch(bound_topic_id):
                diagnostics.append(
                    IngestionDiagnostic(
                        code=DiagnosticCode.MIGRATION_MAPPING_TARGET_INVALID,
                        message=(
                            f"{array_name}[{index}]: topicId {bound_topic_id!r} is not a valid "
                            "topic id"
                        ),
                        source_pointer=f"{source_pointer}/topicId",
                        source_instance_id=raw["sourceInstanceId"],
                    )
                )
                continue
            subscription_name = unicode_nfc(raw["subscriptionName"])

        entries.append(
            IdentityMappingEntry(
                source_instance_id=raw["sourceInstanceId"],
                document_path=normalize_relative_posix_path(raw["documentPath"]),
                pointer=pointer,
                pointer_tokens=decode_pointer_tokens(pointer),
                target_id=target_id,
                bound_topic_id=bound_topic_id,
                subscription_name=subscription_name,
            )
        )
    return tuple(entries), diagnostics


def parse_migration_mappings(
    document: dict, *, locator: str, content_digest: str
) -> tuple[MigrationMappingsDocument | None, list[IngestionDiagnostic]]:
    """Parses and validates one migration-mappings document - shape conformance, RFC 6901
    well-formedness of each `pointer`, and each target id's kind-specific grammar. Does not check
    cross-document/cross-entry duplicates or conflicts (that's `build_shared_identity_index`'s job,
    run across every configured document at once) or whether `sourceInstanceId` exists in a real
    inventory (mirroring `parse_architecture_identity_bindings`'s own scope split). `content_digest`
    is opaque to this function (§5.3's SHA-256-of-exact-bytes convention is `load_migration_
    mappings`'s responsibility, since only it has the raw bytes) - it is carried straight through
    onto the returned `MigrationMappingsDocument` unchanged.
    """
    shape_errors = _shape_errors(document)
    if shape_errors:
        return None, [
            IngestionDiagnostic(
                code=DiagnosticCode.MIGRATION_MAPPING_SHAPE_INVALID,
                message=message,
                source_pointer=locator,
            )
            for message in shape_errors
        ]

    diagnostics: list[IngestionDiagnostic] = []
    parsed_arrays: dict[str, tuple[IdentityMappingEntry, ...]] = {}
    for array_name, id_field, kind in _MAPPING_ARRAYS:
        entries, entry_diagnostics = _parse_entries(
            document.get(array_name) or (),
            id_field=id_field,
            kind=kind,
            locator=locator,
            array_name=array_name,
        )
        parsed_arrays[kind] = entries
        diagnostics.extend(entry_diagnostics)
    if diagnostics:
        return None, diagnostics

    parsed = MigrationMappingsDocument(
        artifact_id=document["metadata"]["id"],
        artifact_revision=document["metadata"]["revision"],
        locator=locator,
        content_digest=content_digest,
        schema_mappings=parsed_arrays["schema"],
        message_mappings=parsed_arrays["message"],
        queue_mappings=parsed_arrays["queue"],
        topic_mappings=parsed_arrays["topic"],
        subscription_mappings=parsed_arrays["subscription"],
    )
    return parsed, []


def _kind_entries(
    document: MigrationMappingsDocument, *, kind: str
) -> tuple[IdentityMappingEntry, ...]:
    return {
        "schema": document.schema_mappings,
        "message": document.message_mappings,
        "queue": document.queue_mappings,
        "topic": document.topic_mappings,
        "subscription": document.subscription_mappings,
    }[kind]


def _entry_payload(entry: IdentityMappingEntry) -> tuple[str, str | None, str | None]:
    # I4 spec §7.3: a subscriptionMappings entry's identity payload is the Subscription id *and*
    # its Topic binding and name - two entries at one key agreeing on the id but disagreeing on
    # either binding are a conflict, never a silent first-wins. For every other kind the extra
    # members are None, so this reduces to exactly the pre-I4 target-id comparison.
    return (entry.target_id, entry.bound_topic_id, entry.subscription_name)


def _entry_sort_key(entry: IdentityMappingEntry) -> tuple:
    return (
        entry.source_instance_id,
        entry.document_path,
        entry.pointer_tokens,
        entry.target_id,
        entry.bound_topic_id or "",
        entry.subscription_name or "",
    )


def _build_kind_entry_index(
    documents: Sequence[MigrationMappingsDocument], *, kind: str
) -> tuple[dict[tuple[str, str, str], IdentityMappingEntry], list[IngestionDiagnostic]]:
    """Sorted-dedup-then-conflict, mirroring `manifest_bindings.build_binding_index`: an identical
    (source_instance_id, document_path, pointer, target_id) quadruple repeated across files
    collapses silently (permutation-independent by construction); the same (source_instance_id,
    document_path, pointer) bound to two *different* target ids is `MIGRATION_MAPPING_CONFLICT`.
    `document_path` is part of the key (not folded into `pointer`) because a single
    SourceInstanceId's own bounded multi-file `$ref` closure (PR3b) can resolve the same relative
    pointer inside two different files - §8.1/§9.1's "normalized definition source pointer" is
    document path plus RFC 6901 pointer together, never the pointer alone.
    """
    raw_entries = [entry for document in documents for entry in _kind_entries(document, kind=kind)]
    for entry in raw_entries:
        _check_subscription_binding_invariant(entry, kind=kind)
    sorted_entries = sorted(raw_entries, key=_entry_sort_key)

    index: dict[tuple[str, str, str], IdentityMappingEntry] = {}
    diagnostics: list[IngestionDiagnostic] = []
    seen: set[tuple] = set()
    for entry in sorted_entries:
        full = (entry.source_instance_id, entry.document_path, entry.pointer, _entry_payload(entry))
        if full in seen:
            continue
        seen.add(full)

        key = (entry.source_instance_id, entry.document_path, entry.pointer)
        if key in index and _entry_payload(index[key]) != _entry_payload(entry):
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_CONFLICT,
                    message=(
                        f"conflicting {kind} migration mapping for {entry.source_instance_id!r} "
                        f"at {entry.document_path!r}{entry.pointer!r}: "
                        f"{_describe_payload(index[key])} vs {_describe_payload(entry)}"
                    ),
                    source_pointer=entry.pointer,
                    source_instance_id=entry.source_instance_id,
                )
            )
            continue
        index[key] = entry

    return index, diagnostics


def _check_subscription_binding_invariant(entry: IdentityMappingEntry, *, kind: str) -> None:
    """`bound_topic_id`/`subscription_name` are set exactly for subscriptionMappings entries.
    `parse_migration_mappings` guarantees this, but `build_shared_identity_index` also accepts
    programmatically-built documents - fail fast on a malformed one rather than indexing a
    `SubscriptionMapping` with missing fields or silently ignoring stray binding fields."""
    has_binding = (entry.bound_topic_id is not None, entry.subscription_name is not None)
    expected = (True, True) if kind == "subscription" else (False, False)
    if has_binding != expected:
        raise ValueError(
            f"{kind} mapping entry at {entry.document_path!r}{entry.pointer!r}: "
            "bound_topic_id/subscription_name must be set for, and only for, subscription mappings"
        )


def _subscription_mapping(entry: IdentityMappingEntry) -> SubscriptionMapping:
    # `_check_subscription_binding_invariant` already rejected every subscription entry lacking
    # either binding field, so both are set here.
    assert entry.bound_topic_id is not None and entry.subscription_name is not None
    return SubscriptionMapping(
        topic_id=entry.bound_topic_id,
        subscription_name=entry.subscription_name,
        subscription_id=entry.target_id,
    )


def _describe_payload(entry: IdentityMappingEntry) -> str:
    if entry.bound_topic_id is None:
        return repr(entry.target_id)
    return (
        f"(topicId={entry.bound_topic_id!r}, subscriptionName={entry.subscription_name!r}, "
        f"subscriptionId={entry.target_id!r})"
    )


def _build_kind_index(
    documents: Sequence[MigrationMappingsDocument], *, kind: str
) -> tuple[dict[tuple[str, str, str], str], list[IngestionDiagnostic]]:
    entry_index, diagnostics = _build_kind_entry_index(documents, kind=kind)
    return {key: entry.target_id for key, entry in entry_index.items()}, diagnostics


@dataclass(frozen=True)
class SharedIdentityMappingIndex:
    schema_index: dict[tuple[str, str, str], str] = field(default_factory=dict)
    message_index: dict[tuple[str, str, str], str] = field(default_factory=dict)
    queue_index: dict[tuple[str, str, str], str] = field(default_factory=dict)
    topic_index: dict[tuple[str, str, str], str] = field(default_factory=dict)
    subscription_index: dict[tuple[str, str, str], SubscriptionMapping] = field(
        default_factory=dict
    )
    documents: tuple[MigrationMappingsDocument, ...] = field(default_factory=tuple)

    def schema_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self.schema_index.get((source_instance_id, document_path, pointer))

    def message_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self.message_index.get((source_instance_id, document_path, pointer))

    def queue_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self.queue_index.get((source_instance_id, document_path, pointer))

    def topic_id_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> str | None:
        return self.topic_index.get((source_instance_id, document_path, pointer))

    def subscription_mapping_for(
        self, *, source_instance_id: str, document_path: str, pointer: str
    ) -> SubscriptionMapping | None:
        return self.subscription_index.get((source_instance_id, document_path, pointer))


EMPTY_SHARED_IDENTITY_INDEX = SharedIdentityMappingIndex()


def build_shared_identity_index(
    documents: Sequence[MigrationMappingsDocument],
) -> tuple[SharedIdentityMappingIndex, list[IngestionDiagnostic]]:
    """Merges every configured migration-mapping document into one lookup index, usable by any
    adapter regardless of which file(s) declared which entries - callers that need to distinguish
    the bundled-example artifact from any other configured one (e.g. for the mapping-context
    digest's `bundledMigrationMappings` vs. `sharedSchemaMappings`/etc. split) do so by filtering
    `documents` on `artifact_id` before or after this call, not by any flag this index itself
    carries.
    """
    schema_index, schema_diagnostics = _build_kind_index(documents, kind="schema")
    message_index, message_diagnostics = _build_kind_index(documents, kind="message")
    queue_index, queue_diagnostics = _build_kind_index(documents, kind="queue")
    topic_index, topic_diagnostics = _build_kind_index(documents, kind="topic")
    subscription_entries, subscription_diagnostics = _build_kind_entry_index(
        documents, kind="subscription"
    )
    diagnostics = [
        *schema_diagnostics,
        *message_diagnostics,
        *queue_diagnostics,
        *topic_diagnostics,
        *subscription_diagnostics,
    ]
    return (
        SharedIdentityMappingIndex(
            schema_index=schema_index,
            message_index=message_index,
            queue_index=queue_index,
            topic_index=topic_index,
            subscription_index={
                key: _subscription_mapping(entry) for key, entry in subscription_entries.items()
            },
            documents=tuple(documents),
        ),
        diagnostics,
    )


def load_migration_mappings(
    paths: Sequence[Path],
) -> tuple[SharedIdentityMappingIndex, tuple[IngestionDiagnostic, ...]]:
    """Reads and parses every configured migration-mapping file (`app.settings.SourcesConfig.
    migrations`), then merges them into one index. A missing/unreadable file or one that isn't
    well-formed YAML/a mapping at its root is diagnosed rather than raised or silently skipped -
    §5.1.1: "Missing or modified migration configuration is diagnosed and MUST NOT fall back to a
    directory slug or name-derived identity."
    """
    diagnostics: list[IngestionDiagnostic] = []
    documents: list[MigrationMappingsDocument] = []

    for path in paths:
        locator = str(path)
        try:
            raw_bytes = path.read_bytes()
        except OSError as exc:
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_FILE_UNAVAILABLE,
                    message=f"{locator}: {exc}",
                    source_pointer=locator,
                )
            )
            continue

        try:
            parsed_yaml = yaml.safe_load(raw_bytes)
        except yaml.YAMLError as exc:
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_SHAPE_INVALID,
                    message=f"{locator}: {exc}",
                    source_pointer=locator,
                )
            )
            continue
        if not isinstance(parsed_yaml, dict):
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.MIGRATION_MAPPING_SHAPE_INVALID,
                    message=f"{locator}: root document is not a mapping",
                    source_pointer=locator,
                )
            )
            continue

        content_digest = sha256_hex(raw_bytes)
        document, parse_diagnostics = parse_migration_mappings(
            parsed_yaml, locator=locator, content_digest=content_digest
        )
        diagnostics.extend(parse_diagnostics)
        if document is not None:
            documents.append(document)

    index, index_diagnostics = build_shared_identity_index(documents)
    diagnostics.extend(index_diagnostics)
    return index, tuple(diagnostics)
