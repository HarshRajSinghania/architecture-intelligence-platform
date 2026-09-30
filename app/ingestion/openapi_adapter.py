from app.canonical import ids
from app.canonical.model import ArchitectureModel, Operation, Relation, Schema, Service
from app.ingestion.adapter_outcomes import (
    composition_limitation_diagnostic,
    declared_evidence,
    reject_if_invalid,
    reject_if_unsupported_dialect,
    rejected_outcome_for_identity,
    resolved_service_id,
    stamp_evidence,
)
from app.ingestion.conflicts import upsert_schema_or_conflict
from app.ingestion.reference_closure import (
    build_resolution_cache,
    enforce_reference_closure,
    rejected_outcome_for_reference_error,
    semantic_input_digest_bytes,
)
from app.ingestion.schema_normalization import resolve_and_normalize_schema, schema_display_name
from app.sources.identity import semantic_input_digest
from app.sources.model import IngestionDiagnostic, IngestionResult, LoadedSource
from app.sources.owner_ids import schema_owned_id
from app.sources.pointers import encode_pointer_tokens
from app.sources.reference_resolution import ReferenceResolutionError
from app.sources.registry import AdapterOutcome, ServiceIdentityResolver, SharedIdentityResolver
from app.sources.service_identity import ServiceIdentityOutcome
from app.validation.source_validation import (
    validate_openapi_document,
)

HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

# I1 spec §8: "accept exactly OpenAPI 3.0.3, 3.1.0, and 3.1.2" (3.1.2 added by the Draft 0.3
# amendment - see docs/specifications/0.5.0/i1-source-ingestion-foundation.md §12).
ACCEPTED_OPENAPI_VERSIONS = frozenset({"3.0.3", "3.1.0", "3.1.2"})


class OpenApiSourceAdapter:
    """I1 spec §8: migrates `parse_openapi` onto the registry seam. Owner-scoped RFC 8785 Schema
    ids; Service identity resolved via `resolve_service_identity` (root + per-operation
    `x-aip-service-id`); bounded multi-file `$ref` resolution, recursive inline/array/nested schema
    normalization, and `allOf`/`oneOf`/`anyOf` composition (structurally preserved, not
    interpreted) per §8.1 (PR3b).
    """

    adapter_identity = "openapi-adapter@1"
    mapping_rule_version = "v1"
    dependency_phase = 0

    def supports(self, loaded: LoadedSource) -> bool:
        return "openapi" in loaded.document

    def map(
        self,
        loaded: LoadedSource,
        *,
        service_identity: ServiceIdentityResolver,
        shared_identity: SharedIdentityResolver,
        upstream_model: ArchitectureModel,
        mapping_context_digest: str,
    ) -> AdapterOutcome:
        document = loaded.document
        locator = loaded.descriptor.locator
        source_instance_id = loaded.descriptor.source_instance_id

        if (rejection := reject_if_invalid(loaded, validate_openapi_document)) is not None:
            return rejection
        if (
            rejection := reject_if_unsupported_dialect(
                loaded, dialect_key="openapi", accepted_versions=ACCEPTED_OPENAPI_VERSIONS
            )
        ) is not None:
            return rejection

        root_resolution = service_identity.resolve(
            source_instance_id=source_instance_id,
            construct_pointer="",
            extension_value=document.get("x-aip-service-id"),
        )
        if root_resolution.outcome is not ServiceIdentityOutcome.RESOLVED:
            return rejected_outcome_for_identity(root_resolution)

        info = document.get("info") or {}

        cache, root_relative_path = build_resolution_cache(loaded)
        closure_error = enforce_reference_closure(
            document, root_relative_path=root_relative_path, cache=cache, source_pointer=locator
        )
        if closure_error is not None:
            return closure_error

        operations: list[Operation] = []
        relations: list[Relation] = []
        schemas_by_id: dict[str, Schema] = {}
        resolved_service_ids: set[str] = {resolved_service_id(root_resolution)}
        any_uninterpreted_composition = False

        def resolve_schema(
            schema_obj: dict | None,
            *,
            canonical_service_id: str,
            media_type: str | None,
            own_pointer_tokens: tuple[str, ...],
        ) -> tuple[str | None, AdapterOutcome | None]:
            nonlocal any_uninterpreted_composition
            if not schema_obj:
                return None, None
            try:
                normalized = resolve_and_normalize_schema(
                    schema_obj,
                    own_document_relative_path=root_relative_path,
                    own_pointer_tokens=own_pointer_tokens,
                    cache=cache,
                )
            except ReferenceResolutionError as exc:
                return None, rejected_outcome_for_reference_error(
                    exc, source_pointer=encode_pointer_tokens(own_pointer_tokens)
                )

            if normalized.has_uninterpreted_composition:
                any_uninterpreted_composition = True

            # §8.1/§5.1.1: an explicit shared-identity/migration mapping, keyed by
            # (SourceInstanceId, normalized definition document path, resolved definition pointer),
            # is authoritative when present - checked before falling back to the owner-scoped
            # default formula. The document path is required alongside the pointer because a single
            # SourceInstanceId's own bounded multi-file $ref closure (PR3b) can resolve the same
            # relative pointer inside two different files.
            explicit_schema_id = shared_identity.schema_id_for(
                source_instance_id=source_instance_id,
                document_path=normalized.normalized_definition_document_path,
                pointer=encode_pointer_tokens(normalized.definition_pointer_tokens),
            )
            schema_id_value = explicit_schema_id or schema_owned_id(
                canonical_service_id=canonical_service_id,
                source_instance_id=source_instance_id,
                normalized_definition_document_path=normalized.normalized_definition_document_path,
                definition_pointer_tokens=normalized.definition_pointer_tokens,
            )
            conflict = upsert_schema_or_conflict(
                schemas_by_id,
                schema_id_value,
                Schema(
                    id=schema_id_value,
                    name=schema_display_name(normalized.definition_pointer_tokens),
                    format=media_type,
                    canonical_hash=normalized.canonical_hash,
                ),
            )
            if conflict is not None:
                return None, AdapterOutcome(
                    result=IngestionResult.REJECTED_CONFLICT,
                    model=ArchitectureModel(),
                    diagnostics=(conflict,),
                    semantic_input_digest=None,
                )
            return schema_id_value, None

        for path, path_item in (document.get("paths") or {}).items():
            if not isinstance(path_item, dict):
                continue
            for method, op in path_item.items():
                if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                    continue

                op_extension = op.get("x-aip-service-id")
                if op_extension is not None:
                    resolution = service_identity.resolve(
                        source_instance_id=source_instance_id,
                        construct_pointer=encode_pointer_tokens(("paths", path, method)),
                        extension_value=op_extension,
                    )
                    if resolution.outcome is not ServiceIdentityOutcome.RESOLVED:
                        return rejected_outcome_for_identity(resolution)
                    canonical_service_id = resolved_service_id(resolution)
                    resolved_service_ids.add(canonical_service_id)
                else:
                    canonical_service_id = resolved_service_id(root_resolution)

                operation_id_value = ids.operation_id(canonical_service_id, method, path)

                request_schema_ids: list[str] = []
                request_content = ((op.get("requestBody") or {}).get("content")) or {}
                for media_type, media_obj in request_content.items():
                    schema_id_value, error_outcome = resolve_schema(
                        media_obj.get("schema"),
                        canonical_service_id=canonical_service_id,
                        media_type=media_type,
                        own_pointer_tokens=(
                            "paths",
                            path,
                            method,
                            "requestBody",
                            "content",
                            media_type,
                            "schema",
                        ),
                    )
                    if error_outcome is not None:
                        return error_outcome
                    if schema_id_value and schema_id_value not in request_schema_ids:
                        request_schema_ids.append(schema_id_value)

                response_schema_ids: list[str] = []
                for status, response_obj in (op.get("responses") or {}).items():
                    if not isinstance(response_obj, dict):
                        continue
                    for media_type, media_obj in (response_obj.get("content") or {}).items():
                        schema_id_value, error_outcome = resolve_schema(
                            media_obj.get("schema"),
                            canonical_service_id=canonical_service_id,
                            media_type=media_type,
                            own_pointer_tokens=(
                                "paths",
                                path,
                                method,
                                "responses",
                                status,
                                "content",
                                media_type,
                                "schema",
                            ),
                        )
                        if error_outcome is not None:
                            return error_outcome
                        if schema_id_value and schema_id_value not in response_schema_ids:
                            response_schema_ids.append(schema_id_value)

                operations.append(
                    Operation(
                        id=operation_id_value,
                        service_id=canonical_service_id,
                        operation_id=op.get("operationId"),
                        method=method.upper(),
                        path=path,
                        request_schema_ids=request_schema_ids,
                        response_schema_ids=response_schema_ids,
                    )
                )
                relations.append(
                    Relation(
                        type="PROVIDES",
                        source_id=canonical_service_id,
                        target_id=operation_id_value,
                    )
                )
                relations.extend(
                    Relation(
                        type="REQUEST_SCHEMA",
                        source_id=operation_id_value,
                        target_id=schema_id_value,
                    )
                    for schema_id_value in request_schema_ids
                )
                relations.extend(
                    Relation(
                        type="RESPONSE_SCHEMA",
                        source_id=operation_id_value,
                        target_id=schema_id_value,
                    )
                    for schema_id_value in response_schema_ids
                )

        evidence = declared_evidence(loaded, "OPENAPI")
        relations = stamp_evidence(relations, evidence)

        services = [
            Service(id=service_id, name=info.get("title", service_id), version=info.get("version"))
            for service_id in sorted(resolved_service_ids)
        ]

        model = ArchitectureModel(
            services=services,
            operations=operations,
            schemas=list(schemas_by_id.values()),
            relations=relations,
            provenance=[evidence],
        )

        digest = semantic_input_digest(
            normalized_document_projection_bytes=semantic_input_digest_bytes(cache),
            mapping_context_digest=mapping_context_digest,
        )

        diagnostics: tuple[IngestionDiagnostic, ...] = ()
        result = IngestionResult.ACCEPTED
        if any_uninterpreted_composition:
            result = IngestionResult.ACCEPTED_WITH_LIMITATIONS
            diagnostics = (composition_limitation_diagnostic(locator, subject="schemas"),)

        return AdapterOutcome(
            result=result, model=model, diagnostics=diagnostics, semantic_input_digest=digest
        )
