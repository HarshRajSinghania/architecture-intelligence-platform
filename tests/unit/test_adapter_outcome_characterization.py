"""Characterization of the outcomes every document adapter (OpenAPI, AsyncAPI, manifest) produces
on the shared rejection and limitation paths: the result, each diagnostic's code/message/pointer
and their order, the absence of a digest, and the evidence stamped on an accepted model. The
adapters share a document prologue (validate -> remote refs -> dialect version) and epilogue
(declared evidence + limitation diagnostic); refactoring that scaffolding must leave every
assertion here unchanged."""

import copy

import pytest

from app.canonical.model import ArchitectureModel, Service
from app.ingestion.asyncapi_adapter import AsyncApiSourceAdapter
from app.ingestion.manifest_adapter import ManifestSourceAdapter
from app.ingestion.openapi_adapter import OpenApiSourceAdapter
from app.sources.migration_mappings import EMPTY_SHARED_IDENTITY_INDEX
from app.sources.model import (
    DiagnosticCode,
    IngestionResult,
    LoadedSource,
    SourceDescriptor,
    SourceKind,
)
from app.sources.service_identity import resolve_service_identity

SOURCE_INSTANCE_ID = "urn:aip:source:filesystem:" + "a" * 64


class _Resolver:
    def resolve(self, *, source_instance_id, construct_pointer, extension_value):
        return resolve_service_identity(
            source_instance_id=source_instance_id,
            construct_pointer=construct_pointer,
            extension_value=extension_value,
            configured_mappings=[],
            manifest_bindings=[],
        )


def _loaded(document: dict, locator: str) -> LoadedSource:
    descriptor = SourceDescriptor(
        source_instance_id=SOURCE_INSTANCE_ID,
        source_kind=SourceKind.FILESYSTEM,
        locator=locator,
        discovery_scope_id="urn:aip:discovery-scope:" + "b" * 64,
        scope_definition_digest="c" * 64,
        content_sha256="d" * 64,
        semantic_input_digest="",
        mapping_context_digest="",
        adapter_identity="",
        mapping_rule_id="",
        mapping_rule_version="",
    )
    return LoadedSource(descriptor=descriptor, document=document)


def _map(adapter, document: dict, *, locator: str = "test.yaml", upstream=None):
    return adapter.map(
        _loaded(document, locator),
        service_identity=_Resolver(),
        shared_identity=EMPTY_SHARED_IDENTITY_INDEX,
        upstream_model=upstream if upstream is not None else ArchitectureModel(),
        mapping_context_digest="e" * 64,
    )


def _diagnostics(outcome):
    return [(d.code, d.message, d.source_pointer) for d in outcome.diagnostics]


_OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "ProductService", "version": "1.0.0"},
    "x-aip-service-id": "service:product-service",
    "paths": {
        "/products/{id}": {
            "get": {
                "operationId": "getProduct",
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Product"}}
                        }
                    }
                },
            }
        }
    },
    "components": {"schemas": {"Product": {"type": "object", "properties": {"id": {}}}}},
}

_ASYNCAPI = {
    "asyncapi": "2.6.0",
    "info": {"title": "Svc"},
    "x-aip-service-id": "service:svc",
    "servers": {
        "asb": {
            "url": "amqps://asb.example.com",
            "protocol": "amqp",
            "x-aip-broker-id": "asb",
            "bindings": {"amqp": {"virtualHost": "commerce"}},
        }
    },
    "channels": {
        "orders-q": {
            "x-aip-destination-kind": "queue",
            "publish": {
                "operationId": "sendOrder",
                "message": {"$ref": "#/components/messages/OrderPlaced"},
            },
        }
    },
    "components": {
        "messages": {
            "OrderPlaced": {
                "name": "OrderPlaced",
                "x-version": "v1",
                "payload": {"$ref": "#/components/schemas/OrderPlacedPayload"},
            }
        },
        "schemas": {
            "OrderPlacedPayload": {"type": "object", "properties": {"id": {"type": "string"}}}
        },
    },
}

_REMOTE = "https://example.com/x.json"


def _openapi(mutate=lambda d: None) -> dict:
    document = copy.deepcopy(_OPENAPI)
    mutate(document)
    return document


def _asyncapi(mutate=lambda d: None) -> dict:
    document = copy.deepcopy(_ASYNCAPI)
    mutate(document)
    return document


# --- rejection paths: (adapter, document, expected result, expected diagnostics) -----------------

_REJECTIONS = {
    "openapi-invalid": (
        OpenApiSourceAdapter(),
        {"openapi": "3.1.0"},
        IngestionResult.REJECTED_INVALID,
        [
            (DiagnosticCode.DOCUMENT_PARSE_INVALID, "'info' is a required property", "test.yaml"),
            (DiagnosticCode.DOCUMENT_PARSE_INVALID, "'paths' is a required property", "test.yaml"),
        ],
    ),
    "openapi-remote-ref": (
        OpenApiSourceAdapter(),
        _openapi(
            lambda d: d["components"]["schemas"]["Product"]["properties"].update(
                id={"$ref": _REMOTE}
            )
        ),
        IngestionResult.REJECTED_UNSUPPORTED,
        [
            (
                DiagnosticCode.REMOTE_REFERENCE_UNSUPPORTED,
                f"remote/non-local reference is not supported: {_REMOTE}",
                "test.yaml",
            )
        ],
    ),
    "openapi-version": (
        OpenApiSourceAdapter(),
        _openapi(lambda d: d.update(openapi="3.2.0")),
        IngestionResult.REJECTED_UNSUPPORTED,
        [
            (
                DiagnosticCode.UNSUPPORTED_DIALECT_VERSION,
                "unsupported openapi version: '3.2.0' (accepted: ['3.0.3', '3.1.0', '3.1.2'])",
                "test.yaml",
            )
        ],
    ),
    "asyncapi-invalid": (
        AsyncApiSourceAdapter(),
        {"asyncapi": "2.6.0"},
        IngestionResult.REJECTED_INVALID,
        [(DiagnosticCode.DOCUMENT_PARSE_INVALID, "'info' is a required property", "test.yaml")],
    ),
    "asyncapi-remote-ref": (
        AsyncApiSourceAdapter(),
        _asyncapi(
            lambda d: d["components"]["schemas"].update(OrderPlacedPayload={"$ref": _REMOTE})
        ),
        IngestionResult.REJECTED_UNSUPPORTED,
        [
            (
                DiagnosticCode.REMOTE_REFERENCE_UNSUPPORTED,
                f"remote/non-local reference is not supported: {_REMOTE}",
                "test.yaml",
            )
        ],
    ),
    "asyncapi-version": (
        AsyncApiSourceAdapter(),
        _asyncapi(lambda d: d.update(asyncapi="9.9.9")),
        IngestionResult.REJECTED_UNSUPPORTED,
        [
            (
                DiagnosticCode.UNSUPPORTED_DIALECT_VERSION,
                "unsupported asyncapi version: '9.9.9' (accepted: ['2.6.0'])",
                "test.yaml",
            )
        ],
    ),
    "manifest-invalid": (
        ManifestSourceAdapter(),
        {"service": {"name": "x"}},
        IngestionResult.REJECTED_INVALID,
        [
            (
                DiagnosticCode.DOCUMENT_PARSE_INVALID,
                "{'name': 'x'} is not of type 'string'",
                "test.yaml",
            )
        ],
    ),
}


@pytest.mark.parametrize("case", sorted(_REJECTIONS))
def test_rejection_outcomes_are_unchanged(case):
    adapter, document, result, diagnostics = _REJECTIONS[case]
    outcome = _map(adapter, document)
    assert outcome.result is result
    assert _diagnostics(outcome) == diagnostics
    assert outcome.semantic_input_digest is None
    assert outcome.model == ArchitectureModel()


# --- accepted-with-limitations + declared evidence -----------------------------------------------

_EVIDENCE_ID = "evidence:{kind}:" + SOURCE_INSTANCE_ID


def test_openapi_composition_limitation_and_declared_evidence_are_unchanged():
    document = _openapi(
        lambda d: d["components"]["schemas"].update(Product={"allOf": [{"type": "object"}]})
    )
    outcome = _map(OpenApiSourceAdapter(), document)
    assert outcome.result is IngestionResult.ACCEPTED_WITH_LIMITATIONS
    assert _diagnostics(outcome) == [
        (
            DiagnosticCode.SCHEMA_COMPOSITION_UNINTERPRETED,
            (
                "one or more schemas contain an allOf/oneOf/anyOf composition, preserved "
                "structurally in the canonical hash but not interpreted as an effective object "
                "shape"
            ),
            "test.yaml",
        )
    ]
    [evidence] = outcome.model.provenance
    assert evidence.model_dump() == {
        "id": _EVIDENCE_ID.format(kind="openapi"),
        "source_type": "OPENAPI",
        "source_file": "test.yaml",
        "source_revision": None,
        "evidence_type": "DECLARED",
    }
    assert outcome.model.relations
    assert all(r.evidence_ids == [evidence.id] for r in outcome.model.relations)
    assert outcome.semantic_input_digest is not None


def test_asyncapi_composition_limitation_and_declared_evidence_are_unchanged():
    document = _asyncapi(
        lambda d: d["components"]["schemas"].update(
            OrderPlacedPayload={"allOf": [{"type": "object"}]}
        )
    )
    outcome = _map(AsyncApiSourceAdapter(), document)
    assert outcome.result is IngestionResult.ACCEPTED_WITH_LIMITATIONS
    assert _diagnostics(outcome) == [
        (
            DiagnosticCode.SCHEMA_COMPOSITION_UNINTERPRETED,
            (
                "one or more payload schemas contain an allOf/oneOf/anyOf composition, preserved "
                "structurally in the canonical hash but not interpreted as an effective object "
                "shape"
            ),
            "test.yaml",
        )
    ]
    [evidence] = outcome.model.provenance
    assert evidence.model_dump() == {
        "id": _EVIDENCE_ID.format(kind="asyncapi"),
        "source_type": "ASYNCAPI",
        "source_file": "test.yaml",
        "source_revision": None,
        "evidence_type": "DECLARED",
    }
    assert outcome.model.relations
    assert all(r.evidence_ids == [evidence.id] for r in outcome.model.relations)


def test_manifest_declared_evidence_is_unchanged():
    upstream = ArchitectureModel(services=[Service(id="service:order-service", name="order")])
    outcome = _map(
        ManifestSourceAdapter(),
        {"service": "order-service", "x-aip-service-id": "service:order-service"},
        locator="architecture.yaml",
        upstream=upstream,
    )
    assert outcome.result is IngestionResult.ACCEPTED, _diagnostics(outcome)
    [evidence] = outcome.model.provenance
    assert evidence.model_dump() == {
        "id": _EVIDENCE_ID.format(kind="manifest"),
        "source_type": "MANIFEST",
        "source_file": "architecture.yaml",
        "source_revision": None,
        "evidence_type": "DECLARED",
    }
