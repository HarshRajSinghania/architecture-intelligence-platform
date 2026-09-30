"""The resolve-and-persist half of OTLP trace ingestion (spec §8, §36): given already-decoded spans,
read the declared candidates each span can resolve against, adapt the spans into an observation
batch, and persist it.

Moved out of `app.api.telemetry` so the route only validates and decodes the HTTP request.
"""

import neo4j

from app.graph.repository import open_session
from app.settings import TelemetryConfig
from app.telemetry.adapter import adapt
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.telemetry.model import RuntimeSpan
from app.telemetry.operation_resolver import fetch_operation_candidates
from app.telemetry.pubsub_resolver import fetch_subscription_candidates, fetch_topic_candidates
from app.telemetry.queue_resolver import fetch_queue_candidates
from app.telemetry.service_resolver import fetch_candidates


def ingest_trace_spans(
    spans: list[RuntimeSpan],
    *,
    driver: neo4j.Driver,
    database: str,
    telemetry: TelemetryConfig,
    correlation_buffer: HttpCorrelationBuffer | None,
) -> None:
    with open_session(driver, database=database, read_only=True) as session:
        service_candidates = fetch_candidates(session)
        operation_candidates = fetch_operation_candidates(session)
        queue_candidates = fetch_queue_candidates(session)
        topic_candidates = fetch_topic_candidates(session)
        subscription_candidates = fetch_subscription_candidates(session)

    batch = adapt(
        spans,
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        queue_candidates=queue_candidates,
        service_aliases=telemetry.service_aliases,
        queue_aliases=telemetry.queue_aliases,
        correlation_buffer=correlation_buffer,
        topic_candidates=topic_candidates,
        subscription_candidates=subscription_candidates,
        topic_aliases=telemetry.topic_aliases,
    )
    persist_observation_batch(driver, database, batch, scoped=telemetry.scoped_evidence)
