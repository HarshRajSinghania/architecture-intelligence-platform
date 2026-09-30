import shutil
import tempfile
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)
from opentelemetry.proto.common.v1.common_pb2 import AnyValue, KeyValue
from opentelemetry.proto.resource.v1.resource_pb2 import Resource
from opentelemetry.proto.trace.v1.trace_pb2 import ResourceSpans, ScopeSpans, Span

from app.canonical import ids
from app.graph.importer import import_all_sources
from app.main import create_app
from app.settings import AppConfig, Secrets, Settings
from app.sources.model import FilesystemSourceConfig
from app.telemetry.correlation_buffer import HttpCorrelationBuffer

EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
DATABASE = "neo4j"
_CONTENT_TYPE = "application/x-protobuf"
_SOURCE_ID = "test-telemetry-api-examples"
# A writable staging copy, not the real examples/ tree directly: one test below mutates a declared
# document in place and reimports it to prove reconciliation - reusing the same configured source
# id and physical root across both imports keeps SourceInstanceId/scope_definition_digest stable
# (I1 spec §5.1/§6), exactly like evaluation/fixture_setup.py's staging pattern.
_STAGING_ROOT = Path(tempfile.gettempdir()) / "aip-test-telemetry-api-examples"


@pytest.fixture(scope="module", autouse=True)
def populated_graph(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
    if _STAGING_ROOT.exists():
        shutil.rmtree(_STAGING_ROOT)
    shutil.copytree(EXAMPLES_DIR, _STAGING_ROOT)
    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id=_SOURCE_ID, root=_STAGING_ROOT),
    )


@pytest.fixture
def session(driver):
    with driver.session(database=DATABASE) as s:
        yield s


def _build_app(driver, *, telemetry: dict | None = None):
    app = create_app()
    app.state.driver = driver
    app.state.settings = Settings(
        config=AppConfig.model_validate(
            {
                "sources": {
                    "directories": [
                        {
                            "id": "aip-bundled-examples-v0.5",
                            "root": str(EXAMPLES_DIR),
                            "stable_target_identity": "urn:aip:logical-root:bundled-examples",
                        }
                    ]
                },
                "graph": {"uri": "bolt://ignored:7687", "database": DATABASE},
                **({"telemetry": telemetry} if telemetry else {}),
            }
        ),
        secrets=Secrets(neo4j_user="neo4j", neo4j_password="ignored"),
    )
    return app


@pytest.fixture
def client(driver):
    return TestClient(_build_app(driver))


_CLIENT_SPAN_ID = bytes.fromhex("b7ad6b7169203331")
_SERVER_SPAN_ID = bytes.fromhex("00f067aa0ba902b7")
_TRACE_ID = bytes.fromhex("4bf92f3577b34da6a3ce929d0e0e4736")


def _client_resource_spans(*, client_service: str, method: str, route: str) -> ResourceSpans:
    resource = Resource(
        attributes=[KeyValue(key="service.name", value=AnyValue(string_value=client_service))]
    )
    span = Span(
        trace_id=_TRACE_ID,
        span_id=_CLIENT_SPAN_ID,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_000_050_000_000,
    )
    return ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])


def _server_resource_spans(*, server_service: str, method: str, route: str) -> ResourceSpans:
    resource = Resource(
        attributes=[
            KeyValue(key="service.name", value=AnyValue(string_value=server_service)),
            KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production")),
        ]
    )
    span = Span(
        trace_id=_TRACE_ID,
        span_id=_SERVER_SPAN_ID,
        parent_span_id=_CLIENT_SPAN_ID,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=1_700_000_000_010_000_000,
        end_time_unix_nano=1_700_000_000_040_000_000,
        attributes=[
            KeyValue(key="http.request.method", value=AnyValue(string_value=method)),
            KeyValue(key="http.route", value=AnyValue(string_value=route)),
        ],
    )
    return ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])


def _resource_spans(*, client_service: str, server_service: str, method: str, route: str) -> bytes:
    request = ExportTraceServiceRequest(
        resource_spans=[
            _client_resource_spans(client_service=client_service, method=method, route=route),
            _server_resource_spans(server_service=server_service, method=method, route=route),
        ]
    )
    return request.SerializeToString()


def test_valid_payload_persists_an_observed_call_and_returns_200(client, session):
    payload = _resource_spans(
        client_service="OrderService",
        server_service="ProductService",
        method="GET",
        route="/products/{id}",
    )

    response = client.post("/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE})
    assert response.status_code == 200
    assert response.headers["content-type"] == _CONTENT_TYPE

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("product-service"), "GET", "/products/{id}")
    record = session.run(
        "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN r.evidence_ids AS ids",
        subject_id=subject_id,
        object_id=object_id,
    ).single()
    assert record is not None
    assert len(record["ids"]) >= 1

    evidence_id = record["ids"][-1]
    evidence = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
        "e.evidence_type AS evidence_type, e.environment AS environment",
        id=evidence_id,
    ).single()
    assert evidence["source_type"] == "OPENTELEMETRY"
    assert evidence["evidence_type"] == "OBSERVED"
    assert evidence["environment"] == "production"


# --- I3 §9.4/§23 slice 2: runtime identity evidence survives OTLP -> persistence -------------------


def _server_resource_spans_with_k8s_identity(
    *, server_service: str, method: str, route: str, k8s_pod_uid: str
) -> ResourceSpans:
    resource = Resource(
        attributes=[
            KeyValue(key="service.name", value=AnyValue(string_value=server_service)),
            KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production")),
            KeyValue(key="k8s.pod.uid", value=AnyValue(string_value=k8s_pod_uid)),
            KeyValue(
                key="k8s.pod.name", value=AnyValue(string_value=f"{server_service.lower()}-abcde")
            ),
        ]
    )
    span = Span(
        trace_id=_TRACE_ID,
        span_id=_SERVER_SPAN_ID,
        parent_span_id=_CLIENT_SPAN_ID,
        name=f"{method} {route}",
        kind=Span.SPAN_KIND_SERVER,
        start_time_unix_nano=1_700_000_000_010_000_000,
        end_time_unix_nano=1_700_000_000_040_000_000,
        attributes=[
            KeyValue(key="http.request.method", value=AnyValue(string_value=method)),
            KeyValue(key="http.route", value=AnyValue(string_value=route)),
        ],
    )
    return ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])


def test_a_k8s_identified_payload_persists_a_runtime_identity_observation(client, session):
    payload = ExportTraceServiceRequest(
        resource_spans=[
            _client_resource_spans(
                client_service="OrderService", method="GET", route="/k8s-identity-test/{id}"
            ),
            _server_resource_spans_with_k8s_identity(
                server_service="ProductService",
                method="GET",
                route="/k8s-identity-test/{id}",
                k8s_pod_uid="pod-uid-e2e-1",
            ),
        ]
    ).SerializeToString()

    response = client.post("/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE})
    assert response.status_code == 200
    assert response.content == ExportTraceServiceResponse().SerializeToString()

    record = session.run(
        "MATCH (o:RuntimeIdentityObservation) WHERE o.k8s_pod_uid = $pod_uid "
        "RETURN o.service_name AS service_name, o.environment AS environment, "
        "o.k8s_pod_name AS k8s_pod_name",
        pod_uid="pod-uid-e2e-1",
    ).single()
    assert record is not None
    assert record["service_name"] == "ProductService"
    assert record["environment"] == "production"
    assert record["k8s_pod_name"] == "productservice-abcde"


def _build_app_with_correlation_buffer(driver):
    app = _build_app(driver)
    app.state.http_correlation_buffer = HttpCorrelationBuffer(
        ttl_seconds=60, max_pending_spans=10000
    )
    return app


@pytest.fixture
def client_with_correlation_buffer(driver):
    return TestClient(_build_app_with_correlation_buffer(driver))


def test_cross_batch_client_and_server_in_separate_requests_produce_one_calls_relation(
    client_with_correlation_buffer, session
):
    # 11H-B / I2: a CLIENT span delivered in one POST /v1/traces and its matching SERVER span
    # delivered in a later, separate POST must still produce exactly one CALLS relation. Targets
    # an undeclared ReviewService/route, distinct from the module's other test's declared
    # order-service -> product-service relation, since this module has no per-test Neo4j reset.
    client_only = ExportTraceServiceRequest(
        resource_spans=[
            _client_resource_spans(
                client_service="OrderService", method="GET", route="/reviews/{id}"
            )
        ]
    ).SerializeToString()
    server_only = ExportTraceServiceRequest(
        resource_spans=[
            _server_resource_spans(
                server_service="ReviewService", method="GET", route="/reviews/{id}"
            )
        ]
    ).SerializeToString()

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("reviewservice"), "GET", "/reviews/{id}")
    count_query = "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN count(r) AS c"

    response_a = client_with_correlation_buffer.post(
        "/v1/traces", content=client_only, headers={"content-type": _CONTENT_TYPE}
    )
    assert response_a.status_code == 200
    assert session.run(count_query, subject_id=subject_id, object_id=object_id).single()["c"] == 0

    response_b = client_with_correlation_buffer.post(
        "/v1/traces", content=server_only, headers={"content-type": _CONTENT_TYPE}
    )
    assert response_b.status_code == 200
    assert session.run(count_query, subject_id=subject_id, object_id=object_id).single()["c"] == 1


def _build_app_with_short_ttl_correlation_buffer(driver):
    app = _build_app(driver)
    app.state.http_correlation_buffer = HttpCorrelationBuffer(
        ttl_seconds=1, max_pending_spans=10000
    )
    return app


@pytest.fixture
def client_with_short_ttl_buffer(driver):
    return TestClient(_build_app_with_short_ttl_correlation_buffer(driver))


def test_client_only_observation_produces_a_calls_relation_after_ttl_expiry(
    client_with_short_ttl_buffer, session
):
    # 11H-C / I3: a CLIENT span with a stable target identity (peer.service) and no SERVER span
    # ever arriving must still, once its TTL expires, produce an observed CALLS candidate.
    client_span_id = bytes.fromhex("aa11bb22cc33dd44")
    trace_id = bytes.fromhex("5cf93f3577b34da6a3ce929d0e0e4737")
    resource = Resource(
        attributes=[
            KeyValue(key="service.name", value=AnyValue(string_value="OrderService")),
            KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production")),
        ]
    )
    span = Span(
        trace_id=trace_id,
        span_id=client_span_id,
        name="GET /catalog/{id}",
        kind=Span.SPAN_KIND_CLIENT,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_000_050_000_000,
        attributes=[
            KeyValue(key="http.request.method", value=AnyValue(string_value="GET")),
            KeyValue(key="http.route", value=AnyValue(string_value="/catalog/{id}")),
            KeyValue(key="peer.service", value=AnyValue(string_value="CatalogService")),
        ],
    )
    payload = ExportTraceServiceRequest(
        resource_spans=[ResourceSpans(resource=resource, scope_spans=[ScopeSpans(spans=[span])])]
    ).SerializeToString()

    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("catalogservice"), "GET", "/catalog/{id}")
    count_query = "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN count(r) AS c"

    response_a = client_with_short_ttl_buffer.post(
        "/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE}
    )
    assert response_a.status_code == 200
    assert session.run(count_query, subject_id=subject_id, object_id=object_id).single()["c"] == 0

    time.sleep(1.2)  # past the 1-second TTL

    # Any subsequent POST triggers the buffer's sweep_expired() - an empty/unrelated batch is
    # enough (spec §17/11H-C: nothing about this second request itself needs to reference the
    # expired CLIENT span).
    empty_response = client_with_short_ttl_buffer.post(
        "/v1/traces",
        content=ExportTraceServiceRequest().SerializeToString(),
        headers={"content-type": _CONTENT_TYPE},
    )
    assert empty_response.status_code == 200

    record = session.run(
        "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) RETURN r.evidence_ids AS ids",
        subject_id=subject_id,
        object_id=object_id,
    ).single()
    assert record is not None
    evidence = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.correlation_mode AS correlation_mode",
        id=record["ids"][-1],
    ).single()
    assert evidence["correlation_mode"] == "CLIENT_ONLY"


# --- 11H-D: observed PROVIDES relation for runtime-discovered operations ------------------------


def test_undeclared_route_on_a_known_provider_gets_an_observed_provides_relation(client, session):
    # I4: ProductService is a real declared service, but /internal/products/{id} is not a
    # declared route - the runtime-minted Operation must carry OBSERVED_ONLY discovery_status
    # and an observed PROVIDES edge from ProductService, not just the CALLS edge to it.
    payload = _resource_spans(
        client_service="OrderService",
        server_service="ProductService",
        method="GET",
        route="/internal/products/{id}",
    )
    response = client.post("/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE})
    assert response.status_code == 200

    provider_id = ids.service_id("product-service")
    operation_id = ids.operation_id(provider_id, "GET", "/internal/products/{id}")

    operation_record = session.run(
        "MATCH (o:Operation {id: $id}) RETURN o.discovery_status AS discovery_status",
        id=operation_id,
    ).single()
    assert operation_record is not None
    assert operation_record["discovery_status"] == "OBSERVED_ONLY"

    provides_record = session.run(
        "MATCH (s:Service {id: $provider_id})-[r:PROVIDES]->(o:Operation {id: $operation_id}) "
        "RETURN r.evidence_ids AS evidence_ids",
        provider_id=provider_id,
        operation_id=operation_id,
    ).single()
    assert provides_record is not None
    assert len(provides_record["evidence_ids"]) == 1

    evidence = session.run(
        "MATCH (e:Evidence {id: $id}) RETURN e.source_type AS source_type, "
        "e.evidence_type AS evidence_type",
        id=provides_record["evidence_ids"][0],
    ).single()
    assert evidence["source_type"] == "OPENTELEMETRY"
    assert evidence["evidence_type"] == "OBSERVED"


def test_later_declaring_an_observed_only_operation_reconciles_without_duplication(
    client, session, driver
):
    # I5: run the same undeclared-route observation as I4, then import a real OpenAPI document
    # that declares that exact method+path for the same service. Reconciliation must land on the
    # SAME Operation node (11H-D/spec §8.4) - this is exactly the id-normalization fix's target:
    # without it, the declared import would mint a second, disconnected node.
    payload = _resource_spans(
        client_service="OrderService",
        server_service="ProductService",
        method="GET",
        route="/internal/products2/{id}",
    )
    response = client.post("/v1/traces", content=payload, headers={"content-type": _CONTENT_TYPE})
    assert response.status_code == 200

    provider_id = ids.service_id("product-service")
    operation_id = ids.operation_id(provider_id, "GET", "/internal/products2/{id}")

    openapi_path = _STAGING_ROOT / "product-service" / "openapi.yaml"
    document = yaml.safe_load(openapi_path.read_text())
    document["paths"]["/internal/products2/{id}"] = {
        "get": {
            "operationId": "getInternalProduct2",
            "responses": {"200": {"content": {"application/json": {"schema": {}}}}},
        }
    }
    openapi_path.write_text(yaml.safe_dump(document))

    import_all_sources(
        driver,
        database=DATABASE,
        source_config=FilesystemSourceConfig(id=_SOURCE_ID, root=_STAGING_ROOT),
    )

    count = session.run(
        "MATCH (o:Operation {id: $id}) RETURN count(o) AS c", id=operation_id
    ).single()["c"]
    assert count == 1

    evidence_types = session.run(
        "MATCH (s:Service {id: $provider_id})-[r:PROVIDES]->(o:Operation {id: $operation_id}) "
        "UNWIND r.evidence_ids AS eid "
        "MATCH (e:Evidence {id: eid}) "
        "RETURN collect(DISTINCT e.evidence_type) AS types",
        provider_id=provider_id,
        operation_id=operation_id,
    ).single()["types"]
    assert set(evidence_types) == {"DECLARED", "OBSERVED"}


# --- v0.6.0 I2.1c: attributed CLIENT identity must not change persisted v1 state -----------------

_K1 = "7f3c2a10-1b2d-4e5f-8a9b-0c1d2e3f4a5b"
_P1 = "11111111-aaaa-4bbb-8ccc-000000000001"


def _attributed_client_resource_spans(*, client_service: str, method: str, route: str):
    resource_spans = _client_resource_spans(
        client_service=client_service, method=method, route=route
    )
    resource_spans.resource.attributes.extend(
        [
            KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production")),
            KeyValue(key="k8s.pod.uid", value=AnyValue(string_value=_P1)),
            KeyValue(key="k8s.cluster.uid", value=AnyValue(string_value=_K1)),
            KeyValue(key="k8s.namespace.name", value=AnyValue(string_value="shop")),
            KeyValue(key="k8s.deployment.name", value=AnyValue(string_value="orders")),
        ]
    )
    return resource_spans


def _plain_client_resource_spans(*, client_service: str, method: str, route: str):
    resource_spans = _client_resource_spans(
        client_service=client_service, method=method, route=route
    )
    resource_spans.resource.attributes.append(
        KeyValue(key="deployment.environment.name", value=AnyValue(string_value="production"))
    )
    return resource_spans


def _post_client_then_server(client_app, *, client_spans, route: str) -> None:
    for resource_spans in (
        client_spans,
        _server_resource_spans(server_service="ReviewService", method="GET", route=route),
    ):
        body = ExportTraceServiceRequest(resource_spans=[resource_spans]).SerializeToString()
        response = client_app.post(
            "/v1/traces", content=body, headers={"content-type": _CONTENT_TYPE}
        )
        assert response.status_code == 200


_EVIDENCE_FOR_CALL = (
    "MATCH (a {id: $subject_id})-[r:CALLS]->(b {id: $object_id}) "
    "UNWIND r.evidence_ids AS eid MATCH (e:Evidence {id: eid}) RETURN properties(e) AS props"
)


def _calls_evidence(session, route: str) -> dict:
    subject_id = ids.service_id("order-service")
    object_id = ids.operation_id(ids.service_id("reviewservice"), "GET", route)
    [record] = session.run(_EVIDENCE_FOR_CALL, subject_id=subject_id, object_id=object_id)
    return dict(record["props"])


def test_an_attributed_client_leaves_persisted_v1_evidence_identical_to_an_unattributed_one(
    client_with_correlation_buffer, session
):
    # Two identical cross-batch calls that differ only in whether the CLIENT Resource carries
    # Kubernetes identity (and in the route, which only changes the operation id). Their persisted
    # v1 evidence must be equal apart from the id, and no scoped node may exist anywhere.
    attributed_route, plain_route = "/reviews-attributed/{id}", "/reviews-plain/{id}"
    _post_client_then_server(
        client_with_correlation_buffer,
        client_spans=_attributed_client_resource_spans(
            client_service="OrderService", method="GET", route=attributed_route
        ),
        route=attributed_route,
    )
    _post_client_then_server(
        client_with_correlation_buffer,
        client_spans=_plain_client_resource_spans(
            client_service="OrderService", method="GET", route=plain_route
        ),
        route=plain_route,
    )

    attributed = _calls_evidence(session, attributed_route)
    plain = _calls_evidence(session, plain_route)
    attributed.pop("id")
    plain.pop("id")

    assert attributed == plain
    assert not any(key.startswith(("k8s", "caller", "scoped")) for key in attributed)

    scoped_nodes = session.run(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'Scoped') "
        "OR (n.id IS NOT NULL AND n.id STARTS WITH 'evidence:otel:calls-scoped') "
        "RETURN count(n) AS c"
    ).single()
    assert scoped_nodes is not None and scoped_nodes["c"] == 0


def _post_attributed_cross_batch(app_client, *, route: str) -> None:
    _post_client_then_server(
        app_client,
        client_spans=_attributed_client_resource_spans(
            client_service="OrderService", method="GET", route=route
        ),
        route=route,
    )


def test_the_endpoint_writes_a_v2_record_only_when_scoped_evidence_is_enabled(driver, session):
    # v0.6.0 I2.2b, end to end through POST /v1/traces: an attributed CLIENT plus its SERVER in a
    # later POST. Disabled (the default) leaves no v2 node; enabled writes exactly one, isolated.
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)
    disabled_app = _build_app(driver)
    disabled_app.state.http_correlation_buffer = buffer
    _post_attributed_cross_batch(TestClient(disabled_app), route="/reviews-scoped-off/{id}")
    assert session.run("MATCH (v:ScopedObservedCallV2) RETURN count(v) AS c").single()["c"] == 0

    enabled_app = _build_app(
        driver, telemetry={"scoped-evidence": {"enabled": True, "stream-id": "test-stream"}}
    )
    enabled_app.state.http_correlation_buffer = HttpCorrelationBuffer(
        ttl_seconds=60, max_pending_spans=10000
    )
    _post_attributed_cross_batch(TestClient(enabled_app), route="/reviews-scoped-on/{id}")

    try:
        [row] = session.run(
            "MATCH (v:ScopedObservedCallV2) RETURN v.caller_pod_uid AS pod, "
            "v.caller_cluster_uid AS cluster, v.k8s_namespace_name AS ns, "
            "v.observation_count AS n, COUNT { (v)--() } AS degree"
        )
        assert (row["pod"], row["cluster"], row["ns"], row["n"], row["degree"]) == (
            _P1,
            _K1,
            "shop",
            1,
            0,
        )
    finally:
        # This module shares one graph, and an earlier test asserts no scoped node exists.
        session.run("MATCH (v:ScopedObservedCallV2) DETACH DELETE v").consume()
