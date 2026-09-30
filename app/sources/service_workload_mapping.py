"""v0.5.0 I3 spec §8.1's configured Service<->Workload identity-mapping artifact (Path B) - a local,
versioned mapping artifact binding an exact `(kubernetesSourceId, clusterUid, apiGroup, kind,
namespace, name)` Kubernetes Workload tuple to a full canonical AIP Service id.

Structurally mirrors `app.sources.migration_mappings` (shape validation via
`Draft202012Validator`, frozen dataclasses, then a sorted-dedup-then-conflict-detection pass), but
the raw YAML->dict step reuses `app.sources.kubernetes_envelope.load_bounded_yaml_documents`
rather than plain `yaml.safe_load`: §21.2 requires rejecting a literal duplicate YAML mapping key,
which plain `yaml.safe_load` silently collapses instead of rejecting.

Pure, no Neo4j access - resolving a mapping entry against real I2 Workload/Service facts is
`app.architecture_intelligence.deployment_projection.resolve_path_b`'s job, not this module's.
Cross-entry "same Workload, different Service" conflict detection also belongs there (spec §8.2):
it needs a real Workload resolution this module cannot perform on its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from app.common.encoding import sha256_hex
from app.sources.kubernetes_envelope import (
    KubernetesEnvelopeLimitExceeded,
    KubernetesEnvelopeMalformedError,
    load_bounded_yaml_documents,
)
from app.sources.model import DiagnosticCode, IngestionDiagnostic
from app.sources.service_identity import is_valid_service_id

_SUPPORTED_WORKLOAD_KINDS = ("Deployment", "StatefulSet", "DaemonSet")

_MAPPING_ENTRY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["mappingId", "serviceId", "kubernetesSourceId", "clusterUid", "workload"],
    "properties": {
        "mappingId": {"type": "string", "minLength": 1},
        "serviceId": {"type": "string", "minLength": 1},
        "kubernetesSourceId": {"type": "string", "minLength": 1},
        "clusterUid": {"type": "string", "minLength": 1},
        "workload": {
            "type": "object",
            "additionalProperties": False,
            "required": ["apiGroup", "kind", "namespace", "name"],
            "properties": {
                # §8.1: "the core API group is the empty string" (mirrors I2's own
                # InfrastructureEntity.api_group convention) - no minLength here, even though
                # Deployment/StatefulSet/DaemonSet are in practice always "apps".
                "apiGroup": {"type": "string"},
                "kind": {"enum": list(_SUPPORTED_WORKLOAD_KINDS)},
                # Deployment/StatefulSet/DaemonSet are always namespaced - unlike apiGroup, an
                # empty namespace here is never valid input for these three kinds.
                "namespace": {"type": "string", "minLength": 1},
                "name": {"type": "string", "minLength": 1},
            },
        },
    },
}

# §8.1: "The initial schema is equivalent to" the YAML example it gives; `apiVersion`/`kind` naming
# is this module's own choice (not spec-given, flagged for review), mirroring
# `migration_mappings.py`'s own `AipSharedIdentityMappings` precedent.
_SERVICE_WORKLOAD_MAPPINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["apiVersion", "kind", "metadata"],
    "properties": {
        "apiVersion": {"const": "aip.dev/v1"},
        "kind": {"const": "ServiceWorkloadIdentityMappings"},
        "metadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["id", "revision"],
            "properties": {
                "id": {"type": "string", "minLength": 1},
                "revision": {"type": "string", "minLength": 1},
            },
        },
        "mappings": {"type": "array", "items": _MAPPING_ENTRY_SCHEMA},
    },
}

_VALIDATOR = Draft202012Validator(_SERVICE_WORKLOAD_MAPPINGS_SCHEMA)


@dataclass(frozen=True)
class ServiceWorkloadMappingEntry:
    mapping_id: str
    service_id: str
    kubernetes_source_id: str
    cluster_uid: str
    api_group: str
    # The raw Kubernetes controller-kind string ("Deployment"/"StatefulSet"/"DaemonSet"), matching
    # I2's own `InfrastructureEntity.resource_kind` convention - not `app.architecture_intelligence.
    # contracts.WorkloadKind` (that public enum is uppercase and belongs to the frozen contract
    # layer, not this sources-layer artifact).
    workload_kind: str
    namespace: str
    name: str


@dataclass(frozen=True)
class ServiceWorkloadMappingDocument:
    artifact_id: str
    artifact_revision: str
    locator: str
    # §8.3: SHA-256 of this artifact file's own exact raw bytes, mirroring
    # `MigrationMappingsDocument.content_digest`'s identical convention.
    content_digest: str
    entries: tuple[ServiceWorkloadMappingEntry, ...] = field(default_factory=tuple)


def _shape_errors(document: dict) -> list[str]:
    # jsonschema error paths mix str (property names) and int (array indices) elements - see
    # `migration_mappings._shape_errors`'s identical comment for why each path element is
    # stringified before sorting.
    return [
        error.message
        for error in sorted(
            _VALIDATOR.iter_errors(document), key=lambda e: [str(p) for p in e.path]
        )
    ]


def _entry_sort_key(entry: ServiceWorkloadMappingEntry) -> tuple:
    return (
        entry.mapping_id,
        entry.service_id,
        entry.kubernetes_source_id,
        entry.cluster_uid,
        entry.api_group,
        entry.workload_kind,
        entry.namespace,
        entry.name,
    )


def _dedupe_and_check_duplicate_ids(
    entries: Sequence[ServiceWorkloadMappingEntry], *, locator: str
) -> tuple[tuple[ServiceWorkloadMappingEntry, ...], list[IngestionDiagnostic]]:
    """§8.2: "Identical duplicate mappings are normalized deterministically" - a full-tuple
    identical repeat collapses silently. A `mappingId` repeated with any differing field is a
    latent identity defect (see `DiagnosticCode.SERVICE_WORKLOAD_MAPPING_DUPLICATE_ID`'s own
    comment): `mappingId` is part of both §13.1's group-key formula and §8.3's evidence identity,
    so two different entries sharing one can never be safely distinguished downstream.
    """
    sorted_entries = sorted(entries, key=_entry_sort_key)
    seen_full_tuples: set[tuple] = set()
    by_mapping_id: dict[str, ServiceWorkloadMappingEntry] = {}
    deduped: list[ServiceWorkloadMappingEntry] = []
    diagnostics: list[IngestionDiagnostic] = []

    for entry in sorted_entries:
        full_tuple = _entry_sort_key(entry)
        if full_tuple in seen_full_tuples:
            continue
        seen_full_tuples.add(full_tuple)

        existing = by_mapping_id.get(entry.mapping_id)
        if existing is not None:
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_DUPLICATE_ID,
                    message=(
                        f"mappingId {entry.mapping_id!r} appears twice with differing content "
                        f"in {locator!r}"
                    ),
                    source_pointer=locator,
                )
            )
            continue
        by_mapping_id[entry.mapping_id] = entry
        deduped.append(entry)

    return tuple(deduped), diagnostics


def parse_service_workload_mappings(
    document: dict, *, locator: str, content_digest: str
) -> tuple[ServiceWorkloadMappingDocument | None, list[IngestionDiagnostic]]:
    """Parses and validates one mapping-artifact document - shape conformance, each entry's
    `serviceId` grammar, and within-document duplicate-mappingId detection. Does not check a
    mapping's Workload/Service target against real I2/declared facts (that's `resolve_path_b`'s
    job) or cross-document conflicts (Path B has no cross-document merge - each artifact's entries
    are evaluated independently by `resolve_path_b`, unlike `migration_mappings`'s own merged
    cross-source index). Any diagnostic here rejects the whole document, mirroring
    `parse_migration_mappings`'s identical "shape, then entry validity" all-or-nothing convention.
    """
    shape_errors = _shape_errors(document)
    if shape_errors:
        return None, [
            IngestionDiagnostic(
                code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID,
                message=message,
                source_pointer=locator,
            )
            for message in shape_errors
        ]

    diagnostics: list[IngestionDiagnostic] = []
    entries: list[ServiceWorkloadMappingEntry] = []
    for index, raw in enumerate(document.get("mappings") or ()):
        service_id = raw["serviceId"]
        source_pointer = f"/mappings/{index}"
        if not is_valid_service_id(service_id):
            diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_TARGET_INVALID,
                    message=f"mappings[{index}]: serviceId {service_id!r} is not a valid Service id",
                    source_pointer=f"{source_pointer}/serviceId",
                )
            )
            continue

        workload = raw["workload"]
        entries.append(
            ServiceWorkloadMappingEntry(
                mapping_id=raw["mappingId"],
                service_id=service_id,
                kubernetes_source_id=raw["kubernetesSourceId"],
                cluster_uid=raw["clusterUid"],
                api_group=workload["apiGroup"],
                workload_kind=workload["kind"],
                namespace=workload["namespace"],
                name=workload["name"],
            )
        )
    if diagnostics:
        return None, diagnostics

    deduped_entries, dedupe_diagnostics = _dedupe_and_check_duplicate_ids(entries, locator=locator)
    if dedupe_diagnostics:
        return None, dedupe_diagnostics

    parsed = ServiceWorkloadMappingDocument(
        artifact_id=document["metadata"]["id"],
        artifact_revision=document["metadata"]["revision"],
        locator=locator,
        content_digest=content_digest,
        entries=deduped_entries,
    )
    return parsed, []


def load_service_workload_mapping(
    path: Path | None,
) -> tuple[ServiceWorkloadMappingDocument | None, tuple[IngestionDiagnostic, ...]]:
    """Reads and parses the single configured mapping-artifact file
    (`app.settings.SourcesConfig.service_workload_mapping`), per spec §8.1: "Path B uses one local,
    versioned mapping artifact" - never a collection (PR #215 review: an earlier `list[Path]`/
    multi-document shape let two artifacts silently collide on the same `(artifact_id,
    artifact_revision, mapping_id)` group key, violating §13.1's exactly-once reduction). `path is
    None` (no artifact configured) returns `(None, ())`. A missing/unreadable file or one that isn't
    well-formed/single-document YAML at its root is diagnosed rather than raised or silently
    skipped, mirroring `migration_mappings.load_migration_mappings`'s identical "diagnose, don't
    fall back" discipline.
    """
    if path is None:
        return None, ()

    locator = str(path)
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return None, (
            IngestionDiagnostic(
                code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_FILE_UNAVAILABLE,
                message=f"{locator}: {exc}",
                source_pointer=locator,
            ),
        )

    content_digest = sha256_hex(raw_bytes)

    try:
        loaded_documents = load_bounded_yaml_documents(raw_bytes)
    except (
        KubernetesEnvelopeLimitExceeded,
        KubernetesEnvelopeMalformedError,
        yaml.YAMLError,
    ) as exc:
        return None, (
            IngestionDiagnostic(
                code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID,
                message=f"{locator}: {exc}",
                source_pointer=locator,
            ),
        )

    if len(loaded_documents) != 1:
        return None, (
            IngestionDiagnostic(
                code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID,
                message=(
                    f"{locator}: expected exactly one YAML document, got {len(loaded_documents)}"
                ),
                source_pointer=locator,
            ),
        )
    [parsed_yaml] = loaded_documents
    if not isinstance(parsed_yaml, dict):
        return None, (
            IngestionDiagnostic(
                code=DiagnosticCode.SERVICE_WORKLOAD_MAPPING_SHAPE_INVALID,
                message=f"{locator}: root document is not a mapping",
                source_pointer=locator,
            ),
        )

    document, parse_diagnostics = parse_service_workload_mappings(
        parsed_yaml, locator=locator, content_digest=content_digest
    )
    return document, tuple(parse_diagnostics)
