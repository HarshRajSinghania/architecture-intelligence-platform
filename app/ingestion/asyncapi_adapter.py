from app.canonical.model import (
    ArchitectureModel,
    Direction,
    Message,
    Queue,
    Relation,
    Schema,
    Service,
    Subscription,
    Topic,
)
from app.canonical.pubsub import PubSubDeclaration, SubscriptionDeadLetterConfiguration
from app.common.encoding import unicode_nfc
from app.common.jcs import JSONValue
from app.ingestion.adapter_outcomes import (
    composition_limitation_diagnostic,
    declared_evidence,
    reject_if_invalid,
    reject_if_unsupported_dialect,
    rejected_outcome_for_identity,
    resolved_service_id,
    stamp_evidence,
)
from app.ingestion.conflicts import upsert_message_or_conflict, upsert_schema_or_conflict
from app.ingestion.reference_closure import (
    build_resolution_cache,
    enforce_reference_closure,
    rejected_outcome_for_reference_error,
    semantic_input_digest_bytes,
)
from app.ingestion.schema_normalization import resolve_and_normalize_schema, schema_display_name
from app.sources.identity import semantic_input_digest
from app.sources.message_contract import message_contract_digest, message_document_digest
from app.sources.model import (
    DiagnosticCode,
    IngestionDiagnostic,
    IngestionResult,
    LoadedSource,
    SubscriptionMapping,
)
from app.sources.owner_ids import (
    MISSING,
    InvalidXVersionError,
    inline_payload_schema_id,
    message_owned_id,
    normalize_x_version,
    queue_owned_id,
    schema_owned_id,
    subscription_owned_id,
    topic_owned_id,
)
from app.sources.pointers import encode_pointer_tokens
from app.sources.reference_resolution import (
    ReferenceResolutionError,
    ResolutionCache,
    resolve_and_read,
)
from app.sources.registry import AdapterOutcome, ServiceIdentityResolver, SharedIdentityResolver
from app.sources.service_identity import ServiceIdentityOutcome
from app.validation.source_validation import (
    validate_asyncapi_document,
)

# AsyncAPI 2.x: "publish" = the described application sends on the channel, "subscribe" = it
# receives from the channel (named from the app's own perspective, not the client's).
OPERATION_DIRECTIONS = {"publish": Direction.SEND, "subscribe": Direction.RECEIVE}
RELATION_TYPES = {Direction.SEND: "SENDS", Direction.RECEIVE: "RECEIVES_FROM"}

# I1 spec §9: "accept exactly AsyncAPI 2.6.0; all other versions, including every AsyncAPI 3.x
# document, are REJECTED_UNSUPPORTED in I1".
ACCEPTED_ASYNCAPI_VERSIONS = frozenset({"2.6.0"})


class _MessageDef:
    """One resolved message definition: its (possibly cross-file-resolved) content plus the
    identity pointer §9.1 requires - "a component reference uses the component definition pointer;
    an inline message uses its operation message pointer"."""

    __slots__ = ("document", "document_path", "pointer_tokens")

    def __init__(self, document: dict, *, document_path: str, pointer_tokens: tuple[str, ...]):
        self.document = document
        self.document_path = document_path
        self.pointer_tokens = pointer_tokens


def _extract_message_defs(
    operation_def: dict,
    *,
    root_relative_path: str,
    channel_name: str,
    operation_key: str,
    cache,
) -> list[_MessageDef]:
    """Returns one `_MessageDef` per message declared on this operation - a `$ref` (resolved,
    possibly cross-file, via the shared §8/§9 resolver) or the message's own document-unique inline
    operation-message pointer (`channel_name`/`operation_key` included: two different channels each
    declaring their own inline, non-`$ref` message must never collide onto the same owner-scoped
    identity just because both happen to sit at an operation's bare `message` key). Raises
    `ReferenceResolutionError` on any resolution failure - the caller converts that into the
    appropriate whole-source `REJECTED_*` outcome.
    """
    message_obj = operation_def.get("message")
    if not message_obj:
        return []
    if "oneOf" in message_obj:
        results = []
        for index, candidate in enumerate(message_obj["oneOf"]):
            if "$ref" in candidate:
                resolved = resolve_and_read(
                    containing_document_relative_path=root_relative_path,
                    ref=candidate["$ref"],
                    cache=cache,
                )
                results.append(
                    _MessageDef(
                        resolved.target_node,
                        document_path=resolved.normalized_relative_path,
                        pointer_tokens=resolved.pointer_tokens,
                    )
                )
            else:
                results.append(
                    _MessageDef(
                        candidate,
                        document_path=root_relative_path,
                        pointer_tokens=(
                            "channels",
                            channel_name,
                            operation_key,
                            "message",
                            "oneOf",
                            str(index),
                        ),
                    )
                )
        return results
    if "$ref" in message_obj:
        resolved = resolve_and_read(
            containing_document_relative_path=root_relative_path,
            ref=message_obj["$ref"],
            cache=cache,
        )
        return [
            _MessageDef(
                resolved.target_node,
                document_path=resolved.normalized_relative_path,
                pointer_tokens=resolved.pointer_tokens,
            )
        ]
    return [
        _MessageDef(
            message_obj,
            document_path=root_relative_path,
            pointer_tokens=("channels", channel_name, operation_key, "message"),
        )
    ]


def _resolve_selected_servers(document: dict, channel_def: dict) -> list[dict]:
    servers_map = document.get("servers") or {}
    channel_servers = channel_def.get("servers")
    if channel_servers:
        return [servers_map[name] for name in channel_servers if name in servers_map]
    return list(servers_map.values())


class _AmbiguousBrokerNamespace:
    """Sentinel distinguishing "selected servers exist but disagree (or only some of them carry
    `x-aip-broker-id`)" from genuinely no selected server/no evidence at all (`None`). Collapsing
    both into one `None` previously let an explicit Queue mapping silently paper over real
    multi-server disagreement, since "no derived id to compare against" and "a derived id exists but
    is unresolvable due to conflict" both looked like "no derived id" to the caller.
    """


_AMBIGUOUS_BROKER_NAMESPACE = _AmbiguousBrokerNamespace()


def _resolve_broker_and_namespace(
    selected_servers: list[dict],
) -> tuple[str, str] | None | _AmbiguousBrokerNamespace:
    """I1 spec §9: broker id from an explicit `x-aip-broker-id` on the selected server(s); when a
    channel selects multiple servers, all must agree on both broker id and namespace or the result
    is ambiguous (`_AMBIGUOUS_BROKER_NAMESPACE`) - distinct from `None`, which means no selected
    server carries any broker evidence at all. Namespace is the AMQP server binding `virtualHost`,
    else empty string - §9's "configured destination namespace" path is deferred (no config surface
    ships in 3a).
    """
    if not selected_servers:
        return None
    candidates: set[tuple[str, str]] = set()
    any_missing = False
    for server in selected_servers:
        broker_id = server.get("x-aip-broker-id")
        if not broker_id:
            any_missing = True
            continue
        namespace = ((server.get("bindings") or {}).get("amqp") or {}).get("virtualHost") or ""
        candidates.add((broker_id, namespace))
    if not candidates:
        return None
    if any_missing or len(candidates) != 1:
        return _AMBIGUOUS_BROKER_NAMESPACE
    return next(iter(candidates))


class _KindEvidence:
    """One channel's destination-kind evidence, per path (I1 spec §9, widened by I4 spec §8.1).

    - `queue_paths`: positive Queue evidence - `x-aip-destination-kind: queue`, AMQP `is: queue`, or
      a configured `queueMappings` entry at the Channel pointer (§9's "versioned configured
      destination mapping declares kind = 'queue'").
    - `topic_paths`: positive Topic evidence - exactly `x-aip-destination-kind: topic`, or a valid
      `topicMappings` entry at the Channel pointer (I4 §7.3: its presence is positive Topic-kind
      evidence).
    - `non_queue_vote`: a present kind value that is neither - any other extension value
      (`pubsub`, `broadcast`, a vendor name, ...) or any AMQP `is` other than `queue` (e.g.
      `routingKey`). It contradicts Queue evidence under the unchanged I1 rule but never supplies
      Topic evidence (I4 §8.1: no negative inference).
    """

    __slots__ = ("non_queue_vote", "queue_paths", "topic_paths")

    def __init__(self, queue_paths: list[str], topic_paths: list[str], non_queue_vote: bool):
        self.queue_paths = queue_paths
        self.topic_paths = topic_paths
        self.non_queue_vote = non_queue_vote


def _classify_destination_kind(
    channel_def: dict, *, queue_mapped: bool, topic_mapped: bool
) -> _KindEvidence:
    queue_paths: list[str] = []
    topic_paths: list[str] = []
    non_queue_vote = False
    if "x-aip-destination-kind" in channel_def:
        declared_kind = channel_def["x-aip-destination-kind"]
        if declared_kind == "queue":
            queue_paths.append("x-aip-destination-kind")
        elif declared_kind == "topic":
            topic_paths.append("x-aip-destination-kind")
        else:
            non_queue_vote = True
    amqp_binding = ((channel_def.get("bindings") or {}).get("amqp")) or {}
    if "is" in amqp_binding:
        if amqp_binding["is"] == "queue":
            queue_paths.append("bindings.amqp.is")
        else:
            non_queue_vote = True
    if queue_mapped:
        queue_paths.append("queueMappings")
    if topic_mapped:
        topic_paths.append("topicMappings")
    return _KindEvidence(sorted(queue_paths), sorted(topic_paths), non_queue_vote)


_SUBSCRIPTION_DEAD_LETTER_KEY = "x-aip-subscription-dead-letter"


def _parse_subscription_dead_letter(value: object) -> tuple[str, str | None] | None:
    """I4 spec §10 (declared construct is a slice-2 decision, disclosed in its PR): exactly
    `{target: <non-empty string>, targetKind: <non-empty string, optional>}`. Returns the
    NFC-normalized `(target_token, target_kind_token)`, or `None` for any other shape."""
    if not isinstance(value, dict) or not set(value) <= {"target", "targetKind"}:
        return None
    target = value.get("target")
    if not isinstance(target, str) or not target:
        return None
    target_kind = value.get("targetKind")
    if "targetKind" in value and (not isinstance(target_kind, str) or not target_kind):
        return None
    return unicode_nfc(target), (unicode_nfc(target_kind) if target_kind is not None else None)


class _AsyncApiMapping:
    """The state and steps of mapping one AsyncAPI document (I1 spec §9, I4 §7-§11), extracted from
    what used to be nested closures inside `AsyncApiSourceAdapter.map`.

    Each `map_*` step returns an `AdapterOutcome` only for an atomic rejection (which ends the whole
    mapping) and `None` otherwise; `finish` builds the accepted outcome. The steps must run in the
    order `map_queues`, `map_dead_letter_targets`, `map_operations`: later steps read the channel ->
    Queue/Topic tables the earlier ones fill, and diagnostics accumulate in that order.
    """

    def __init__(
        self,
        loaded: LoadedSource,
        *,
        shared_identity: SharedIdentityResolver,
        canonical_service_id: str,
        cache: ResolutionCache,
        root_relative_path: str,
    ):
        self.loaded = loaded
        self.document = loaded.document
        self.locator = loaded.descriptor.locator
        self.source_instance_id = loaded.descriptor.source_instance_id
        self.shared_identity = shared_identity
        self.canonical_service_id = canonical_service_id
        self.cache = cache
        self.root_relative_path = root_relative_path
        self.channels = self.document.get("channels") or {}

        self.queues_by_id: dict[str, Queue] = {}
        self.messages_by_id: dict[str, Message] = {}
        self.schemas_by_id: dict[str, Schema] = {}
        self.relations: list[Relation] = []
        self.seen_relations: set[tuple[str, str, str]] = set()
        self.diagnostics: list[IngestionDiagnostic] = []
        self.any_uninterpreted_composition = False

        self.channel_queue_id: dict[str, str] = {}
        self.channel_broker_namespace: dict[str, tuple[str, str]] = {}
        self.any_channel_supported = False
        self.any_omission = False

        # v0.5.0 I4 §7-§11 Topic/Subscription state. Declarations are collected as field dicts and
        # materialized after the semantic input digest is known (§11 retains it per artifact).
        self.topics_by_id: dict[str, Topic] = {}
        self.subscriptions_by_id: dict[str, Subscription] = {}
        self.dead_letter_configurations: list[SubscriptionDeadLetterConfiguration] = []
        self.pending_declarations: list[dict] = []
        self.channel_topic_id: dict[str, str] = {}
        # channel -> (stable broker id or None, namespace-or-empty, exact NFC channel address)
        self.channel_topic_context: dict[str, tuple[str | None, str, str]] = {}

    def add_relation(self, relation_type: str, source_id: str, target_id: str) -> None:
        key = (relation_type, source_id, target_id)
        if key not in self.seen_relations:
            self.seen_relations.add(key)
            self.relations.append(
                Relation(type=relation_type, source_id=source_id, target_id=target_id)
            )

    def resolve_payload_schema_id(
        self,
        payload: dict | None,
        *,
        message_id: str,
        message_name: str,
        message_document_path: str,
        message_pointer_tokens: tuple[str, ...],
    ) -> tuple[str | None, JSONValue | None, AdapterOutcome | None]:
        """I1 spec §9.1: "A payload $ref always uses the resolved definition's §8.1 Schema ID;
        only a payload defined inline uses the message-owned inline payload ID". The payload
        lives inside the message's OWN document, not necessarily the root - a relative $ref
        (or an inline payload's own identity pointer) must resolve against
        `message_document_path`, never unconditionally against the root's own path, or a
        payload declared inside an externally-referenced message document resolves relative to
        the wrong directory. Returns (schema_id, normalized_payload_value, error_outcome) - the
        middle value feeds `message_contract_digest`'s payload projection.
        """
        if not payload:
            return None, None, None
        if "$ref" in payload:
            try:
                normalized = resolve_and_normalize_schema(
                    payload,
                    own_document_relative_path=message_document_path,
                    own_pointer_tokens=message_pointer_tokens,
                    cache=self.cache,
                )
            except ReferenceResolutionError as exc:
                return (
                    None,
                    None,
                    rejected_outcome_for_reference_error(
                        exc, source_pointer=encode_pointer_tokens(message_pointer_tokens)
                    ),
                )
            explicit_schema_id = self.shared_identity.schema_id_for(
                source_instance_id=self.source_instance_id,
                document_path=normalized.normalized_definition_document_path,
                pointer=encode_pointer_tokens(normalized.definition_pointer_tokens),
            )
            schema_id_value = explicit_schema_id or schema_owned_id(
                canonical_service_id=self.canonical_service_id,
                source_instance_id=self.source_instance_id,
                normalized_definition_document_path=normalized.normalized_definition_document_path,
                definition_pointer_tokens=normalized.definition_pointer_tokens,
            )
            schema_name = schema_display_name(normalized.definition_pointer_tokens)
        else:
            try:
                normalized = resolve_and_normalize_schema(
                    payload,
                    own_document_relative_path=message_document_path,
                    own_pointer_tokens=(*message_pointer_tokens, "payload"),
                    cache=self.cache,
                )
            except ReferenceResolutionError as exc:
                return (
                    None,
                    None,
                    rejected_outcome_for_reference_error(
                        exc,
                        source_pointer=encode_pointer_tokens((*message_pointer_tokens, "payload")),
                    ),
                )
            explicit_schema_id = self.shared_identity.schema_id_for(
                source_instance_id=self.source_instance_id,
                document_path=normalized.normalized_definition_document_path,
                pointer=encode_pointer_tokens(normalized.definition_pointer_tokens),
            )
            schema_id_value = explicit_schema_id or inline_payload_schema_id(
                message_id=message_id,
                normalized_inline_payload_document_path=normalized.normalized_definition_document_path,
                inline_payload_pointer_tokens=normalized.definition_pointer_tokens,
            )
            # Schema.name is a display label only (identity comes from schema_id_value) - an
            # inline payload has no component name of its own, so fall back to its owning
            # message's name.
            schema_name = f"{message_name} payload"

        if normalized.has_uninterpreted_composition:
            self.any_uninterpreted_composition = True

        conflict = upsert_schema_or_conflict(
            self.schemas_by_id,
            schema_id_value,
            Schema(
                id=schema_id_value,
                name=schema_name,
                format="application/json",
                canonical_hash=normalized.canonical_hash,
            ),
        )
        if conflict is not None:
            return (
                None,
                None,
                AdapterOutcome(
                    result=IngestionResult.REJECTED_CONFLICT,
                    model=ArchitectureModel(),
                    diagnostics=(conflict,),
                    semantic_input_digest=None,
                ),
            )
        return schema_id_value, normalized.normalized_value, None

    def resolve_topic(
        self,
        channel_name: str,
        channel_def: dict,
        *,
        channel_pointer: str,
        explicit_topic_id: str | None,
        kind_evidence: list[str],
    ) -> AdapterOutcome | None:
        """I4 spec §7.1/§8.1: positive Topic-kind evidence exists; establish qualified Topic
        identity or omit the channel. Returns an outcome only for an atomic rejection."""
        broker_and_namespace = _resolve_broker_and_namespace(
            _resolve_selected_servers(self.document, channel_def)
        )
        # Mirrors the Queue rule: disagreeing/partial server declarations leave identity
        # AMBIGUOUS even when a configured Topic id exists.
        if isinstance(broker_and_namespace, _AmbiguousBrokerNamespace):
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.AMBIGUOUS,
                    message=(
                        f"channel {channel_name!r}: no single agreeing broker id/namespace "
                        "across selected servers"
                    ),
                    source_pointer=channel_pointer,
                )
            )
            return None

        topic_address = unicode_nfc(channel_name)
        stable_broker_id, namespace = None, ""
        derived_topic_id = None
        if broker_and_namespace is not None:
            stable_broker_id, namespace = broker_and_namespace
            derived_topic_id = topic_owned_id(
                stable_broker_id=stable_broker_id,
                normalized_namespace_or_empty=namespace,
                exact_topic_address=topic_address,
            )

        if (
            explicit_topic_id is not None
            and derived_topic_id is not None
            and explicit_topic_id != derived_topic_id
        ):
            return AdapterOutcome(
                result=IngestionResult.REJECTED_CONFLICT,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.TOPIC_IDENTITY_CONFLICT,
                        message=(
                            f"channel {channel_name!r}: configured Topic id "
                            f"{explicit_topic_id!r} disagrees with the derived id "
                            f"{derived_topic_id!r}"
                        ),
                        source_pointer=channel_pointer,
                    ),
                ),
                semantic_input_digest=None,
            )

        topic_id_value = explicit_topic_id or derived_topic_id
        if topic_id_value is None:
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.AMBIGUOUS,
                    message=(
                        f"channel {channel_name!r}: Topic kind evidence without a stable "
                        "broker id or a configured Topic id"
                    ),
                    source_pointer=channel_pointer,
                )
            )
            return None

        self.topics_by_id.setdefault(
            topic_id_value,
            Topic(
                id=topic_id_value,
                name=channel_name,
                protocol=next(iter(channel_def.get("bindings") or {}), None),
                namespace=namespace or None,
            ),
        )
        self.channel_topic_id[channel_name] = topic_id_value
        self.channel_topic_context[channel_name] = (stable_broker_id, namespace, topic_address)
        self.pending_declarations.append(
            {
                "entity_id": topic_id_value,
                "entity_kind": "TOPIC",
                "source_pointer": channel_pointer,
                "broker_id": stable_broker_id,
                "namespace": namespace or None,
                "kind_evidence": kind_evidence,
                "identity_methods": sorted(
                    {
                        *(["CONFIGURED"] if explicit_topic_id is not None else []),
                        *(["DERIVED"] if derived_topic_id is not None else []),
                    }
                ),
                "topic_address": topic_address,
            }
        )
        return None

    def resolve_subscription(
        self, channel_name: str, operation_def: dict, *, topic_id_value: str
    ) -> tuple[str | None, AdapterOutcome | None]:
        """I4 spec §7.2/§7.3/§8.3: a Topic subscribe operation needs explicit Subscription
        identity; nothing is ever synthesized from a Service/Channel/operationId/path. Returns
        (subscription id or None when omitted, atomic-rejection outcome or None)."""
        operation_pointer = encode_pointer_tokens(("channels", channel_name, "subscribe"))
        dead_letter, rejection = self._parse_subscription_dead_letter_or_reject(
            channel_name, operation_def
        )
        if rejection is not None:
            return None, rejection

        mapping = self.shared_identity.subscription_mapping_for(
            source_instance_id=self.source_instance_id,
            document_path=self.root_relative_path,
            pointer=operation_pointer,
        )
        raw_name = operation_def.get("x-aip-subscription-name")
        declared_name = unicode_nfc(raw_name) if isinstance(raw_name, str) and raw_name else None

        def conflict(message: str) -> tuple[None, AdapterOutcome]:
            return None, AdapterOutcome(
                result=IngestionResult.REJECTED_CONFLICT,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.SUBSCRIPTION_IDENTITY_CONFLICT,
                        message=f"channel {channel_name!r}: {message}",
                        source_pointer=operation_pointer,
                    ),
                ),
                semantic_input_digest=None,
            )

        if mapping is not None and mapping.topic_id != topic_id_value:
            return conflict(
                f"configured Subscription binds Topic {mapping.topic_id!r}, but the Channel "
                f"resolves Topic {topic_id_value!r}"
            )
        if (
            mapping is not None
            and declared_name is not None
            and mapping.subscription_name != declared_name
        ):
            return conflict(
                f"configured Subscription name {mapping.subscription_name!r} disagrees with "
                f"x-aip-subscription-name {declared_name!r}"
            )

        subscription_name = declared_name or (mapping.subscription_name if mapping else None)
        stable_broker_id, namespace, topic_address = self.channel_topic_context[channel_name]
        derived_subscription_id = None
        if subscription_name is not None and stable_broker_id is not None:
            derived_subscription_id = subscription_owned_id(
                stable_broker_id=stable_broker_id,
                normalized_namespace_or_empty=namespace,
                topic_id=topic_id_value,
                exact_subscription_name=subscription_name,
            )
        if (
            mapping is not None
            and derived_subscription_id is not None
            and mapping.subscription_id != derived_subscription_id
        ):
            return conflict(
                f"configured Subscription id {mapping.subscription_id!r} disagrees with the "
                f"derived id {derived_subscription_id!r}"
            )

        subscription_id_value = (
            mapping.subscription_id if mapping is not None else derived_subscription_id
        )
        if subscription_id_value is None:
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.SUBSCRIPTION_IDENTITY_MISSING,
                    message=(
                        f"channel {channel_name!r}: Topic subscribe operation has no explicit "
                        "x-aip-subscription-name with stable broker identity and no "
                        "configured Subscription mapping; subscribe-side topology omitted"
                    ),
                    source_pointer=operation_pointer,
                )
            )
            return None, None

        self._record_subscription(
            channel_name,
            operation_pointer=operation_pointer,
            topic_id_value=topic_id_value,
            subscription_id_value=subscription_id_value,
            subscription_name=subscription_name,
            mapping=mapping,
            declared_name=declared_name,
            derived_subscription_id=derived_subscription_id,
            stable_broker_id=stable_broker_id,
            namespace=namespace,
            topic_address=topic_address,
            dead_letter=dead_letter,
        )
        return subscription_id_value, None

    def _parse_subscription_dead_letter_or_reject(
        self, channel_name: str, operation_def: dict
    ) -> tuple[tuple[str, str | None] | None, AdapterOutcome | None]:
        """The subscribe operation's optional dead-letter declaration, or an atomic REJECTED_INVALID
        when it is present but malformed."""
        dead_letter = None
        if _SUBSCRIPTION_DEAD_LETTER_KEY in operation_def:
            dead_letter = _parse_subscription_dead_letter(
                operation_def[_SUBSCRIPTION_DEAD_LETTER_KEY]
            )
            if dead_letter is None:
                return None, AdapterOutcome(
                    result=IngestionResult.REJECTED_INVALID,
                    model=ArchitectureModel(),
                    diagnostics=(
                        IngestionDiagnostic(
                            code=DiagnosticCode.DOCUMENT_PARSE_INVALID,
                            message=(
                                f"channel {channel_name!r}: {_SUBSCRIPTION_DEAD_LETTER_KEY} "
                                "must be {target: <non-empty string>, targetKind: "
                                "<non-empty string, optional>}"
                            ),
                            source_pointer=encode_pointer_tokens(
                                (
                                    "channels",
                                    channel_name,
                                    "subscribe",
                                    _SUBSCRIPTION_DEAD_LETTER_KEY,
                                )
                            ),
                        ),
                    ),
                    semantic_input_digest=None,
                )
        return dead_letter, None

    def _record_subscription(
        self,
        channel_name: str,
        *,
        operation_pointer: str,
        topic_id_value: str,
        subscription_id_value: str,
        subscription_name: str | None,
        mapping: SubscriptionMapping | None,
        declared_name: str | None,
        derived_subscription_id: str | None,
        stable_broker_id: str | None,
        namespace: str,
        topic_address: str,
        dead_letter: tuple[str, str | None] | None,
    ) -> None:
        """Register a resolved Subscription, its Pub/Sub declaration and any dead-letter
        configuration (I4 spec §7.2/§7.3/§11)."""
        # A subscription id comes from a mapping (whose subscription_name backs this one) or is
        # derived, which requires a subscription_name - so the name is set here.
        assert subscription_name is not None
        topic = self.topics_by_id[topic_id_value]
        self.subscriptions_by_id.setdefault(
            subscription_id_value,
            Subscription(
                id=subscription_id_value,
                name=subscription_name,
                protocol=topic.protocol,
                namespace=topic.namespace,
            ),
        )
        self.pending_declarations.append(
            {
                "entity_id": subscription_id_value,
                "entity_kind": "SUBSCRIPTION",
                "source_pointer": operation_pointer,
                "broker_id": stable_broker_id,
                "namespace": namespace or None,
                "kind_evidence": sorted(
                    {
                        *(["subscriptionMappings"] if mapping is not None else []),
                        *(["x-aip-subscription-name"] if declared_name is not None else []),
                    }
                ),
                "identity_methods": sorted(
                    {
                        *(["CONFIGURED"] if mapping is not None else []),
                        *(["DERIVED"] if derived_subscription_id is not None else []),
                    }
                ),
                "topic_address": topic_address,
                "topic_id": topic_id_value,
                "subscription_name": subscription_name,
            }
        )
        if dead_letter is not None:
            target_token, target_kind_token = dead_letter
            self.dead_letter_configurations.append(
                SubscriptionDeadLetterConfiguration(
                    subscription_id=subscription_id_value,
                    source_instance_id=self.source_instance_id,
                    source_locator=self.locator,
                    source_revision=self.loaded.descriptor.declared_provider_revision,
                    source_pointer=encode_pointer_tokens(
                        ("channels", channel_name, "subscribe", _SUBSCRIPTION_DEAD_LETTER_KEY)
                    ),
                    target_token=target_token,
                    target_kind_token=target_kind_token,
                )
            )

    def map_queues(self) -> AdapterOutcome | None:
        """Pass 1: resolve Queue (or, I4, Topic) kind and identity per channel."""
        for channel_name, channel_def in self.channels.items():
            if not isinstance(channel_def, dict):
                continue
            if (rejection := self._map_channel(channel_name, channel_def)) is not None:
                return rejection
        return None

    def _map_channel(self, channel_name: str, channel_def: dict) -> AdapterOutcome | None:
        """Classify one channel's destination kind; hand a Topic to `resolve_topic` and a Queue to
        `_resolve_queue`, or record why the channel is omitted."""
        channel_pointer = encode_pointer_tokens(("channels", channel_name))
        explicit_queue_id = self.shared_identity.queue_id_for(
            source_instance_id=self.source_instance_id,
            document_path=self.root_relative_path,
            pointer=channel_pointer,
        )
        explicit_topic_id = self.shared_identity.topic_id_for(
            source_instance_id=self.source_instance_id,
            document_path=self.root_relative_path,
            pointer=channel_pointer,
        )

        # §9: "versioned configured destination mapping declares kind = 'queue'" is a third
        # Queue-kind evidence path, on equal footing with the extension/AMQP-binding paths - an
        # explicit mapping's mere presence counts as Queue evidence. I4 §8.1 adds the Topic
        # paths. Every path is classified together so disagreement among ANY of them is caught
        # uniformly, distinct from no evidence at all - and no precedence ever picks a winner.
        kind = _classify_destination_kind(
            channel_def,
            queue_mapped=explicit_queue_id is not None,
            topic_mapped=explicit_topic_id is not None,
        )
        if kind.queue_paths and (kind.topic_paths or kind.non_queue_vote):
            return AdapterOutcome(
                result=IngestionResult.REJECTED_CONFLICT,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.QUEUE_KIND_CONFLICT,
                        message=(
                            f"channel {channel_name!r}: Queue/Topic kind evidence paths disagree"
                            if kind.topic_paths
                            else f"channel {channel_name!r}: Queue-kind evidence paths disagree"
                        ),
                        source_pointer=channel_pointer,
                    ),
                ),
                semantic_input_digest=None,
            )
        if kind.topic_paths:
            topic_outcome = self.resolve_topic(
                channel_name,
                channel_def,
                channel_pointer=channel_pointer,
                explicit_topic_id=explicit_topic_id,
                kind_evidence=kind.topic_paths,
            )
            if topic_outcome is not None:
                return topic_outcome
            return None
        if not kind.queue_paths and not kind.non_queue_vote:
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.QUEUE_EVIDENCE_MISSING,
                    message=f"channel {channel_name!r}: no Queue-kind evidence path succeeded",
                    source_pointer=channel_pointer,
                )
            )
            return None
        if not kind.queue_paths:
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.QUEUE_EVIDENCE_MISSING,
                    message=f"channel {channel_name!r}: destination kind evidence is not 'queue'",
                    source_pointer=channel_pointer,
                )
            )
            return None
        return self._resolve_queue(
            channel_name,
            channel_def,
            channel_pointer=channel_pointer,
            explicit_queue_id=explicit_queue_id,
        )

    def _resolve_queue(
        self,
        channel_name: str,
        channel_def: dict,
        *,
        channel_pointer: str,
        explicit_queue_id: str | None,
    ) -> AdapterOutcome | None:
        """A channel with Queue-kind evidence: establish its Queue identity (I1 spec §9) or omit it."""
        # §9: "a configured Queue ID that disagrees with the derived ID" is REJECTED_CONFLICT -
        # both identity paths are computed (whenever each has enough evidence to compute at
        # all) and compared, not just whichever one happens to be present. A channel lacking
        # broker/namespace evidence altogether (the genuine "unchanged v0.4.2 fixture, no
        # x-aip-broker-id yet" case §9 actually describes) has no derived id to compare against,
        # so the configured mapping alone establishes identity with nothing to conflict with.
        selected_servers = _resolve_selected_servers(self.document, channel_def)
        broker_and_namespace = _resolve_broker_and_namespace(selected_servers)

        # §9: selected servers that disagree (or only partially carry `x-aip-broker-id`) leave
        # this channel's Queue identity AMBIGUOUS regardless of an explicit mapping - a
        # configured Queue ID does not resolve a real disagreement among the channel's own
        # server declarations, it only supplies an id to compare a *resolved* derived id
        # against. Checked before consulting `explicit_queue_id` at all so the ambiguity can't
        # be silently papered over by treating it the same as "no derived id to compare".
        if isinstance(broker_and_namespace, _AmbiguousBrokerNamespace):
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.AMBIGUOUS,
                    message=(
                        f"channel {channel_name!r}: no single agreeing broker id/namespace "
                        "across selected servers"
                    ),
                    source_pointer=channel_pointer,
                )
            )
            return None

        derived_queue_id: str | None = None
        stable_broker_id, namespace = None, None
        if broker_and_namespace is not None:
            stable_broker_id, namespace = broker_and_namespace
            channel_address = unicode_nfc(channel_name)
            derived_queue_id = queue_owned_id(
                stable_broker_id=stable_broker_id,
                normalized_namespace_or_empty=namespace,
                exact_channel_address=channel_address,
            )

        if (
            explicit_queue_id is not None
            and derived_queue_id is not None
            and explicit_queue_id != derived_queue_id
        ):
            return AdapterOutcome(
                result=IngestionResult.REJECTED_CONFLICT,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.QUEUE_IDENTITY_CONFLICT,
                        message=(
                            f"channel {channel_name!r}: configured Queue id "
                            f"{explicit_queue_id!r} disagrees with the derived id "
                            f"{derived_queue_id!r}"
                        ),
                        source_pointer=channel_pointer,
                    ),
                ),
                semantic_input_digest=None,
            )

        if explicit_queue_id is not None:
            queue_id_value = explicit_queue_id
        elif derived_queue_id is not None:
            queue_id_value = derived_queue_id
        else:
            self.any_omission = True
            self.diagnostics.append(
                IngestionDiagnostic(
                    code=DiagnosticCode.AMBIGUOUS,
                    message=(
                        f"channel {channel_name!r}: no single agreeing broker id/namespace "
                        "across selected servers"
                    ),
                    source_pointer=channel_pointer,
                )
            )
            return None

        protocol = next(iter(channel_def.get("bindings") or {}), None)
        self.queues_by_id[queue_id_value] = Queue(
            id=queue_id_value,
            name=channel_name,
            protocol=protocol,
            namespace=namespace or None,
        )
        self.channel_queue_id[channel_name] = queue_id_value
        if broker_and_namespace is not None:
            self.channel_broker_namespace[channel_name] = broker_and_namespace
        return None

    def map_dead_letter_targets(self) -> AdapterOutcome | None:
        """Pass 1b: DEAD_LETTERS_TO links between resolved Queues."""
        # DLQ links inherit their declaring channel's resolved broker/namespace by default (§9 gives
        # no separate built-in evidence path for a DLQ target's own kind/identity) - but the target
        # can also have its own explicit shared-identity mapping, keyed at the
        # `x-dead-letter-queue` field's own pointer, taking priority the same way a channel's own
        # mapping does.
        for channel_name, channel_def in self.channels.items():
            if not isinstance(channel_def, dict):
                continue
            dlq_target_name = channel_def.get("x-dead-letter-queue")
            if not dlq_target_name:
                continue
            if channel_name not in self.channel_queue_id:
                self.any_omission = True
                self.diagnostics.append(
                    IngestionDiagnostic(
                        code=DiagnosticCode.QUEUE_EVIDENCE_MISSING,
                        message=(
                            f"channel {channel_name!r}: cannot establish DEAD_LETTERS_TO target "
                            "without a resolved declaring Queue"
                        ),
                        source_pointer=encode_pointer_tokens(("channels", channel_name)),
                    )
                )
                continue

            dlq_pointer = encode_pointer_tokens(("channels", channel_name, "x-dead-letter-queue"))
            explicit_target_queue_id = self.shared_identity.queue_id_for(
                source_instance_id=self.source_instance_id,
                document_path=self.root_relative_path,
                pointer=dlq_pointer,
            )
            derived_target_queue_id = None
            target_namespace = None
            if channel_name in self.channel_broker_namespace:
                stable_broker_id, namespace = self.channel_broker_namespace[channel_name]
                target_address = unicode_nfc(dlq_target_name)
                derived_target_queue_id = queue_owned_id(
                    stable_broker_id=stable_broker_id,
                    normalized_namespace_or_empty=namespace,
                    exact_channel_address=target_address,
                )
                target_namespace = namespace

            if (
                explicit_target_queue_id is not None
                and derived_target_queue_id is not None
                and explicit_target_queue_id != derived_target_queue_id
            ):
                return AdapterOutcome(
                    result=IngestionResult.REJECTED_CONFLICT,
                    model=ArchitectureModel(),
                    diagnostics=(
                        IngestionDiagnostic(
                            code=DiagnosticCode.QUEUE_IDENTITY_CONFLICT,
                            message=(
                                f"channel {channel_name!r}: configured DEAD_LETTERS_TO target id "
                                f"{explicit_target_queue_id!r} disagrees with the derived id "
                                f"{derived_target_queue_id!r}"
                            ),
                            source_pointer=dlq_pointer,
                        ),
                    ),
                    semantic_input_digest=None,
                )

            if explicit_target_queue_id is not None:
                target_queue_id = explicit_target_queue_id
            elif derived_target_queue_id is not None:
                target_queue_id = derived_target_queue_id
            else:
                # The declaring channel has no derived broker/namespace to inherit and the DLQ
                # target has no explicit mapping of its own - there is no evidence path left to
                # establish its identity.
                self.any_omission = True
                self.diagnostics.append(
                    IngestionDiagnostic(
                        code=DiagnosticCode.QUEUE_EVIDENCE_MISSING,
                        message=(
                            f"channel {channel_name!r}: DEAD_LETTERS_TO target has no explicit "
                            "mapping and its declaring channel has no derived broker/namespace "
                            "to inherit"
                        ),
                        source_pointer=dlq_pointer,
                    )
                )
                continue

            if target_queue_id not in self.queues_by_id:
                self.queues_by_id[target_queue_id] = Queue(
                    id=target_queue_id, name=dlq_target_name, namespace=target_namespace or None
                )
            self.add_relation(
                "DEAD_LETTERS_TO", self.channel_queue_id[channel_name], target_queue_id
            )
        return None

    def map_operations(self) -> AdapterOutcome | None:
        """Pass 2: publish/subscribe operations and their messages."""
        # Pass 2: publish/subscribe operations and their messages, only for channels with a
        # resolved Queue or (I4) a resolved Topic.
        for channel_name, channel_def in self.channels.items():
            if not isinstance(channel_def, dict):
                continue
            if channel_name in self.channel_queue_id:
                destination_id = self.channel_queue_id[channel_name]
                is_topic = False
            elif channel_name in self.channel_topic_id:
                destination_id = self.channel_topic_id[channel_name]
                is_topic = True
            else:
                continue

            for operation_key, direction in OPERATION_DIRECTIONS.items():
                operation_def = channel_def.get(operation_key)
                if not isinstance(operation_def, dict):
                    continue
                if (
                    rejection := self._map_operation(
                        channel_name,
                        operation_key,
                        direction,
                        operation_def,
                        destination_id=destination_id,
                        is_topic=is_topic,
                    )
                ) is not None:
                    return rejection
        return None

    def _map_operation(
        self,
        channel_name: str,
        operation_key: str,
        direction: Direction,
        operation_def: dict,
        *,
        destination_id: str,
        is_topic: bool,
    ) -> AdapterOutcome | None:
        """One publish/subscribe operation on a channel with a resolved Queue or Topic: its
        direction relation, then every message it carries."""
        self.any_channel_supported = True
        if not is_topic:
            self.add_relation(RELATION_TYPES[direction], self.canonical_service_id, destination_id)
        elif direction is Direction.SEND:
            # I4 §8.2: application-perspective publish on a qualified Topic.
            self.add_relation("PUBLISHES_TO", self.canonical_service_id, destination_id)
        else:
            # I4 §8.3: subscribe identifies direction only; topology needs explicit
            # Subscription identity. Topic CARRIES Message remains either way.
            subscription_id_value, error_outcome = self.resolve_subscription(
                channel_name, operation_def, topic_id_value=destination_id
            )
            if error_outcome is not None:
                return error_outcome
            if subscription_id_value is not None:
                self.add_relation("SUBSCRIPTION_OF", subscription_id_value, destination_id)
                self.add_relation("RECEIVES_FROM", self.canonical_service_id, subscription_id_value)

        try:
            message_defs = _extract_message_defs(
                operation_def,
                root_relative_path=self.root_relative_path,
                channel_name=channel_name,
                operation_key=operation_key,
                cache=self.cache,
            )
        except ReferenceResolutionError as exc:
            return rejected_outcome_for_reference_error(
                exc,
                source_pointer=encode_pointer_tokens(("channels", channel_name, operation_key)),
            )

        for message_def in message_defs:
            if (
                rejection := self._map_message(
                    channel_name, operation_key, message_def, destination_id=destination_id
                )
            ) is not None:
                return rejection
        return None

    def _map_message(
        self,
        channel_name: str,
        operation_key: str,
        message_def: _MessageDef,
        *,
        destination_id: str,
    ) -> AdapterOutcome | None:
        """One message of an operation: its identity, payload schema, Message entity (first-wins, or
        an atomic conflict) and CONFORMS_TO / CARRIES relations."""
        message_document = message_def.document
        message_pointer_tokens = message_def.pointer_tokens
        try:
            normalized_x_version = normalize_x_version(message_document.get("x-version", MISSING))
        except InvalidXVersionError as exc:
            return AdapterOutcome(
                result=IngestionResult.REJECTED_INVALID,
                model=ArchitectureModel(),
                diagnostics=(
                    IngestionDiagnostic(
                        code=DiagnosticCode.SERVICE_IDENTITY_INVALID,
                        message=str(exc),
                        source_pointer=encode_pointer_tokens(
                            ("channels", channel_name, operation_key)
                        ),
                    ),
                ),
                semantic_input_digest=None,
            )

        explicit_message_id = self.shared_identity.message_id_for(
            source_instance_id=self.source_instance_id,
            document_path=message_def.document_path,
            pointer=encode_pointer_tokens(message_pointer_tokens),
        )
        message_id_value = explicit_message_id or message_owned_id(
            canonical_service_id=self.canonical_service_id,
            source_instance_id=self.source_instance_id,
            normalized_definition_document_path=message_def.document_path,
            definition_pointer_tokens=message_pointer_tokens,
            normalized_x_version_or_empty=normalized_x_version,
        )
        message_name = (
            message_document.get("name")
            or message_document.get("title")
            or f"{channel_name}:{operation_key}"
        )
        payload = message_document.get("payload")
        schema_id_value, normalized_payload_value, error_outcome = self.resolve_payload_schema_id(
            payload,
            message_id=message_id_value,
            message_name=message_name,
            message_document_path=message_def.document_path,
            message_pointer_tokens=message_pointer_tokens,
        )
        if error_outcome is not None:
            return error_outcome

        conflict = upsert_message_or_conflict(
            self.messages_by_id,
            message_id_value,
            Message(
                id=message_id_value,
                name=message_name,
                version=normalized_x_version or None,
                schema_id=schema_id_value,
                contract_digest=message_contract_digest(
                    message_document, normalized_payload=normalized_payload_value
                ),
                document_digest=message_document_digest(message_document),
            ),
        )
        if conflict is not None:
            return AdapterOutcome(
                result=IngestionResult.REJECTED_CONFLICT,
                model=ArchitectureModel(),
                diagnostics=(conflict,),
                semantic_input_digest=None,
            )
        if schema_id_value:
            self.add_relation("CONFORMS_TO", message_id_value, schema_id_value)
        self.add_relation("CARRIES", destination_id, message_id_value)
        return None

    def finish(self, *, mapping_context_digest: str) -> AdapterOutcome:
        """The accepted (or ACCEPTED_WITH_LIMITATIONS / REJECTED_UNSUPPORTED) outcome once every
        step has run without an atomic rejection."""
        info = self.document.get("info") or {}
        if not self.channels:
            result = IngestionResult.ACCEPTED
        elif not self.any_channel_supported:
            return AdapterOutcome(
                result=IngestionResult.REJECTED_UNSUPPORTED,
                model=ArchitectureModel(),
                diagnostics=tuple(self.diagnostics),
                semantic_input_digest=None,
            )
        elif self.any_omission or self.any_uninterpreted_composition:
            result = IngestionResult.ACCEPTED_WITH_LIMITATIONS
        else:
            result = IngestionResult.ACCEPTED

        if self.any_uninterpreted_composition:
            self.diagnostics.append(
                composition_limitation_diagnostic(self.locator, subject="payload schemas")
            )

        evidence = declared_evidence(self.loaded, "ASYNCAPI")
        self.relations = stamp_evidence(self.relations, evidence)

        digest = semantic_input_digest(
            normalized_document_projection_bytes=semantic_input_digest_bytes(self.cache),
            mapping_context_digest=mapping_context_digest,
        )

        model = ArchitectureModel(
            services=[
                Service(
                    id=self.canonical_service_id,
                    name=info.get("title", self.canonical_service_id),
                    version=info.get("version"),
                )
            ],
            queues=list(self.queues_by_id.values()),
            messages=list(self.messages_by_id.values()),
            schemas=list(self.schemas_by_id.values()),
            relations=self.relations,
            provenance=[evidence],
            topics=list(self.topics_by_id.values()),
            subscriptions=list(self.subscriptions_by_id.values()),
            pubsub_declarations=[
                PubSubDeclaration(
                    **fields,
                    source_instance_id=self.source_instance_id,
                    source_locator=self.locator,
                    source_revision=self.loaded.descriptor.declared_provider_revision,
                    semantic_input_digest=digest,
                    adapter_identity=self.loaded.descriptor.adapter_identity,
                    mapping_rule_id=self.loaded.descriptor.mapping_rule_id,
                    mapping_rule_version=self.loaded.descriptor.mapping_rule_version,
                )
                for fields in self.pending_declarations
            ],
            subscription_dead_letter_configurations=self.dead_letter_configurations,
        )

        return AdapterOutcome(
            result=result,
            model=model,
            diagnostics=tuple(self.diagnostics),
            semantic_input_digest=digest,
        )


class AsyncApiSourceAdapter:
    """I1 spec §9: migrates `parse_asyncapi` onto the registry seam. Owner-scoped RFC 8785
    Message/Schema ids; Queue kind/identity requires real evidence (`x-aip-destination-kind`/AMQP
    `is: queue` + `x-aip-broker-id`) instead of being derived from the bare channel name; bounded
    multi-file `$ref` resolution and payload composition handling reuse the identical §8/§8.1
    contract via `app.ingestion.conflicts` (PR3b).
    """

    adapter_identity = "asyncapi-adapter@1"
    mapping_rule_version = "v1"
    dependency_phase = 0

    def supports(self, loaded: LoadedSource) -> bool:
        return "asyncapi" in loaded.document

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

        if (rejection := reject_if_invalid(loaded, validate_asyncapi_document)) is not None:
            return rejection
        if (
            rejection := reject_if_unsupported_dialect(
                loaded, dialect_key="asyncapi", accepted_versions=ACCEPTED_ASYNCAPI_VERSIONS
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
        canonical_service_id = resolved_service_id(root_resolution)

        cache, root_relative_path = build_resolution_cache(loaded)
        closure_error = enforce_reference_closure(
            document, root_relative_path=root_relative_path, cache=cache, source_pointer=locator
        )
        if closure_error is not None:
            return closure_error

        mapping = _AsyncApiMapping(
            loaded,
            shared_identity=shared_identity,
            canonical_service_id=canonical_service_id,
            cache=cache,
            root_relative_path=root_relative_path,
        )
        for mapping_step in (
            mapping.map_queues,
            mapping.map_dead_letter_targets,
            mapping.map_operations,
        ):
            if (rejection := mapping_step()) is not None:
                return rejection
        return mapping.finish(mapping_context_digest=mapping_context_digest)
