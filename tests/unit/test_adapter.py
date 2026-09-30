from datetime import UTC, datetime

import pytest

from app.telemetry.adapter import (
    CORRELATION_EXPIRED,
    MISSING_CALLER_IDENTITY,
    MISSING_TARGET_IDENTITY,
    NO_DESTINATION_NAME,
    NO_ENVIRONMENT,
    NO_STABLE_ROUTE,
    adapt,
    correlate_http_call_observations,
    correlate_queue_observations,
)
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.telemetry.messaging_guards import (
    AMBIGUOUS_SERVICE_IDENTITY,
    CONFLICTING_SERVICE_IDENTITY,
    PLACEHOLDER_SERVICE_IDENTITY,
    UNRESOLVED_DESTINATION_SEMANTICS,
    UNSUPPORTED_DESTINATION_SEMANTICS,
)
from app.telemetry.model import RuntimeSpan
from app.telemetry.operation_resolver import DeclaredOperationCandidate
from app.telemetry.queue_resolver import DeclaredQueueCandidate
from app.telemetry.service_resolver import DeclaredServiceCandidate

ORDER_SERVICE = DeclaredServiceCandidate(
    id="service:order-service", name="OrderService", namespace=None
)
PRODUCT_SERVICE = DeclaredServiceCandidate(
    id="service:product-service", name="ProductService", namespace=None
)
SERVICE_CANDIDATES = [ORDER_SERVICE, PRODUCT_SERVICE]

GET_PRODUCT = DeclaredOperationCandidate(
    id="operation:product-service:GET:/products/{id}",
    provider_service_id="service:product-service",
    method="GET",
    path="/products/{id}",
)
OPERATION_CANDIDATES = [GET_PRODUCT]

PAYMENT_Q = DeclaredQueueCandidate(id="queue:payment-q", name="payment-q", namespace=None)
QUEUE_CANDIDATES = [PAYMENT_Q]


def _span(**overrides) -> RuntimeSpan:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_name": "op",
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "service_namespace": None,
        "service_version": None,
        "service_instance_id": None,
        "environment": "production",
        "start_time": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        "end_time": datetime(2026, 8, 26, 12, 0, 1, tzinfo=UTC),
        "attributes": {},
    }
    defaults.update(overrides)
    return RuntimeSpan(**defaults)


def _client_server_pair(**server_overrides):
    client = _span(
        span_id="c1" * 8,
        span_kind="CLIENT",
        service_name="OrderService",
        service_version="1.0.0",
    )
    server_defaults = {
        "parent_span_id": client.span_id,
        "span_kind": "SERVER",
        "service_name": "ProductService",
        "attributes": {"http.request.method": "GET", "http.route": "/products/{id}"},
    }
    server_defaults.update(server_overrides)
    server = _span(**server_defaults)
    return client, server


def _correlate(spans, **kwargs):
    return correlate_http_call_observations(
        spans,
        service_candidates=kwargs.get("service_candidates", SERVICE_CANDIDATES),
        operation_candidates=kwargs.get("operation_candidates", OPERATION_CANDIDATES),
        service_aliases=kwargs.get("service_aliases", {}),
        correlation_buffer=kwargs.get("correlation_buffer"),
    )


# --- correlation pairing -----------------------------------------------------------------------


def test_correlated_pair_produces_one_calls_fact():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.relation_type == "CALLS"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.environment == "production"
    assert batch.unresolved == []


def test_unpaired_client_only_produces_empty_batch():
    client, _ = _client_server_pair()
    batch = _correlate([client])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


def test_unpaired_server_only_produces_empty_batch():
    _, server = _client_server_pair()
    batch = _correlate([server])
    assert batch.facts == []


def test_mismatched_trace_id_does_not_correlate():
    client, server = _client_server_pair()
    client = client.model_copy(update={"trace_id": "z" * 32})
    batch = _correlate([client, server])
    assert batch.facts == []


def test_empty_batch_of_spans_produces_empty_observation_batch():
    batch = _correlate([])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


# --- cross-batch correlation (11H-B) ---------------------------------------------------------


def test_cross_batch_server_first_then_client_produces_one_calls_fact():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)

    first = _correlate([server], correlation_buffer=buffer)
    assert first.facts == []

    second = _correlate([client], correlation_buffer=buffer)
    assert len(second.facts) == 1
    fact = second.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.environment == "production"
    assert buffer.cross_batch_matches == 1


def test_cross_batch_client_first_then_server_produces_one_calls_fact():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)

    first = _correlate([client], correlation_buffer=buffer)
    assert first.facts == []

    second = _correlate([server], correlation_buffer=buffer)
    assert len(second.facts) == 1
    fact = second.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert buffer.cross_batch_matches == 1


def test_buffer_none_preserves_single_batch_only_behavior():
    client, server = _client_server_pair()
    first = _correlate([client], correlation_buffer=None)
    second = _correlate([server], correlation_buffer=None)
    assert first.facts == []
    assert second.facts == []


def test_leftover_server_missing_route_is_unresolved_not_buffered():
    _, server = _client_server_pair(attributes={})
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    batch = _correlate([server], correlation_buffer=buffer)
    assert [u.reason for u in batch.unresolved] == [NO_STABLE_ROUTE]
    assert buffer.cross_batch_matches == 0


def test_cross_batch_correlated_pair_has_client_server_correlation_mode():
    client, server = _client_server_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    batch = _correlate([server], correlation_buffer=buffer)
    assert batch.facts[0].evidence.correlation_mode == "CLIENT_SERVER"


def test_in_batch_correlated_pair_has_client_server_correlation_mode():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert batch.facts[0].evidence.correlation_mode == "CLIENT_SERVER"


# --- partial instrumentation: CLIENT_ONLY / SERVER_ONLY (11H-C) -------------------------------


def _expire_client(buffer, client):
    key = (client.trace_id, client.span_id)
    stored_span, _ = buffer._pending_clients[key]
    buffer._pending_clients[key] = (stored_span, datetime(2000, 1, 1, tzinfo=UTC))


def _expire_server(buffer, server):
    key = (server.trace_id, server.parent_span_id)
    stored_span, _ = buffer._pending_servers[key]
    buffer._pending_servers[key] = (stored_span, datetime(2000, 1, 1, tzinfo=UTC))


def test_client_only_with_peer_service_produces_a_calls_fact():
    client = _span(
        span_kind="CLIENT",
        attributes={
            "http.request.method": "GET",
            "http.route": "/products/{id}",
            "peer.service": "ProductService",
        },
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.object_id == "operation:product-service:GET:/products/{id}"
    assert fact.evidence.correlation_mode == "CLIENT_ONLY"
    assert batch.unresolved == []


def test_client_only_without_peer_service_is_unresolved():
    client = _span(
        span_kind="CLIENT",
        attributes={"http.request.method": "GET", "http.route": "/products/{id}"},
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [MISSING_TARGET_IDENTITY]


def test_client_only_without_method_or_route_is_correlation_expired():
    client = _span(span_kind="CLIENT", attributes={"peer.service": "ProductService"})
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [CORRELATION_EXPIRED]


def test_client_only_without_environment_is_unresolved():
    client = _span(
        span_kind="CLIENT",
        environment=None,
        attributes={
            "http.request.method": "GET",
            "http.route": "/products/{id}",
            "peer.service": "ProductService",
        },
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_server_only_never_invents_a_caller():
    _, server = _client_server_pair(service_name="FraudService")
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)
    _expire_server(buffer, server)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [MISSING_CALLER_IDENTITY]
    # The provider itself is still recorded as an observed-only entity, even with no caller.
    assert any(e.label == "Service" and e.name == "FraudService" for e in batch.entities)


# --- unresolved reasons --------------------------------------------------------------------------


def test_missing_environment_is_unresolved():
    client, server = _client_server_pair(environment=None)
    batch = _correlate([client, server])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_missing_route_is_unresolved():
    client, server = _client_server_pair(attributes={"http.request.method": "GET"})
    batch = _correlate([client, server])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_STABLE_ROUTE]


def test_all_unresolved_reasons_are_from_the_fixed_set():
    client_a, server_a = _client_server_pair(environment=None)
    client_b, server_b = _client_server_pair(
        span_id="c2" * 8, attributes={"http.request.method": "GET"}
    )
    server_b = server_b.model_copy(update={"parent_span_id": client_b.span_id})
    batch = _correlate([client_a, server_a, client_b, server_b])
    assert {u.reason for u in batch.unresolved} <= {NO_ENVIRONMENT, NO_STABLE_ROUTE}
    assert len(batch.unresolved) == 2


# --- evidence shape --------------------------------------------------------------------------------


def test_evidence_has_opentelemetry_defaults_and_single_observation_seed():
    client, server = _client_server_pair()
    fact = _correlate([client, server]).facts[0]
    evidence = fact.evidence
    assert evidence.source_type == "OPENTELEMETRY"
    assert evidence.evidence_type == "OBSERVED"
    assert evidence.source_file == "opentelemetry"
    assert evidence.observation_count == 1
    assert evidence.sample_trace_ids == [server.trace_id]
    assert evidence.first_seen == evidence.last_seen == fact.timestamp
    assert evidence.bucket_start <= fact.timestamp < evidence.bucket_end


def test_evidence_id_is_deterministic_for_the_same_fact():
    client, server = _client_server_pair()
    fact1 = _correlate([client, server]).facts[0]
    fact2 = _correlate([client, server]).facts[0]
    assert fact1.evidence.id == fact2.evidence.id


def test_source_service_version_comes_from_client_span():
    client, server = _client_server_pair()
    fact = _correlate([client, server]).facts[0]
    assert fact.source_service_version == "1.0.0"


# --- observed-only entities ------------------------------------------------------------------------


def test_observed_only_provider_and_operation_are_recorded_as_entities():
    client, server = _client_server_pair(service_name="FraudService")
    batch = _correlate([client, server])
    labels_and_ids = {(e.label, e.id) for e in batch.entities}
    assert ("Service", "service:fraudservice") in labels_and_ids
    # the operation is minted observed-only too, since FraudService has no declared operations
    assert any(label == "Operation" for label, _ in labels_and_ids)


def test_declared_provider_and_operation_are_not_recorded_as_entities():
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert batch.entities == []


def test_observed_only_entities_are_deduplicated_across_pairs():
    client_a, server_a = _client_server_pair(service_name="FraudService")
    client_b, server_b = _client_server_pair(span_id="c2" * 8, service_name="FraudService")
    server_b = server_b.model_copy(update={"parent_span_id": client_b.span_id})
    batch = _correlate([client_a, server_a, client_b, server_b])
    service_entities = [e for e in batch.entities if e.label == "Service"]
    assert len(service_entities) == 1


# --- observed PROVIDES relation for runtime-discovered operations (11H-D) ----------------------


def test_observed_only_operation_produces_both_calls_and_provides_facts():
    # FraudService has no declared operations at all - resolve_operation mints an OBSERVED_ONLY
    # operation id (Fall B), which must now also earn its own observed PROVIDES fact.
    client, server = _client_server_pair(service_name="FraudService")
    batch = _correlate([client, server])

    assert len(batch.facts) == 2
    calls = next(f for f in batch.facts if f.relation_type == "CALLS")
    provides = next(f for f in batch.facts if f.relation_type == "PROVIDES")

    assert calls.subject_id == "service:order-service"
    assert calls.object_id == "operation:service:fraudservice:GET:/products/{id}"

    assert provides.subject_id == "service:fraudservice"
    assert provides.object_id == calls.object_id
    assert provides.evidence.evidence_type == "OBSERVED"
    assert provides.evidence.correlation_mode == "CLIENT_SERVER"
    assert provides.evidence.id != calls.evidence.id


def test_declared_operation_produces_only_a_calls_fact():
    # GET_PRODUCT is a real declared operation (Fall A) - no second PROVIDES fact should be
    # synthesized, since one already exists from the OpenAPI import.
    client, server = _client_server_pair()
    batch = _correlate([client, server])
    assert len(batch.facts) == 1
    assert batch.facts[0].relation_type == "CALLS"


def test_client_only_observed_only_operation_also_produces_a_provides_fact():
    client = _span(
        span_kind="CLIENT",
        attributes={
            "http.request.method": "GET",
            "http.route": "/fraud-check",
            "peer.service": "FraudService",
        },
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)

    batch = _correlate([], correlation_buffer=buffer)

    assert len(batch.facts) == 2
    provides = next(f for f in batch.facts if f.relation_type == "PROVIDES")
    assert provides.subject_id == "service:fraudservice"
    assert provides.evidence.correlation_mode == "CLIENT_ONLY"


# --- correlate_queue_observations ---------------------------------------------------------------


def _queue_correlate(spans, **kwargs):
    return correlate_queue_observations(
        spans,
        service_candidates=kwargs.get("service_candidates", SERVICE_CANDIDATES),
        queue_candidates=kwargs.get("queue_candidates", QUEUE_CANDIDATES),
        service_aliases=kwargs.get("service_aliases", {}),
        queue_aliases=kwargs.get("queue_aliases", {}),
    )


def test_send_span_produces_sends_fact():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.system": "azure.servicebus",
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == "service:order-service"
    assert fact.relation_type == "SENDS"
    assert fact.object_id == "queue:payment-q"
    assert fact.evidence.correlation_mode == "MESSAGING_SEND"
    assert batch.unresolved == []


def test_receive_span_produces_receives_from_fact():
    span = _span(
        service_name="PaymentService",
        attributes={
            "messaging.operation.type": "receive",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts[0].relation_type == "RECEIVES_FROM"
    assert batch.facts[0].evidence.correlation_mode == "MESSAGING_RECEIVE"


def test_process_span_produces_receives_from_fact():
    span = _span(
        service_name="PaymentService",
        attributes={
            "messaging.operation.type": "process",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts[0].relation_type == "RECEIVES_FROM"
    assert batch.facts[0].evidence.correlation_mode == "MESSAGING_PROCESS"


def test_unrecognized_operation_type_is_silently_skipped():
    span = _span(
        attributes={"messaging.operation.type": "create", "messaging.destination.name": "payment-q"}
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_missing_operation_type_is_silently_skipped():
    span = _span(attributes={"messaging.destination.name": "payment-q"})
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_legacy_messaging_operation_attribute_shape_is_not_recognized():
    # Characterizes the current behavior underlying ledger finding qsh-kafka-operation-type-gap
    # (docs/real-world-validation/cross-system/decisions/messaging-operation-compatibility.md,
    # I4.1). This is the complete legacy attribute shape independently captured from a real
    # SmallRye Reactive Messaging Kafka producer span (messaging.operation, not
    # messaging.operation.type) - not just a missing/unrecognized value on the current key.
    # Neutral destination/system values per spec §17. This test pins current, unchanged behavior;
    # it does not assert that recognizing this shape would be safe (see
    # decisions/queue-topic-boundary.md for why it is not, on its own).
    span = _span(
        attributes={
            "messaging.operation": "publish",
            "messaging.destination.name": "orders-topic",
            "messaging.system": "kafka",
        }
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_quarkus_fights_topic_exact_captured_shape_is_not_recognized():
    # v0.4.1 I2.3 (spec §30): unlike the neutral-name test above (spec §17's general-genericity
    # convention), this uses the literal captured attributes from the real Quarkus Super Heroes
    # Kafka producer span verbatim - docs/real-world-validation/quarkus-super-heroes/evidence/
    # messaging.md and decisions/qsh-kafka-operation-type-gap.md: messaging.destination.name:
    # fights, messaging.operation (not .type): publish, messaging.system: kafka. This is what
    # actually backs the ADR 0013/completion-record claim that "the real captured Quarkus shape
    # remains unrecognized" - the neutral test alone only proves the attribute-key behavior is
    # name-generic, not that this exact real input was ever run through it.
    span = _span(
        attributes={
            "messaging.operation": "publish",
            "messaging.destination.name": "fights",
            "messaging.system": "kafka",
        }
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


def test_quarkus_shape_destination_guard_reachability_with_a_recognized_operation_type():
    # v0.4.1 I2.3 (spec §30): the frozen shape above stays unrecognized only because operation
    # recognition is frozen - this proves the destination guard itself refuses the same real
    # captured destination/system (fights/kafka) independently, once a currently-recognized
    # operation.type reaches it. No messaging.destination_kind is supplied (matching the real
    # captured shape, which never carried one) - the refusal is "unresolved" by default-deny, not
    # because "kafka" is asserted to mean topic (spec §30 explicitly forbids that assertion).
    span = _span(
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "fights",
            "messaging.system": "kafka",
        }
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [UNRESOLVED_DESTINATION_SEMANTICS]


def test_celery_instrumentation_semconv_shape_is_not_recognized():
    # Characterizes the current behavior underlying ledger findings
    # airflow-celery-messaging-runtime-status and i4-celery-instrumentation-semconv-mismatch
    # (docs/real-world-validation/cross-system/decisions/messaging-operation-compatibility.md,
    # I4.1). This is the complete attribute shape independently captured from
    # opentelemetry-instrumentation-celery==0.65b0 (destination_kind/destination, no operation
    # attribute of any name, no messaging.system) - a third, independently-shaped real span, not
    # representable by the current-key or legacy-key tests above. Neutral destination value per
    # spec §17. This test pins current, unchanged behavior.
    span = _span(
        attributes={
            "messaging.destination_kind": "queue",
            "messaging.destination": "task-queue",
        }
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.unresolved == []


def test_airflow_unknown_service_exact_captured_shape_is_not_recognized():
    # v0.4.1 I2.3 (spec §31): unlike the neutral-name test above (spec §17's general-genericity
    # convention), this uses the literal captured attributes from the real Apache Airflow/Celery
    # producer span verbatim - docs/real-world-validation/apache-airflow/profile.md: service.name:
    # unknown_service, messaging.destination_kind: queue, messaging.destination (not
    # .destination.name): default, no messaging.system. This is what actually backs the ADR 0013/
    # completion-record claim that "the real captured Airflow shape remains unrecognized" - the
    # neutral test alone only proves the attribute-key behavior is name-generic, not that this
    # exact real input was ever run through it.
    span = _span(
        service_name="unknown_service",
        attributes={
            "messaging.destination_kind": "queue",
            "messaging.destination": "default",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


def test_airflow_shape_service_identity_guard_reachability_with_a_recognized_operation_type():
    # v0.4.1 I2.3 (spec §31): the frozen shape above stays unrecognized only because destination-
    # name recognition is frozen (messaging.destination, not messaging.destination.name) - this
    # proves the service-identity guard itself refuses the real captured identity
    # (service.name: unknown_service) independently, once a currently-recognized operation.type
    # and a real destination.name reach it. The predicate under test is generic - it does not
    # inspect "Airflow", a role name, or a fixture path (spec §31).
    span = _span(
        service_name="unknown_service",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [PLACEHOLDER_SERVICE_IDENTITY]


def test_missing_destination_name_is_unresolved():
    span = _span(attributes={"messaging.operation.type": "send"})
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_DESTINATION_NAME]


def test_missing_environment_is_unresolved_for_queue_observations():
    span = _span(
        environment=None,
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_observed_only_service_and_queue_are_both_recorded():
    # v0.4.1 I2: an undeclared destination with no destination-kind evidence now refuses (default-
    # deny, spec §11) rather than silently minting - explicit kind=queue is what still allows an
    # otherwise-undeclared destination to be recorded here.
    span = _span(
        service_name="FraudService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "legacy-q",
            "messaging.destination_kind": "queue",
        },
    )
    batch = _queue_correlate([span])
    labels = {e.label for e in batch.entities}
    assert labels == {"Service", "Queue"}


def test_queue_evidence_matches_the_single_observation_seed_shape():
    span = _span(
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"}
    )
    fact = _queue_correlate([span]).facts[0]
    evidence = fact.evidence
    assert evidence.source_type == "OPENTELEMETRY"
    assert evidence.evidence_type == "OBSERVED"
    assert evidence.observation_count == 1
    assert evidence.sample_trace_ids == [span.trace_id]


# --- v0.4.1 I2.2: composed messaging-guard matrix (spec §27, C1-C17) ----------------------------
#
# Asserts complete entities/facts/unresolved shapes, not just counts, per spec §27's own
# requirement. NAMESPACED_FRAUD/AMBIGUOUS_BILLING_* are local to this section - not added to the
# shared SERVICE_CANDIDATES/QUEUE_CANDIDATES used elsewhere in this file, to avoid affecting any
# other test.

NAMESPACED_FRAUD = DeclaredServiceCandidate(
    id="service:commerce:fraud-service", name="FraudService", namespace="commerce"
)
AMBIGUOUS_BILLING_A = DeclaredServiceCandidate(
    id="service:billing-v1", name="Billing", namespace=None
)
AMBIGUOUS_BILLING_B = DeclaredServiceCandidate(
    id="service:billing-v2", name="Billing", namespace=None
)


def _assert_one_fact(batch, *, subject_id, relation_type, object_id, environment, correlation_mode):
    """Full-shape fact assertion (spec §27: "complete entities/facts/unresolved results, not only
    fact count")."""
    assert len(batch.facts) == 1
    fact = batch.facts[0]
    assert fact.subject_id == subject_id
    assert fact.relation_type == relation_type
    assert fact.object_id == object_id
    assert fact.environment == environment
    assert fact.evidence.correlation_mode == correlation_mode


def test_c1_declared_service_and_declared_queue_send_produces_one_sends_fact_no_unresolved():
    span = _span(
        service_name="OrderService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    assert batch.entities == []
    _assert_one_fact(
        batch,
        subject_id="service:order-service",
        relation_type="SENDS",
        object_id="queue:payment-q",
        environment="production",
        correlation_mode="MESSAGING_SEND",
    )


def test_c2_declared_service_and_declared_queue_receive_produces_one_receives_from_fact():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "receive",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    assert batch.entities == []
    _assert_one_fact(
        batch,
        subject_id="service:order-service",
        relation_type="RECEIVES_FROM",
        object_id="queue:payment-q",
        environment="production",
        correlation_mode="MESSAGING_RECEIVE",
    )


def test_c3_declared_service_and_declared_queue_process_produces_one_receives_from_fact():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "process",
            "messaging.destination.name": "payment-q",
        },
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    assert batch.entities == []
    _assert_one_fact(
        batch,
        subject_id="service:order-service",
        relation_type="RECEIVES_FROM",
        object_id="queue:payment-q",
        environment="production",
        correlation_mode="MESSAGING_PROCESS",
    )


def test_c4_explicit_observed_only_service_with_declared_queue_records_service_entity():
    span = _span(
        service_name="FraudService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    _assert_one_fact(
        batch,
        subject_id="service:fraudservice",
        relation_type="SENDS",
        object_id="queue:payment-q",
        environment="production",
        correlation_mode="MESSAGING_SEND",
    )
    assert len(batch.entities) == 1
    assert batch.entities[0].id == "service:fraudservice"
    assert batch.entities[0].label == "Service"
    assert batch.entities[0].name == "FraudService"


def test_c5_declared_service_with_explicit_kind_queue_undeclared_destination_records_queue_entity():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "events",
            "messaging.destination_kind": "queue",
        },
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    _assert_one_fact(
        batch,
        subject_id="service:order-service",
        relation_type="SENDS",
        object_id="queue:events",
        environment="production",
        correlation_mode="MESSAGING_SEND",
    )
    assert len(batch.entities) == 1
    assert batch.entities[0].id == "queue:events"
    assert batch.entities[0].label == "Queue"
    assert batch.entities[0].name == "events"


def test_c6_explicit_observed_only_service_and_queue_both_record_entities_one_fact():
    span = _span(
        service_name="FraudService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "events",
            "messaging.destination_kind": "queue",
        },
    )
    batch = _queue_correlate([span])
    assert batch.unresolved == []
    _assert_one_fact(
        batch,
        subject_id="service:fraudservice",
        relation_type="SENDS",
        object_id="queue:events",
        environment="production",
        correlation_mode="MESSAGING_SEND",
    )
    entities_by_label = {e.label: e for e in batch.entities}
    assert set(entities_by_label) == {"Service", "Queue"}
    assert entities_by_label["Service"].id == "service:fraudservice"
    assert entities_by_label["Queue"].id == "queue:events"


def test_c7_explicit_kind_topic_is_destination_refusal_no_entities_or_facts():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
            "messaging.destination_kind": "topic",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [UNSUPPORTED_DESTINATION_SEMANTICS]


def test_c8_unresolved_destination_semantics_no_entities_or_facts():
    span = _span(
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "unknown-destination",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [UNRESOLVED_DESTINATION_SEMANTICS]


def test_c9_placeholder_service_with_declared_queue_is_service_refusal_no_entities_or_facts():
    span = _span(
        service_name="unknown_service",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [PLACEHOLDER_SERVICE_IDENTITY]


def test_c10_ambiguous_service_with_declared_queue_is_service_refusal():
    span = _span(
        service_name="Billing",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span], service_candidates=[AMBIGUOUS_BILLING_A, AMBIGUOUS_BILLING_B])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [AMBIGUOUS_SERVICE_IDENTITY]


def test_c11_conflicting_namespace_with_declared_queue_is_service_refusal():
    span = _span(
        service_name="FraudService",
        service_namespace="warehouse",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span], service_candidates=[NAMESPACED_FRAUD])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [CONFLICTING_SERVICE_IDENTITY]


def test_c12_placeholder_service_with_explicit_kind_topic_reports_destination_reason_only():
    # Destination-first precedence (spec §6): when both guards would refuse, exactly one reason -
    # the destination's - is produced, never both and never the service reason instead.
    span = _span(
        service_name="unknown_service",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
            "messaging.destination_kind": "topic",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [UNSUPPORTED_DESTINATION_SEMANTICS]


def test_c13_accepted_span_environment_is_scoped_to_the_reporting_environment():
    # "valid namespaced service" per spec §27's C13 row - NAMESPACED_FRAUD/"commerce" is a genuinely
    # namespaced declared candidate, matched via tier1 (spec §14 step 1), not an unnamespaced one.
    span = _span(
        service_name="FraudService",
        service_namespace="commerce",
        environment="staging",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span], service_candidates=[NAMESPACED_FRAUD])
    assert batch.unresolved == []
    assert batch.entities == []  # declared match - nothing new
    _assert_one_fact(
        batch,
        subject_id="service:commerce:fraud-service",
        relation_type="SENDS",
        object_id="queue:payment-q",
        environment="staging",
        correlation_mode="MESSAGING_SEND",
    )
    assert batch.facts[0].evidence.environment == "staging"


def test_c14_unrecognized_operation_is_silently_skipped_even_with_otherwise_guard_failing_fields():
    # The guards never even run - operation recognition remains frozen and is checked first (spec
    # §20), so a topic-shaped destination and a placeholder service on the same span still produce
    # neither a fact nor an unresolved entry.
    span = _span(
        service_name="unknown_service",
        attributes={
            "messaging.operation.type": "publish",
            "messaging.destination.name": "payment-q",
            "messaging.destination_kind": "topic",
        },
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert batch.unresolved == []


def test_c15_missing_destination_name_is_still_no_destination_name():
    span = _span(service_name="OrderService", attributes={"messaging.operation.type": "send"})
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [NO_DESTINATION_NAME]


def test_c16_missing_environment_is_still_no_environment():
    span = _span(
        service_name="OrderService",
        environment=None,
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([span])
    assert batch.facts == []
    assert batch.entities == []
    assert [u.reason for u in batch.unresolved] == [NO_ENVIRONMENT]


def test_c17_mixed_batch_only_the_valid_span_contributes_artifacts():
    refused_span = _span(
        service_name="OrderService",
        trace_id="1" * 32,
        span_id="r1" * 8,
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
            "messaging.destination_kind": "topic",
        },
    )
    valid_span = _span(
        service_name="OrderService",
        trace_id="2" * 32,
        span_id="v1" * 8,
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = _queue_correlate([refused_span, valid_span])
    assert batch.entities == []  # both spans use the already-declared OrderService/payment-q
    _assert_one_fact(
        batch,
        subject_id="service:order-service",
        relation_type="SENDS",
        object_id="queue:payment-q",
        environment="production",
        correlation_mode="MESSAGING_SEND",
    )
    assert batch.facts[0].trace_id == valid_span.trace_id
    assert [u.reason for u in batch.unresolved] == [UNSUPPORTED_DESTINATION_SEMANTICS]


# --- adapt: combines HTTP and queue observations ------------------------------------------------


def test_adapt_combines_http_and_queue_facts():
    client, server = _client_server_pair()
    queue_span = _span(
        span_id="q1" * 8,
        service_name="OrderService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = adapt(
        [client, server, queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    relation_types = {f.relation_type for f in batch.facts}
    assert relation_types == {"CALLS", "SENDS"}


def test_adapt_deduplicates_entities_discovered_via_both_paths():
    client, server = _client_server_pair(service_name="FraudService")
    queue_span = _span(
        span_id="q2" * 8,
        service_name="FraudService",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = adapt(
        [client, server, queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    fraud_entities = [e for e in batch.entities if e.name == "FraudService"]
    assert len(fraud_entities) == 1


def test_refused_messaging_span_does_not_suppress_valid_http_facts_in_the_same_batch():
    client, server = _client_server_pair()
    refused_queue_span = _span(
        span_id="q3" * 8,
        service_name="OrderService",
        attributes={
            "messaging.operation.type": "send",
            "messaging.destination.name": "payment-q",
            "messaging.destination_kind": "topic",
        },
    )
    batch = adapt(
        [client, server, refused_queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    assert {f.relation_type for f in batch.facts} == {"CALLS"}
    assert [u.reason for u in batch.unresolved] == [UNSUPPORTED_DESTINATION_SEMANTICS]


def test_messaging_placeholder_refusal_does_not_change_http_service_resolution():
    # The messaging service-identity guard is scoped to the messaging path only (spec §14) -
    # "unknown_service" refuses for messaging but the HTTP path's own resolver is untouched and
    # still mints it as OBSERVED_ONLY exactly as before (this is the provider/SERVER side here;
    # _client_server_pair only exposes server_overrides).
    client, server = _client_server_pair(service_name="unknown_service")
    queue_span = _span(
        span_id="q4" * 8,
        service_name="unknown_service",
        attributes={"messaging.operation.type": "send", "messaging.destination.name": "payment-q"},
    )
    batch = adapt(
        [client, server, queue_span],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
    )
    calls_facts = [f for f in batch.facts if f.relation_type == "CALLS"]
    assert len(calls_facts) == 1
    assert calls_facts[0].subject_id == "service:order-service"
    unknown_service_entities = [e for e in batch.entities if e.id == "service:unknown-service"]
    assert len(unknown_service_entities) == 1  # HTTP path still minted it, unaffected

    sends_facts = [f for f in batch.facts if f.relation_type == "SENDS"]
    assert sends_facts == []
    assert [u.reason for u in batch.unresolved] == [PLACEHOLDER_SERVICE_IDENTITY]


# --- v0.6.0 I2.1c: original CLIENT attribution carried through correlation ----------------------

_K1 = "7f3c2a10-1b2d-4e5f-8a9b-0c1d2e3f4a5b"
_P1 = "11111111-aaaa-4bbb-8ccc-000000000001"
_K8S = {
    "k8s_pod_uid": _P1,
    "k8s_cluster_uid": _K1,
    "k8s_namespace_name": "shop",
    "k8s_deployment_name": "orders",
}
_SERVER_END = datetime(2026, 8, 26, 12, 0, 2, tzinfo=UTC)  # differs from the CLIENT's 12:00:01


def _attributed_pair(client_k8s=None, *, server_k8s=None):
    """A CLIENT/SERVER pair whose two end times differ, so the fact time is distinguishable."""
    client, server = _client_server_pair(end_time=_SERVER_END, **(server_k8s or {}))
    return client.model_copy(update=(_K8S if client_k8s is None else client_k8s)), server


def _plain_pair():
    return _attributed_pair({})


def _strip_seed(facts):
    return [f.model_copy(update={"scoped_seed": None}) for f in facts]


def _seed_of(batch):
    [fact] = [f for f in batch.facts if f.relation_type == "CALLS"]
    return fact.scoped_seed


def _in_batch(client, server):
    return _correlate([client, server])


def _server_first(client, server):
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)
    return _correlate([client], correlation_buffer=buffer)


def _client_first(client, server):
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    return _correlate([server], correlation_buffer=buffer)


def _client_only(client, server):
    client = client.model_copy(
        update={
            "attributes": {
                "http.request.method": "GET",
                "http.route": "/products/{id}",
                "peer.service": "ProductService",
            }
        }
    )
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)
    _expire_client(buffer, client)
    return _correlate([], correlation_buffer=buffer)


PAIRING_PATHS = {
    "in-batch": _in_batch,
    "server-first cross-batch": _server_first,
    "client-first cross-batch": _client_first,
    "client-only expiry": _client_only,
}


def test_every_pairing_path_yields_the_same_seed_for_the_same_calls():
    seeds = {
        name: _seed_of(path(*_attributed_pair()))
        for name, path in PAIRING_PATHS.items()
        if name != "client-only expiry"
    }
    assert all(seed is not None for seed in seeds.values())
    assert len({seed.model_dump_json() for seed in seeds.values()}) == 1
    seed = seeds["in-batch"]
    assert seed.caller_pod_uid == _P1
    assert seed.caller_cluster_uid == _K1
    assert seed.k8s_namespace_name == "shop"
    assert seed.k8s_deployment_name == "orders"
    assert seed.subject_id == "service:order-service"
    assert seed.object_id == "operation:product-service:GET:/products/{id}"
    # The accepted fact time is the SERVER's; the CLIENT's earlier end time is not used.
    assert seed.fact_timestamp == _SERVER_END


def test_client_only_expiry_keeps_the_original_client_identity():
    batch = _client_only(*_attributed_pair())
    seed = _seed_of(batch)
    assert seed is not None
    assert seed.correlation_mode == "CLIENT_ONLY"
    assert (seed.caller_pod_uid, seed.caller_cluster_uid) == (_P1, _K1)
    assert seed.fact_timestamp == _attributed_pair()[0].end_time
    assert batch.scoped_refusals == []


@pytest.mark.parametrize("path", list(PAIRING_PATHS.values()), ids=list(PAIRING_PATHS))
def test_v1_output_is_identical_with_and_without_kubernetes_attributes(path):
    attributed = path(*_attributed_pair())
    plain = path(*_plain_pair())

    assert [f.scoped_seed is not None for f in attributed.facts] == [True]
    assert [f.scoped_seed for f in plain.facts] == [None]
    assert _strip_seed(attributed.facts) == _strip_seed(plain.facts)
    assert attributed.entities == plain.entities
    assert attributed.unresolved == plain.unresolved


@pytest.mark.parametrize("path", list(PAIRING_PATHS.values()), ids=list(PAIRING_PATHS))
def test_a_missing_pod_uid_refuses_the_seed_but_keeps_the_v1_fact(path):
    client_k8s = {**_K8S, "k8s_pod_uid": None}
    batch = path(*_attributed_pair(client_k8s))
    plain = path(*_plain_pair())

    assert len(batch.facts) == 1
    assert batch.facts[0].scoped_seed is None
    assert _strip_seed(batch.facts) == _strip_seed(plain.facts)
    [refusal] = batch.scoped_refusals
    assert refusal.reasons == ("LOCALITY_POD_UID_MISSING",)
    assert refusal.disposition == "INSUFFICIENT_EVIDENCE"
    assert refusal.v1_status == "unchanged"
    assert batch.unresolved == plain.unresolved


def test_server_resource_identity_never_stands_in_for_the_caller():
    client, server = _attributed_pair({}, server_k8s=_K8S)
    batch = _in_batch(client, server)

    assert batch.facts[0].scoped_seed is None
    assert [r.reasons for r in batch.scoped_refusals] == [
        ("LOCALITY_CLUSTER_UID_MISSING", "LOCALITY_POD_UID_MISSING")
    ]


def test_the_client_identity_is_used_even_when_the_server_carries_another():
    other = {"k8s_pod_uid": "22222222-bbbb-4ccc-8ddd-000000000002", "k8s_cluster_uid": "K-OTHER"}
    client, server = _attributed_pair(server_k8s=other)
    seed = _seed_of(_in_batch(client, server))

    assert (seed.caller_pod_uid, seed.caller_cluster_uid) == (_P1, _K1)


def test_a_pending_server_never_carries_kubernetes_identity():
    _, server = _attributed_pair(server_k8s=_K8S)
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)

    [(stored, _)] = buffer._pending_servers.values()
    assert stored.k8s_pod_uid is None and stored.k8s_cluster_uid is None


def test_a_waiting_client_keeps_only_its_own_admitted_identity():
    client, _ = _attributed_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([client], correlation_buffer=buffer)

    [(stored, _)] = buffer._pending_clients.values()
    assert (stored.k8s_pod_uid, stored.k8s_cluster_uid) == (_P1, _K1)
    assert stored.k8s_namespace_name == "shop"


def test_environment_and_day_mismatches_are_ingestion_refusals_with_v1_unchanged():
    client, server = _attributed_pair()
    # The paired fact's environment comes from the SERVER; a different CLIENT environment must not
    # change v1 but must refuse the seed.
    client = client.model_copy(update={"environment": "staging"})
    batch = _in_batch(client, server)

    assert len(batch.facts) == 1 and batch.facts[0].scoped_seed is None
    assert [r.reasons for r in batch.scoped_refusals] == [
        ("LOCALITY_CLIENT_FACT_ENVIRONMENT_MISMATCH",)
    ]
    assert batch.facts[0].environment == "production"


def test_a_cross_midnight_pair_keeps_its_v1_day_and_gets_no_seed():
    client, server = _attributed_pair()
    client = client.model_copy(update={"end_time": datetime(2026, 8, 27, 0, 0, 0, 100, tzinfo=UTC)})
    server = server.model_copy(
        update={"end_time": datetime(2026, 8, 26, 23, 59, 59, 999900, tzinfo=UTC)}
    )
    batch = _in_batch(client, server)

    [fact] = batch.facts
    assert fact.scoped_seed is None
    assert fact.evidence.bucket_start == datetime(2026, 8, 26, tzinfo=UTC)
    assert [r.reasons for r in batch.scoped_refusals] == [("LOCALITY_CLIENT_FACT_DAY_MISMATCH",)]
    assert batch.scoped_refusals[0].bucket_utc_day == "2026-08-26"


def test_server_only_is_recorded_as_a_refusal_and_never_a_seed():
    _, server = _attributed_pair(server_k8s=_K8S)
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)
    _expire_server(buffer, server)

    batch = _correlate([], correlation_buffer=buffer)

    assert batch.facts == []
    [refusal] = batch.scoped_refusals
    assert refusal.reasons == ("LOCALITY_SERVER_ONLY_NO_CLIENT",)
    assert refusal.v1_status == "none"


def test_a_size_evicted_client_is_never_localized_retroactively():
    client_a, server_a = _attributed_pair()
    client_b = client_a.model_copy(update={"trace_id": "c" * 32, "span_id": "d" * 16})
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=1)
    _correlate([client_a], correlation_buffer=buffer)
    _correlate([client_b], correlation_buffer=buffer)  # evicts client_a
    assert buffer.evictions == 1

    batch = _correlate([server_a], correlation_buffer=buffer)

    assert batch.facts == []
    assert batch.scoped_refusals == []


def test_no_seed_is_attached_without_a_calls_fact():
    client, server = _attributed_pair()
    server = server.model_copy(update={"attributes": {}})  # no method/route: NO_STABLE_ROUTE
    batch = _in_batch(client, server)

    assert batch.facts == []
    assert batch.scoped_refusals == []
    assert [u.reason for u in batch.unresolved] == [NO_STABLE_ROUTE]


def test_adapt_returns_the_ingestion_refusals():
    _, server = _attributed_pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    _correlate([server], correlation_buffer=buffer)
    _expire_server(buffer, server)

    batch = adapt(
        [],
        service_candidates=SERVICE_CANDIDATES,
        operation_candidates=OPERATION_CANDIDATES,
        queue_candidates=QUEUE_CANDIDATES,
        service_aliases={},
        queue_aliases={},
        correlation_buffer=buffer,
    )

    assert [r.reasons for r in batch.scoped_refusals] == [("LOCALITY_SERVER_ONLY_NO_CLIENT",)]


def test_the_seed_is_not_part_of_the_persisted_v1_evidence():
    batch = _in_batch(*_attributed_pair())
    [fact] = batch.facts

    assert fact.scoped_seed is not None
    assert "scoped_seed" not in fact.evidence.model_dump()
    assert not any(
        key.startswith(("k8s", "caller", "scoped")) for key in fact.evidence.model_dump()
    )
