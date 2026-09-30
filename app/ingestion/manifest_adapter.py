from app.canonical.model import ArchitectureModel, Relation
from app.common.jcs import canonical_json_bytes
from app.ingestion.adapter_outcomes import (
    declared_evidence,
    reject_if_invalid,
    rejected_outcome_for_identity,
    resolved_service_id,
    stamp_evidence,
)
from app.sources.identity import semantic_input_digest
from app.sources.model import DiagnosticCode, IngestionDiagnostic, IngestionResult, LoadedSource
from app.sources.registry import AdapterOutcome, ServiceIdentityResolver, SharedIdentityResolver
from app.sources.service_identity import ServiceIdentityOutcome, is_valid_service_id
from app.validation.source_validation import validate_manifest_document


class ManifestSourceAdapter:
    """I1 spec §4/§7: migrates `parse_manifest` (the existing `architecture.yaml` CALLS-relation
    format - distinct from PR #1's `ArchitectureIdentityBindings` binding-manifest format, which
    isn't a `SourceAdapter` at all since it emits no canonical entities) onto the registry seam.

    `dependency_phase=1` is the generic mechanism giving this adapter access to `upstream_model`
    (the merged result of every phase-0 adapter across every discovered source), replacing
    `pipeline.py`'s special-cased external `operation_index` construction - the mechanism now
    generalizes to any future cross-referencing adapter, not just this one.
    """

    adapter_identity = "manifest-adapter@1"
    mapping_rule_version = "v1"
    dependency_phase = 1

    def supports(self, loaded: LoadedSource) -> bool:
        return (
            "service" in loaded.document
            and loaded.document.get("kind") != "ArchitectureIdentityBindings"
        )

    def map(
        self,
        loaded: LoadedSource,
        *,
        service_identity: ServiceIdentityResolver,
        shared_identity: SharedIdentityResolver,
        upstream_model: ArchitectureModel,
        mapping_context_digest: str,
    ) -> AdapterOutcome:
        # This adapter emits only Service/Operation/CALLS-Relation entities (no Schema/Message/
        # Queue of its own to look up a shared/migration-mapped id for) - shared_identity is
        # accepted for interface uniformity across every registered SourceAdapter and unused here.
        document = loaded.document
        source_instance_id = loaded.descriptor.source_instance_id

        if (rejection := reject_if_invalid(loaded, validate_manifest_document)) is not None:
            return rejection

        root_resolution = service_identity.resolve(
            source_instance_id=source_instance_id,
            construct_pointer="",
            extension_value=document.get("x-aip-service-id"),
        )
        if root_resolution.outcome is not ServiceIdentityOutcome.RESOLVED:
            return rejected_outcome_for_identity(root_resolution)
        caller_service_id = resolved_service_id(root_resolution)

        # v0.5.0 I5 finding F1: the manifest declares CALLS from its caller, but never the caller
        # Service itself - that comes from a phase-0 source (the caller's own OpenAPI/AsyncAPI).
        # Without one, every CALLS relation would have an unknown source, so the manifest is
        # rejected here exactly like an unresolved call target, and it mints nothing.
        known_service_ids = {service.id for service in upstream_model.services}
        if document.get("calls") and caller_service_id not in known_service_ids:
            return AdapterOutcome(
                result=IngestionResult.REJECTED_UNSUPPORTED,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.MANIFEST_CALL_SOURCE_UNRESOLVED,
                        message=(
                            f"caller service {caller_service_id!r} is not declared by any "
                            "discovered source"
                        ),
                        source_pointer=(
                            "/x-aip-service-id" if "x-aip-service-id" in document else ""
                        ),
                    ),
                ),
                semantic_input_digest=None,
            )

        # (service, operationId) -> full canonical Operation id, built from the merged phase-0
        # model instead of pipeline.py's separately-scanned index.
        operation_index: dict[tuple[str, str], str] = {
            (operation.service_id, operation.operation_id): operation.id
            for operation in upstream_model.operations
            if operation.operation_id
        }

        relations: list[Relation] = []
        for index, entry in enumerate(document.get("calls") or []):
            target_service_id = entry["service"]
            operation_id_name = entry["operationId"]
            call_pointer = f"/calls/{index}"

            if not is_valid_service_id(target_service_id):
                return AdapterOutcome(
                    result=IngestionResult.REJECTED_INVALID,
                    model=ArchitectureModel(),
                    diagnostics=(
                        IngestionDiagnostic(
                            code=DiagnosticCode.SERVICE_IDENTITY_INVALID,
                            message=f"malformed calls[].service: {target_service_id!r}",
                            source_pointer=call_pointer,
                        ),
                    ),
                    semantic_input_digest=None,
                )

            target_operation_id = operation_index.get((target_service_id, operation_id_name))
            if target_operation_id is None:
                return AdapterOutcome(
                    result=IngestionResult.REJECTED_UNSUPPORTED,
                    model=ArchitectureModel(),
                    diagnostics=(
                        IngestionDiagnostic(
                            code=DiagnosticCode.MANIFEST_CALL_TARGET_UNRESOLVED,
                            message=(
                                f"service {target_service_id!r} has no known operationId "
                                f"{operation_id_name!r} among the discovered sources"
                            ),
                            source_pointer=call_pointer,
                        ),
                    ),
                    semantic_input_digest=None,
                )

            relations.append(
                Relation(type="CALLS", source_id=caller_service_id, target_id=target_operation_id)
            )

        evidence = declared_evidence(loaded, "MANIFEST")
        relations = stamp_evidence(relations, evidence)

        model = ArchitectureModel(relations=relations, provenance=[evidence])
        digest = semantic_input_digest(
            normalized_document_projection_bytes=canonical_json_bytes(document),
            mapping_context_digest=mapping_context_digest,
        )

        return AdapterOutcome(
            result=IngestionResult.ACCEPTED,
            model=model,
            diagnostics=(),
            semantic_input_digest=digest,
        )
