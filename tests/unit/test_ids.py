from datetime import UTC, datetime

from app.canonical.ids import (
    evidence_id,
    message_id,
    observed_evidence_id,
    operation_id,
    queue_id,
    runtime_identity_observation_id,
    schema_id,
    service_id,
)


def test_service_id_matches_spec_example():
    assert service_id("order-service") == "service:order-service"


def test_service_id_without_namespace():
    assert service_id("fraud-service") == "service:fraud-service"


def test_service_id_with_namespace():
    assert service_id("fraud-service", namespace="commerce") == "service:commerce:fraud-service"


def test_operation_id_matches_spec_example():
    assert (
        operation_id("product-service", "GET", "/products/{id}")
        == "operation:product-service:GET:/products/{id}"
    )


def test_operation_id_normalizes_method_case():
    assert operation_id("product-service", "get", "/products/{id}") == operation_id(
        "product-service", "GET", "/products/{id}"
    )


def test_queue_id_matches_spec_example_with_namespace():
    assert queue_id("payment-q", namespace="asb:commerce") == "queue:asb:commerce:payment-q"


def test_queue_id_without_namespace():
    assert queue_id("payment-q") == "queue:payment-q"


def test_message_id_matches_spec_example():
    assert message_id("PaymentRequested", "v2") == "message:PaymentRequested:v2"


def test_message_id_without_version():
    assert message_id("PaymentRequested") == "message:PaymentRequested"


def test_schema_id_matches_spec_example():
    assert schema_id("PaymentRequested", "v2") == "schema:PaymentRequested:v2"


def test_evidence_id_without_revision():
    assert evidence_id("ASYNCAPI", "order-service") == "evidence:asyncapi:order-service"


def test_evidence_id_with_revision():
    assert (
        evidence_id("ASYNCAPI", "order-service", "abc123")
        == "evidence:asyncapi:order-service:abc123"
    )


def test_evidence_id_lowercases_source_type():
    assert evidence_id("MANIFEST", "order-service") == "evidence:manifest:order-service"


def test_evidence_id_changes_when_revision_changes():
    assert evidence_id("OPENAPI", "order-service", "abc123") != evidence_id(
        "OPENAPI", "order-service", "def456"
    )


def test_observed_evidence_id_is_deterministic():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    assert observed_evidence_id(
        "production", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    ) == observed_evidence_id(
        "production", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    )


def test_observed_evidence_id_matches_spec_example_shape():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    result = observed_evidence_id(
        "production", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    )
    assert result.startswith("evidence:otel:production:2026-08-26:")


def test_observed_evidence_id_changes_with_different_fact():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    a = observed_evidence_id(
        "production", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    )
    b = observed_evidence_id(
        "production", bucket_start, "service:payment-service", "CALLS", "operation:x:GET:/y"
    )
    assert a != b


def test_observed_evidence_id_changes_with_different_environment_or_day():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    other_day = datetime(2026, 8, 27, tzinfo=UTC)
    base = observed_evidence_id(
        "production", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    )
    diff_env = observed_evidence_id(
        "staging", bucket_start, "service:order-service", "CALLS", "operation:x:GET:/y"
    )
    diff_day = observed_evidence_id(
        "production", other_day, "service:order-service", "CALLS", "operation:x:GET:/y"
    )
    assert base != diff_env
    assert base != diff_day


def test_ids_are_deterministic_across_calls():
    assert service_id("order-service") == service_id("order-service")
    assert operation_id("product-service", "GET", "/products/{id}") == operation_id(
        "product-service", "GET", "/products/{id}"
    )


def test_observed_evidence_id_pins_full_golden_value():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)
    # printf '%s' 'service:orders|CALLS|operation:pricing:GET:/prices' | sha256sum
    assert (
        observed_evidence_id(
            "production",
            bucket_start,
            "service:orders",
            "CALLS",
            "operation:pricing:GET:/prices",
        )
        == "evidence:otel:production:2026-08-26:47a491ddd2fc"
    )


def test_runtime_identity_observation_id_pins_namespace_and_pod_values():
    bucket_start = datetime(2026, 8, 26, tzinfo=UTC)

    # printf '%s' 'orders||pod-123' | sha256sum
    assert (
        runtime_identity_observation_id(
            environment="production",
            bucket_start=bucket_start,
            service_name="orders",
            service_namespace=None,
            k8s_pod_uid="pod-123",
        )
        == "runtime-identity:otel:production:2026-08-26:0b89a71d5b49"
    )

    # printf '%s' 'orders|commerce|pod-123' | sha256sum
    assert (
        runtime_identity_observation_id(
            environment="production",
            bucket_start=bucket_start,
            service_name="orders",
            service_namespace="commerce",
            k8s_pod_uid="pod-123",
        )
        == "runtime-identity:otel:production:2026-08-26:88409f733833"
    )

    # printf '%s' 'orders||pod-456' | sha256sum
    assert (
        runtime_identity_observation_id(
            environment="production",
            bucket_start=bucket_start,
            service_name="orders",
            service_namespace=None,
            k8s_pod_uid="pod-456",
        )
        == "runtime-identity:otel:production:2026-08-26:ba5066c11f30"
    )


def test_runtime_identity_observation_id_pins_environment_and_day():
    # The identity seed is unchanged; environment/day are explicit ID components.
    assert (
        runtime_identity_observation_id(
            environment="staging",
            bucket_start=datetime(2026, 8, 27, tzinfo=UTC),
            service_name="orders",
            service_namespace=None,
            k8s_pod_uid="pod-123",
        )
        == "runtime-identity:otel:staging:2026-08-27:0b89a71d5b49"
    )
