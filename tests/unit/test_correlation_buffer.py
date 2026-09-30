from datetime import UTC, datetime, timedelta

from app.telemetry.correlation_buffer import HttpCorrelationBuffer, PendingHttpSpan


def _pending(**overrides) -> PendingHttpSpan:
    defaults = {
        "trace_id": "a" * 32,
        "span_id": "b" * 16,
        "parent_span_id": None,
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "service_namespace": None,
        "service_version": None,
        "environment": "production",
        "method": None,
        "route": None,
        "timestamp": datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return PendingHttpSpan(**defaults)


def test_offer_server_then_offer_client_matches():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        service_name="ProductService",
        environment="production",
        method="GET",
        route="/products/{id}",
    )
    client = _pending(span_kind="CLIENT", span_id="c" * 16, service_name="OrderService")

    assert buffer.offer_server(server) is None
    matched = buffer.offer_client(client)

    assert matched is not None
    assert matched.service_name == "ProductService"
    assert buffer.cross_batch_matches == 1


def test_offer_client_then_offer_server_matches():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16, service_name="OrderService")
    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        service_name="ProductService",
        environment="production",
        method="GET",
        route="/products/{id}",
    )

    assert buffer.offer_client(client) is None
    matched = buffer.offer_server(server)

    assert matched is not None
    assert matched.service_name == "OrderService"
    assert buffer.cross_batch_matches == 1


def test_different_trace_ids_never_match():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16, trace_id="a" * 32)
    server = _pending(
        span_kind="SERVER", parent_span_id="c" * 16, trace_id="z" * 32, environment="production"
    )

    assert buffer.offer_client(client) is None
    assert buffer.offer_server(server) is None
    assert buffer.cross_batch_matches == 0


def test_server_with_no_parent_span_id_is_never_buffered_or_matched():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    server = _pending(span_kind="SERVER", parent_span_id=None, environment="production")
    assert buffer.offer_server(server) is None
    # Nothing was buffered for it, so an otherwise-matching client still finds no counterpart.
    client = _pending(span_kind="CLIENT", span_id="c" * 16)
    assert buffer.offer_client(client) is None


def test_ttl_expiry_removes_a_stale_pending_entry():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    client = _pending(span_kind="CLIENT", span_id="c" * 16)
    assert buffer.offer_client(client) is None

    # Simulate time passing beyond the TTL by directly rewriting the stored insertion timestamp -
    # the buffer has no clock injection point, and this keeps the test deterministic and fast.
    key = (client.trace_id, client.span_id)
    stored_span, _ = buffer._pending_clients[key]
    buffer._pending_clients[key] = (stored_span, datetime.now(UTC) - timedelta(seconds=120))

    server = _pending(
        span_kind="SERVER",
        parent_span_id="c" * 16,
        environment="production",
        method="GET",
        route="/x",
    )
    matched = buffer.offer_server(server)

    assert matched is None
    assert buffer.expirations >= 1


def test_max_pending_spans_evicts_the_oldest_entry():
    buffer = HttpCorrelationBuffer(ttl_seconds=3600, max_pending_spans=2)
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="1" * 16, trace_id="a" * 32))
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="2" * 16, trace_id="a" * 32))
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="3" * 16, trace_id="a" * 32))

    assert len(buffer._pending_clients) == 2
    assert buffer.evictions == 1
    # The oldest (span_id "1"...) was evicted - a server matching it now finds nothing.
    evicted_server = _pending(
        span_kind="SERVER",
        parent_span_id="1" * 16,
        trace_id="a" * 32,
        environment="production",
        method="GET",
        route="/x",
    )
    assert buffer.offer_server(evicted_server) is None
    # The two most recent (span_id "2"/"3") are still present.
    surviving_server = _pending(
        span_kind="SERVER",
        parent_span_id="3" * 16,
        trace_id="a" * 32,
        environment="production",
        method="GET",
        route="/x",
    )
    assert buffer.offer_server(surviving_server) is not None


# --- sweep_expired (11H-C) -----------------------------------------------------------------------


def _expire(buffer, store_name: str, key: tuple[str, str]) -> None:
    store = getattr(buffer, store_name)
    stored_span, _ = store[key]
    store[key] = (stored_span, datetime.now(UTC) - timedelta(seconds=120))


def test_sweep_expired_returns_and_clears_only_genuinely_expired_entries():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    stale_client = _pending(span_kind="CLIENT", span_id="1" * 16, trace_id="a" * 32)
    fresh_client = _pending(span_kind="CLIENT", span_id="2" * 16, trace_id="a" * 32)
    buffer.offer_client(stale_client)
    buffer.offer_client(fresh_client)
    _expire(buffer, "_pending_clients", ("a" * 32, "1" * 16))

    expired_clients, expired_servers = buffer.sweep_expired()

    assert [c.span_id for c in expired_clients] == ["1" * 16]
    assert expired_servers == []
    # The fresh entry is untouched and still matchable.
    server = _pending(
        span_kind="SERVER",
        parent_span_id="2" * 16,
        trace_id="a" * 32,
        environment="production",
        method="GET",
        route="/x",
    )
    assert buffer.offer_server(server) is not None


def test_sweep_expired_is_idempotent():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="1" * 16, trace_id="a" * 32))
    _expire(buffer, "_pending_clients", ("a" * 32, "1" * 16))

    first_clients, _ = buffer.sweep_expired()
    second_clients, _ = buffer.sweep_expired()

    assert len(first_clients) == 1
    assert second_clients == []


def test_sweep_expired_reports_both_clients_and_servers():
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10)
    buffer.offer_client(_pending(span_kind="CLIENT", span_id="1" * 16, trace_id="a" * 32))
    buffer.offer_server(
        _pending(
            span_kind="SERVER",
            parent_span_id="2" * 16,
            trace_id="b" * 32,
            environment="production",
            method="GET",
            route="/x",
        )
    )
    _expire(buffer, "_pending_clients", ("a" * 32, "1" * 16))
    _expire(buffer, "_pending_servers", ("b" * 32, "2" * 16))

    expired_clients, expired_servers = buffer.sweep_expired()

    assert len(expired_clients) == 1
    assert len(expired_servers) == 1


def test_max_pending_spans_logs_count_only_warning(caplog):
    buffer = HttpCorrelationBuffer(ttl_seconds=3600, max_pending_spans=1)
    first = _pending(
        span_kind="CLIENT",
        span_id="1" * 16,
        trace_id="a" * 32,
        service_name="SensitiveServiceName",
        route="/private/path",
    )
    second = _pending(
        span_kind="CLIENT",
        span_id="2" * 16,
        trace_id="a" * 32,
        service_name="AnotherSensitiveService",
        route="/another/private/path",
    )

    buffer.offer_client(first)
    with caplog.at_level("WARNING", logger="app.telemetry.correlation_buffer"):
        buffer.offer_client(second)

    assert buffer.evictions == 1
    assert len(buffer._pending_clients) == 1
    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == "HTTP correlation buffer size eviction count=1"
    assert "SensitiveServiceName" not in caplog.text
    assert "AnotherSensitiveService" not in caplog.text
    assert "/private/path" not in caplog.text
