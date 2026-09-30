from app.sources.identity import (
    discovery_scope_id,
    kubernetes_source_instance_id,
    normalize_relative_posix_path,
    scope_definition_digest,
)
from app.sources.kubernetes_envelope import KubernetesSourceSnapshot, validate_kubernetes_snapshot
from app.sources.model import (
    DiagnosticCode,
    IngestionDiagnostic,
    IngestionResult,
    KubernetesCaptureScope,
    KubernetesSourceConfig,
    LoadedSource,
    SourceDescriptor,
    SourceKind,
)
from app.sources.registry import DiscoveryOutcome

# The empty-bytes SHA-256 - this codebase's existing convention for "no real content" (mirrors
# app.sources.identity.EMPTY_CLOSURE_DIGEST). Used as `content_sha256` for a `LoadedSource` whose
# envelope never successfully read any bytes; the field is audit-only for an already-rejected
# source and is never consulted past that rejection.
_EMPTY_CONTENT_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

# I2 Draft 0.2 §4.2: fields the configured registration binds, checked against the corresponding
# envelope field. A cluster_uid mismatch is K8S_CLUSTER_IDENTITY_UNRESOLVED - the only diagnostic
# named for identity specifically; every other mismatch here is K8S_SNAPSHOT_INVALID (§10: "shape,
# digest, or scope mismatch").
_CLUSTER_IDENTITY_MISMATCH = "cluster_uid"


class KubernetesSourceDiscoverer:
    """I2 Draft 0.2 §4.2's Kubernetes source discoverer - one instance per configured
    `KubernetesSourceConfig`, wrapping slice 2a's `validate_kubernetes_snapshot` and performing the
    registration-binding check §4.2 requires ("Envelope values must match [the registration]").
    """

    source_kind = SourceKind.KUBERNETES

    def __init__(self, config: KubernetesSourceConfig):
        self._config = config
        self.discoverer_identity = "kubernetes-discoverer@1"

    def discover(self) -> DiscoveryOutcome:
        config = self._config
        # I2 Draft 0.2 §3/§8: a snapshot is required for every discovery attempt, including a
        # failed one, and both formulas are pure functions of configured values - computed before
        # any filesystem access, mirroring FilesystemSourceDiscoverer's own already-reviewed fix for
        # exactly this "compute before the existence check" bug.
        scope_id = discovery_scope_id(
            configured_scope_id=config.resolved_scope_id,
            stable_target_identity=config.resolved_stable_target_identity,
        )
        scope_digest = scope_definition_digest(
            discovery_scope_id=scope_id,
            normalized_roots=[normalize_relative_posix_path(str(config.root))],
            filters=[],
            inclusion_rules=[],
        )

        if not config.root.is_dir():
            # §10: "Acquisition fails before a stable source can be loaded and identified" - the
            # whole configured root is unavailable, not just its envelope. Mirrors filesystem's
            # identical missing-root case exactly: enumeration_complete=False forces run FAILED.
            return DiscoveryOutcome(
                loaded_sources=(),
                enumeration_complete=False,
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.SOURCE_ROOT_UNAVAILABLE,
                        message=(
                            f"configured source root does not exist or is not a directory: "
                            f"{config.root}"
                        ),
                        source_pointer=str(config.root),
                    ),
                ),
                discovery_scope_id=scope_id,
                scope_definition_digest=scope_digest,
            )

        # §6: SourceInstanceId needs only configured values (configured_source_id, cluster_uid) -
        # unlike a filesystem source's own formula, which needs a discovered document's own
        # relative path. This means a Kubernetes source's identity is always computable, even when
        # its envelope turns out missing or invalid.
        instance_id = kubernetes_source_instance_id(
            configured_kubernetes_source_id=config.id, cluster_uid=config.cluster_uid
        )

        validation = validate_kubernetes_snapshot(
            root=config.root, envelope_relative_path=config.envelope_relative_path
        )
        if validation.result != IngestionResult.ACCEPTED or validation.envelope is None:
            # §10's exact source/run distinction: "A loaded envelope declares an incomplete
            # capture" / "a required listed file is missing, has the wrong digest, or cannot be
            # parsed" -> REJECTED_INVALID (source) / PARTIAL (run), never FAILED. The discoverer
            # itself did its job (it identified exactly one source); that source is what's invalid,
            # so enumeration_complete stays True.
            loaded_source = LoadedSource(
                descriptor=SourceDescriptor(
                    source_instance_id=instance_id,
                    source_kind=SourceKind.KUBERNETES,
                    locator=str(config.root / config.envelope_relative_path),
                    discovery_scope_id=scope_id,
                    scope_definition_digest=scope_digest,
                    content_sha256=_EMPTY_CONTENT_SHA256,
                    semantic_input_digest="",
                    mapping_context_digest="",
                    adapter_identity="",
                    mapping_rule_id="",
                    mapping_rule_version="",
                ),
                document={},
                diagnostics=list(validation.diagnostics),
                source_root=str(config.root),
            )
            return DiscoveryOutcome(
                loaded_sources=(loaded_source,),
                enumeration_complete=True,
                diagnostics=(),
                discovery_scope_id=scope_id,
                scope_definition_digest=scope_digest,
            )

        envelope = validation.envelope
        binding_mismatch = self._registration_binding_mismatch(envelope)
        if binding_mismatch is not None:
            field_name, message = binding_mismatch
            code = (
                DiagnosticCode.K8S_CLUSTER_IDENTITY_UNRESOLVED
                if field_name == _CLUSTER_IDENTITY_MISMATCH
                else DiagnosticCode.K8S_SNAPSHOT_INVALID
            )
            loaded_source = LoadedSource(
                descriptor=SourceDescriptor(
                    source_instance_id=instance_id,
                    source_kind=SourceKind.KUBERNETES,
                    locator=str(config.root / config.envelope_relative_path),
                    discovery_scope_id=scope_id,
                    scope_definition_digest=scope_digest,
                    content_sha256=validation.envelope_content_sha256 or _EMPTY_CONTENT_SHA256,
                    semantic_input_digest="",
                    mapping_context_digest="",
                    adapter_identity="",
                    mapping_rule_id="",
                    mapping_rule_version="",
                ),
                document={},
                diagnostics=[
                    IngestionDiagnostic(
                        code=code,
                        message=message,
                        source_pointer=config.envelope_relative_path,
                    )
                ],
                source_root=str(config.root),
            )
            return DiscoveryOutcome(
                loaded_sources=(loaded_source,),
                enumeration_complete=True,
                diagnostics=(),
                discovery_scope_id=scope_id,
                scope_definition_digest=scope_digest,
            )

        # I2 Draft 0.2 §8: "Changing namespace filters changes the scope digest." The upfront
        # scope_digest (config-only) is a safe non-committing fallback for the failed/mismatched
        # cases above, which never reach a commit anyway - but an ACCEPTED envelope's own declared
        # namespaces must participate in the persisted digest, or two accepted envelopes at the same
        # root with different scope.namespaces would collide onto one digest, letting a later
        # scope-narrowing be misclassified as same-scope and authorize unsafe expiry (§8).
        accepted_scope_digest = scope_definition_digest(
            discovery_scope_id=scope_id,
            normalized_roots=[normalize_relative_posix_path(str(config.root))],
            filters=sorted(envelope.scope.namespaces),
            inclusion_rules=[],
        )

        # Adapter-specific fields (semantic_input_digest, mapping_context_digest, adapter_identity,
        # mapping_rule_id, mapping_rule_version) are enriched by the orchestrator once an adapter is
        # matched, mirroring FilesystemSourceDiscoverer's own discovery-time placeholders.
        # I1 spec §7.2: "Every successful load SHALL record... declared/provider revision, where
        # available." The envelope's own metadata.revision is exactly that - it was previously left
        # unset, discarding it after this function returns despite being read here.
        descriptor = SourceDescriptor(
            source_instance_id=instance_id,
            source_kind=SourceKind.KUBERNETES,
            locator=str(config.root / config.envelope_relative_path),
            discovery_scope_id=scope_id,
            scope_definition_digest=accepted_scope_digest,
            declared_provider_revision=envelope.metadata.revision,
            # v0.6.0 I2.2d (decision record D5): only this fully-accepted path carries the capture.
            capture_scope=KubernetesCaptureScope(
                namespaces=tuple(sorted(envelope.scope.namespaces)),
                cluster_uid=envelope.source.cluster_uid,
                revision=envelope.metadata.revision,
                evidence_mode=str(envelope.source.mode),
                captured_at=envelope.metadata.captured_at,
            ),
            content_sha256=validation.envelope_content_sha256 or _EMPTY_CONTENT_SHA256,
            semantic_input_digest="",
            mapping_context_digest="",
            adapter_identity="",
            mapping_rule_id="",
            mapping_rule_version="",
        )
        loaded_source = LoadedSource(
            descriptor=descriptor,
            document=envelope.model_dump(by_alias=True),
            source_root=str(config.root),
            kubernetes_resources=validation.resources,
        )
        return DiscoveryOutcome(
            loaded_sources=(loaded_source,),
            enumeration_complete=True,
            diagnostics=(),
            discovery_scope_id=scope_id,
            scope_definition_digest=accepted_scope_digest,
            # I2 Draft 0.2 §4.2 (slice 2b-ii): the envelope's own declared predecessor claim -
            # `None` legitimately means "expect no prior committed inventory" (first import), not
            # "no predecessor check requested". Only set on this fully-accepted path: an envelope
            # that failed validation or registration binding is untrusted, so its declared claim
            # isn't honored either (the same "safe non-committing fallback" reasoning already
            # applied to scope_definition_digest above) - inert either way, since a rejected source
            # already blocks commit before any predecessor check would run.
            expected_prior_inventory_revision=envelope.completeness.expected_prior_inventory_revision,
        )

    def _registration_binding_mismatch(
        self, envelope: KubernetesSourceSnapshot
    ) -> tuple[str, str] | None:
        config = self._config
        checks = (
            (_CLUSTER_IDENTITY_MISMATCH, envelope.source.cluster_uid, config.cluster_uid),
            (
                "configured_source_id",
                envelope.source.configured_source_id,
                config.id,
            ),
            (
                "configured_scope_id",
                envelope.source.configured_scope_id,
                config.resolved_scope_id,
            ),
            ("mode", envelope.source.mode, config.evidence_mode),
            ("producer", envelope.metadata.producer, config.authorized_producer),
            ("authority_ref", envelope.completeness.authority_ref, config.authority_record),
        )
        for field_name, envelope_value, configured_value in checks:
            if envelope_value != configured_value:
                # Never echoes either value: both are registration identifiers, not attacker-
                # controlled resource content, but slice 2a's own review history (see
                # feedback_sanitize_diagnostics_and_reject_frozen_input) settled on keeping every
                # diagnostic message a pure structural pointer - the field name is enough to locate
                # the mismatch; the mismatching values themselves add nothing a fix needs.
                return (
                    field_name,
                    f"envelope {field_name} does not match the configured registration",
                )
        return None
