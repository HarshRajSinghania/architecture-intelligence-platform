from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from app.canonical import ids
from app.provenance.model import ObservedEvidence
from app.telemetry.correlation_buffer import HttpCorrelationBuffer, PendingHttpSpan
from app.telemetry.messaging_guards import (
    PubSubDecision,
    decide_messaging_destination,
    decide_service_identity,
)
from app.telemetry.model import (
    DiscoveryStatus,
    ObservationBatch,
    ObservedFactCandidate,
    ObservedOnlyEntity,
    RuntimeSpan,
    UnresolvedObservation,
    day_bucket,
)
from app.telemetry.operation_resolver import DeclaredOperationCandidate, resolve_operation
from app.telemetry.pubsub_resolver import DeclaredSubscriptionCandidate, DeclaredTopicCandidate
from app.telemetry.queue_resolver import DeclaredQueueCandidate
from app.telemetry.runtime_identity import extract_runtime_identity_observations
from app.telemetry.scoped_attribution import (
    ClientCarrier,
    ScopedCallSeed,
    ScopedIngressRefusal,
    admissible,
    evaluate_scoped_ingress,
    server_only_refusal,
)
from app.telemetry.semconv.http import HTTP_REQUEST_METHOD, HTTP_ROUTE, PEER_SERVICE, URL_TEMPLATE
from app.telemetry.semconv.messaging import (
    MESSAGING_DESTINATION_KIND,
    MESSAGING_DESTINATION_NAME,
    MESSAGING_DESTINATION_SUBSCRIPTION_NAME,
    MESSAGING_OPERATION_TYPE,
    MESSAGING_SYSTEM,
)
from app.telemetry.service_resolver import (
    DeclaredServiceCandidate,
    resolve_runtime_span,
    resolve_service,
)

NO_ENVIRONMENT = "no_environment"
NO_STABLE_ROUTE = "no_stable_route"
NO_DESTINATION_NAME = "no_destination_name"
# 11H R3/spec §17 - CLIENT_ONLY/SERVER_ONLY-specific reason codes. Spec §17 lists three more
# (UNSTABLE_HTTP_ROUTE, AMBIGUOUS_SERVICE, UNSUPPORTED_SPAN) with an "extend as needed" framing;
# not added since none has a concrete trigger site in this codebase yet (NO_STABLE_ROUTE already
# covers route instability).
MISSING_TARGET_IDENTITY = "missing_target_identity"
MISSING_CALLER_IDENTITY = "missing_caller_identity"
CORRELATION_EXPIRED = "correlation_expired"


def _find_correlated_pairs(
    spans: list[RuntimeSpan],
) -> tuple[list[tuple[RuntimeSpan, RuntimeSpan]], list[RuntimeSpan], list[RuntimeSpan]]:
    """Pairs each SERVER span with its correlated CLIENT span (same trace_id,
    server.parent_span_id == client.span_id) WITHIN this list only, and also returns the CLIENT/
    SERVER spans that didn't pair up in this batch - candidates for cross-batch correlation via an
    HttpCorrelationBuffer (11H R2/spec §6), if the caller supplies one. A SERVER span with no
    parent_span_id can never pair with anything by construction and is silently excluded from both
    the pairs and the leftover-server list, exactly as it was silently excluded before."""
    clients_by_key = {(s.trace_id, s.span_id): s for s in spans if s.span_kind == "CLIENT"}
    matched_client_keys: set[tuple[str, str]] = set()
    pairs = []
    leftover_servers = []
    for span in spans:
        if span.span_kind != "SERVER" or span.parent_span_id is None:
            continue
        key = (span.trace_id, span.parent_span_id)
        client = clients_by_key.get(key)
        if client is not None:
            pairs.append((client, span))
            matched_client_keys.add(key)
        else:
            leftover_servers.append(span)
    leftover_clients = [
        s
        for s in spans
        if s.span_kind == "CLIENT" and (s.trace_id, s.span_id) not in matched_client_keys
    ]
    return pairs, leftover_clients, leftover_servers


def _record_if_observed_only(
    entities: dict[str, ObservedOnlyEntity],
    *,
    entity_id: str,
    discovery_status: DiscoveryStatus | None,
    label: Literal["Service", "Operation", "Queue"],
    name: str,
) -> None:
    if discovery_status == DiscoveryStatus.OBSERVED_ONLY:
        entities[entity_id] = ObservedOnlyEntity(id=entity_id, label=label, name=name)


def _build_call_fact(
    *,
    operation_candidates: list[DeclaredOperationCandidate],
    entities: dict[str, ObservedOnlyEntity],
    caller_service_id: str,
    provider_service_id: str,
    caller_service_version: str | None,
    provider_service_version: str | None = None,
    environment: str,
    method: str,
    route: str,
    timestamp: datetime,
    trace_id: str,
    correlation_mode: str,
    client_carrier: ClientCarrier | None,
    scoped_refusals: list[ScopedIngressRefusal],
) -> list[ObservedFactCandidate]:
    """Shared CALLS-fact core for both in-batch and cross-batch correlated observations, once both
    sides' service identity is already resolved and environment/method/route are known to be
    present - the piece of fact-construction logic (operation resolution, evidence, the fact
    itself) that's identical regardless of how the CLIENT/SERVER pair was correlated. Returns []
    (never guessed) if the operation can't be resolved - callers report NO_STABLE_ROUTE.

    When the operation resolves as OBSERVED_ONLY (runtime-discovered, no declared PROVIDES edge -
    11H-D/spec §8), also returns a second observed PROVIDES fact (provider -> operation) alongside
    the CALLS fact, so the provider side of a runtime-discovered operation is itself confirmable/
    visible to blast-radius and coverage analyses, not just the caller side. Never emitted for an
    already-DECLARED operation - it already has its PROVIDES edge from the OpenAPI import, and
    11H-D/spec §8.4's reconciliation guarantee (a later real declaration must reuse this exact
    operation id, not mint a duplicate node) depends on the id-normalization fix in
    openapi_adapter.py, not on anything here.

    v0.6.0 I2.1c: once a CALLS fact exists (guard I-1), the original CLIENT's carrier is evaluated
    against guards I-2..I-5. An eligible interaction's seed rides on the CALLS fact; otherwise an
    ingestion-only refusal is appended to `scoped_refusals`. The v1 facts and evidence built here
    are identical either way."""
    operation = resolve_operation(
        operation_candidates, provider_service_id=provider_service_id, method=method, route=route
    )
    if operation.operation_id is None:
        return []
    _record_if_observed_only(
        entities,
        entity_id=operation.operation_id,
        discovery_status=operation.discovery_status,
        label="Operation",
        name=f"{method} {route}",
    )

    bucket_start, bucket_end = day_bucket(timestamp)
    calls_evidence = ObservedEvidence(
        id=ids.observed_evidence_id(
            environment, bucket_start, caller_service_id, "CALLS", operation.operation_id
        ),
        environment=environment,
        bucket_start=bucket_start,
        bucket_end=bucket_end,
        first_seen=timestamp,
        last_seen=timestamp,
        observation_count=1,
        sample_trace_ids=[trace_id],
        service_version=caller_service_version,
        correlation_mode=correlation_mode,
    )
    outcome = evaluate_scoped_ingress(
        subject_id=caller_service_id,
        object_id=operation.operation_id,
        fact_environment=environment,
        fact_timestamp=timestamp,
        trace_id=trace_id,
        correlation_mode=correlation_mode,
        carrier=client_carrier,
    )
    if isinstance(outcome, ScopedIngressRefusal):
        scoped_refusals.append(outcome)
    facts = [
        ObservedFactCandidate(
            subject_id=caller_service_id,
            relation_type="CALLS",
            object_id=operation.operation_id,
            environment=environment,
            timestamp=timestamp,
            trace_id=trace_id,
            source_service_version=caller_service_version,
            evidence=calls_evidence,
            scoped_seed=outcome if isinstance(outcome, ScopedCallSeed) else None,
        )
    ]

    if operation.discovery_status == DiscoveryStatus.OBSERVED_ONLY:
        provides_evidence = ObservedEvidence(
            id=ids.observed_evidence_id(
                environment, bucket_start, provider_service_id, "PROVIDES", operation.operation_id
            ),
            environment=environment,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            first_seen=timestamp,
            last_seen=timestamp,
            observation_count=1,
            sample_trace_ids=[trace_id],
            service_version=provider_service_version,
            correlation_mode=correlation_mode,
        )
        facts.append(
            ObservedFactCandidate(
                subject_id=provider_service_id,
                relation_type="PROVIDES",
                object_id=operation.operation_id,
                environment=environment,
                timestamp=timestamp,
                trace_id=trace_id,
                source_service_version=provider_service_version,
                evidence=provides_evidence,
            )
        )

    return facts


def _pending_span_from_server(server: RuntimeSpan, *, method: str, route: str) -> PendingHttpSpan:
    return PendingHttpSpan(
        trace_id=server.trace_id,
        span_id=server.span_id,
        parent_span_id=server.parent_span_id,
        span_kind="SERVER",
        service_name=server.service_name,
        service_namespace=server.service_namespace,
        service_version=server.service_version,
        environment=server.environment,
        method=method,
        route=route,
        timestamp=server.end_time,
    )


def _pending_span_from_client(client: RuntimeSpan) -> PendingHttpSpan:
    """Unlike the paired/cross-batch-matched CALLS path (which always sources method/route from
    the SERVER span, per H4.6), a CLIENT_ONLY observation has no SERVER side to source from at
    all - so method/route/target_identity are extracted here from the CLIENT span's own
    attributes, even though the CLIENT_SERVER paths that also call this function never read them
    back off a matched client (harmless, inert extra fields for those paths)."""
    return PendingHttpSpan(
        trace_id=client.trace_id,
        span_id=client.span_id,
        parent_span_id=client.parent_span_id,
        span_kind="CLIENT",
        service_name=client.service_name,
        service_namespace=client.service_namespace,
        service_version=client.service_version,
        environment=client.environment,
        method=client.attributes.get(HTTP_REQUEST_METHOD),
        route=client.attributes.get(HTTP_ROUTE) or client.attributes.get(URL_TEMPLATE),
        target_identity=client.attributes.get(PEER_SERVICE),
        timestamp=client.end_time,
        # I2.1c: the original CLIENT's admitted Kubernetes identity (matrix §10.2).
        k8s_pod_uid=admissible(client.k8s_pod_uid),
        k8s_cluster_uid=admissible(client.k8s_cluster_uid),
        k8s_namespace_name=admissible(client.k8s_namespace_name),
        k8s_pod_name=admissible(client.k8s_pod_name),
        k8s_deployment_name=admissible(client.k8s_deployment_name),
        k8s_statefulset_name=admissible(client.k8s_statefulset_name),
        k8s_daemonset_name=admissible(client.k8s_daemonset_name),
    )


def correlate_http_call_observations(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    operation_candidates: list[DeclaredOperationCandidate],
    service_aliases: dict[str, str],
    correlation_buffer: HttpCorrelationBuffer | None = None,
) -> ObservationBatch:
    """Correlates HTTP CLIENT/SERVER span pairs into observed CALLS relationships (spec §20-23).

    Pairing happens in two phases. First, within this one decoded OTLP batch
    (_find_correlated_pairs). Second, for whichever CLIENT/SERVER spans didn't pair up in this
    batch, against a caller-supplied HttpCorrelationBuffer (11H R2/spec §6) - a bounded, TTL-based,
    in-memory store of spans still awaiting their counterpart from a *different* /v1/traces POST.
    This supersedes H4's original single-batch-only limitation: real OTel Collector batch
    processors flush by time/size, not trace completeness, so a call's two sides frequently arrive
    in separate batches - the buffer (never a Neo4j Span store, never unbounded, spec
    §6.3/§13/§14) closes that gap while still never becoming the "trace store"/causality graph
    this platform deliberately stays out of. Passing correlation_buffer=None (the default) skips
    the second phase entirely, preserving exactly the original single-batch-only behavior -
    existing callers/tests are unaffected.

    Environment, method, route, and timestamp are always read from the SERVER span, not the
    client - this is necessary, not just a style choice: declared Operation ids are minted from
    the provider's own OpenAPI path, so sourcing the route from the client's url.template instead
    risks a lexical mismatch against the declared path string, silently breaking Fall A matching
    (H4.6). This holds identically whether the SERVER span was seen in-batch or arrived from the
    correlation buffer. source_service_version comes from the CLIENT span (the "source"/calling
    side) in both phases too.
    """
    facts: list[ObservedFactCandidate] = []
    entities: dict[str, ObservedOnlyEntity] = {}
    unresolved: list[UnresolvedObservation] = []
    scoped_refusals: list[ScopedIngressRefusal] = []

    pairs, leftover_clients, leftover_servers = _find_correlated_pairs(spans)

    for client, server in pairs:
        caller = resolve_runtime_span(service_candidates, client, aliases=service_aliases)
        provider = resolve_runtime_span(service_candidates, server, aliases=service_aliases)
        _record_if_observed_only(
            entities,
            entity_id=caller.service_id,
            discovery_status=caller.discovery_status,
            label="Service",
            name=client.service_name,
        )
        _record_if_observed_only(
            entities,
            entity_id=provider.service_id,
            discovery_status=provider.discovery_status,
            label="Service",
            name=server.service_name,
        )

        if not server.environment:
            # Never guess an environment - a fabricated placeholder could quietly pollute a later
            # environment-scoped analysis (spec §14/§40's "don't invent facts" principle).
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_ENVIRONMENT)
            )
            continue

        method = server.attributes.get(HTTP_REQUEST_METHOD)
        route = server.attributes.get(HTTP_ROUTE) or server.attributes.get(URL_TEMPLATE)
        if not method or not route:
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
            )
            continue

        new_facts = _build_call_fact(
            operation_candidates=operation_candidates,
            entities=entities,
            caller_service_id=caller.service_id,
            provider_service_id=provider.service_id,
            caller_service_version=client.service_version,
            provider_service_version=server.service_version,
            environment=server.environment,
            method=method,
            route=route,
            timestamp=server.end_time,
            trace_id=server.trace_id,
            correlation_mode="CLIENT_SERVER",
            client_carrier=ClientCarrier.from_span(client),
            scoped_refusals=scoped_refusals,
        )
        if not new_facts:
            unresolved.append(
                UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
            )
            continue
        facts.extend(new_facts)

    if correlation_buffer is not None:
        # Drain whatever aged out of the buffer since it was last touched, independent of this
        # batch's own spans (11H-C/spec §7) - a CLIENT/SERVER span that never gets a counterpart
        # becomes a CLIENT_ONLY/SERVER_ONLY candidate instead of vanishing silently.
        expired_clients, expired_servers = correlation_buffer.sweep_expired()

        for expired_client in expired_clients:
            caller = resolve_service(
                service_candidates,
                service_name=expired_client.service_name,
                service_namespace=expired_client.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=caller.service_id,
                discovery_status=caller.discovery_status,
                label="Service",
                name=expired_client.service_name,
            )

            if not expired_client.method or not expired_client.route:
                unresolved.append(
                    UnresolvedObservation(
                        trace_id=expired_client.trace_id, reason=CORRELATION_EXPIRED
                    )
                )
                continue
            if not expired_client.target_identity:
                # peer.service is the only allowlisted way to identify a CLIENT-only call's
                # target - never guessed from server.address/an IP alone (spec §7.5).
                unresolved.append(
                    UnresolvedObservation(
                        trace_id=expired_client.trace_id, reason=MISSING_TARGET_IDENTITY
                    )
                )
                continue
            if not expired_client.environment:
                unresolved.append(
                    UnresolvedObservation(trace_id=expired_client.trace_id, reason=NO_ENVIRONMENT)
                )
                continue

            provider = resolve_service(
                service_candidates,
                service_name=expired_client.target_identity,
                service_namespace=None,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=expired_client.target_identity,
            )

            new_facts = _build_call_fact(
                operation_candidates=operation_candidates,
                entities=entities,
                caller_service_id=caller.service_id,
                provider_service_id=provider.service_id,
                caller_service_version=expired_client.service_version,
                environment=expired_client.environment,
                method=expired_client.method,
                route=expired_client.route,
                timestamp=expired_client.timestamp,
                trace_id=expired_client.trace_id,
                correlation_mode="CLIENT_ONLY",
                client_carrier=ClientCarrier.from_span(expired_client),
                scoped_refusals=scoped_refusals,
            )
            if not new_facts:
                unresolved.append(
                    UnresolvedObservation(trace_id=expired_client.trace_id, reason=NO_STABLE_ROUTE)
                )
                continue
            facts.extend(new_facts)

        for expired_server in expired_servers:
            # Every SERVER PendingHttpSpan the buffer stores was already validated (environment,
            # method, route all present) before being offered - see the leftover_servers loop
            # below. Nothing in this codebase's current semconv allowlist identifies a CALLER from
            # a SERVER span alone (spec §7.3), so this is expected to fire for every SERVER_ONLY
            # case today - the check exists so 11H.8 ("never invent an unknown caller") is a real,
            # tested structural guarantee, not an accident of missing data.
            provider = resolve_service(
                service_candidates,
                service_name=expired_server.service_name,
                service_namespace=expired_server.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=expired_server.service_name,
            )
            unresolved.append(
                UnresolvedObservation(
                    trace_id=expired_server.trace_id, reason=MISSING_CALLER_IDENTITY
                )
            )
            # I2.1c: no CLIENT identity exists for a SERVER_ONLY interaction (I1 L09b).
            scoped_refusals.append(
                server_only_refusal(
                    trace_id=expired_server.trace_id,
                    environment=expired_server.environment,
                    timestamp=expired_server.timestamp,
                )
            )

        for server in leftover_servers:
            if not server.environment:
                unresolved.append(
                    UnresolvedObservation(trace_id=server.trace_id, reason=NO_ENVIRONMENT)
                )
                continue
            method = server.attributes.get(HTTP_REQUEST_METHOD)
            route = server.attributes.get(HTTP_ROUTE) or server.attributes.get(URL_TEMPLATE)
            if not method or not route:
                unresolved.append(
                    UnresolvedObservation(trace_id=server.trace_id, reason=NO_STABLE_ROUTE)
                )
                continue

            provider = resolve_runtime_span(service_candidates, server, aliases=service_aliases)
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=server.service_name,
            )

            matched_client = correlation_buffer.offer_server(
                _pending_span_from_server(server, method=method, route=route)
            )
            if matched_client is None:
                continue

            caller = resolve_service(
                service_candidates,
                service_name=matched_client.service_name,
                service_namespace=matched_client.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=caller.service_id,
                discovery_status=caller.discovery_status,
                label="Service",
                name=matched_client.service_name,
            )

            facts.extend(
                _build_call_fact(
                    operation_candidates=operation_candidates,
                    entities=entities,
                    caller_service_id=caller.service_id,
                    provider_service_id=provider.service_id,
                    caller_service_version=matched_client.service_version,
                    provider_service_version=server.service_version,
                    environment=server.environment,
                    method=method,
                    route=route,
                    timestamp=server.end_time,
                    trace_id=server.trace_id,
                    correlation_mode="CLIENT_SERVER",
                    client_carrier=ClientCarrier.from_span(matched_client),
                    scoped_refusals=scoped_refusals,
                )
            )

        for client in leftover_clients:
            caller = resolve_runtime_span(service_candidates, client, aliases=service_aliases)
            _record_if_observed_only(
                entities,
                entity_id=caller.service_id,
                discovery_status=caller.discovery_status,
                label="Service",
                name=client.service_name,
            )

            matched_server = correlation_buffer.offer_client(_pending_span_from_client(client))
            if matched_server is None:
                continue
            # Every SERVER PendingHttpSpan the buffer ever stores was validated (environment,
            # method, route all present) before being offered - see the leftover_servers loop
            # above, the only place offer_server() is ever called.
            assert matched_server.environment and matched_server.method and matched_server.route

            provider = resolve_service(
                service_candidates,
                service_name=matched_server.service_name,
                service_namespace=matched_server.service_namespace,
                aliases=service_aliases,
            )
            _record_if_observed_only(
                entities,
                entity_id=provider.service_id,
                discovery_status=provider.discovery_status,
                label="Service",
                name=matched_server.service_name,
            )

            facts.extend(
                _build_call_fact(
                    operation_candidates=operation_candidates,
                    entities=entities,
                    caller_service_id=caller.service_id,
                    provider_service_id=provider.service_id,
                    caller_service_version=client.service_version,
                    provider_service_version=matched_server.service_version,
                    environment=matched_server.environment,
                    method=matched_server.method,
                    route=matched_server.route,
                    timestamp=matched_server.timestamp,
                    trace_id=matched_server.trace_id,
                    correlation_mode="CLIENT_SERVER",
                    client_carrier=ClientCarrier.from_span(client),
                    scoped_refusals=scoped_refusals,
                )
            )

    return ObservationBatch(
        entities=list(entities.values()),
        facts=facts,
        unresolved=unresolved,
        scoped_refusals=scoped_refusals,
    )


def correlate_queue_observations(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    queue_candidates: list[DeclaredQueueCandidate],
    service_aliases: dict[str, str],
    queue_aliases: dict[str, str],
    topic_candidates: Sequence[DeclaredTopicCandidate] = (),
    subscription_candidates: Sequence[DeclaredSubscriptionCandidate] = (),
    topic_aliases: dict[str, str] | None = None,
) -> ObservationBatch:
    """Builds observed SENDS/RECEIVES_FROM facts from messaging spans (spec §24-26). Unlike HTTP,
    no correlation between spans is needed - SENDS/RECEIVES_FROM are independent relations, each
    derivable from a single span alone (spec §24's existing graph model already treats them this
    way).

    Classification keys exclusively off messaging.operation.type (spec §25/§26's own literal
    examples never mention span_kind, and messaging.operation.type exists in real OTel semantic
    conventions specifically because span_kind is too coarse to disambiguate "receive" from
    "process"). A span with no recognized operation.type is not a candidate observation at all and
    is silently skipped, not reported as unresolved - the same status as an INTERNAL-kind span in
    the HTTP path. This recognition surface is frozen (v0.4.1 I2 spec §21) - I2 only adds refusal
    paths after this point, never new recognition before it.

    v0.4.1 I2 (spec §6/§18/§22): the destination and service-identity guards both run, in that
    order, before any entity, Evidence, or fact is recorded for a span - neither guard is wired
    alone (spec §36), and no unsafe "mint anyway" path exists. A destination refusal is reported
    without ever resolving service identity (spec §6's destination-first precedence, so exactly one
    reason is produced when both would fail); a service refusal after a destination accept still
    records nothing - the accepted destination's resolution is discarded, not partially persisted.

    v0.5.0 I4 spec §9: the same destination-first/service-second order also qualifies
    already-declared Topic/Subscription topology via `decide_messaging_destination` - a `send`
    confirms `Service -[PUBLISHES_TO]-> Topic`, a `receive`/`process` with an exactly matching
    `messaging.destination.subscription.name` confirms `Service -[RECEIVES_FROM]-> Subscription`.
    Nothing on that route is ever recorded as an observed-only entity: no Topic/Subscription is
    minted from runtime evidence.
    """
    topic_aliases = topic_aliases or {}
    facts: list[ObservedFactCandidate] = []
    entities: dict[str, ObservedOnlyEntity] = {}
    unresolved: list[UnresolvedObservation] = []

    for span in spans:
        operation_type = (span.attributes.get(MESSAGING_OPERATION_TYPE) or "").lower()
        if operation_type == "send":
            relation_type, correlation_mode = "SENDS", "MESSAGING_SEND"
        elif operation_type == "receive":
            relation_type, correlation_mode = "RECEIVES_FROM", "MESSAGING_RECEIVE"
        elif operation_type == "process":
            # receive and process both map to the same RECEIVES_FROM relation type (spec §25/§26)
            # but keep distinct correlation_mode values (11H R3/spec §14) - the relation semantics
            # don't change, only the evidence metadata gets more precise.
            relation_type, correlation_mode = "RECEIVES_FROM", "MESSAGING_PROCESS"
        else:
            continue

        destination_name = span.attributes.get(MESSAGING_DESTINATION_NAME)
        if not destination_name:
            unresolved.append(
                UnresolvedObservation(trace_id=span.trace_id, reason=NO_DESTINATION_NAME)
            )
            continue

        if not span.environment:
            unresolved.append(UnresolvedObservation(trace_id=span.trace_id, reason=NO_ENVIRONMENT))
            continue

        messaging_system = span.attributes.get(MESSAGING_SYSTEM)
        destination_decision = decide_messaging_destination(
            queue_candidates,
            list(topic_candidates),
            list(subscription_candidates),
            messaging_system=messaging_system,
            destination_name=destination_name,
            destination_kind=span.attributes.get(MESSAGING_DESTINATION_KIND),
            is_consumer=relation_type == "RECEIVES_FROM",
            subscription_name=span.attributes.get(MESSAGING_DESTINATION_SUBSCRIPTION_NAME),
            queue_aliases=queue_aliases,
            topic_aliases=topic_aliases,
        )
        if not destination_decision.accepted:
            # every refused decision from decide_messaging_destination carries a refusal_reason
            assert destination_decision.refusal_reason is not None
            unresolved.append(
                UnresolvedObservation(
                    trace_id=span.trace_id, reason=destination_decision.refusal_reason
                )
            )
            continue

        service_decision = decide_service_identity(
            service_candidates,
            service_name=span.service_name,
            service_namespace=span.service_namespace,
            aliases=service_aliases,
        )
        if not service_decision.accepted:
            # every refused decision from decide_service_identity carries a refusal_reason
            assert service_decision.refusal_reason is not None
            unresolved.append(
                UnresolvedObservation(
                    trace_id=span.trace_id, reason=service_decision.refusal_reason
                )
            )
            continue

        service_id = service_decision.service_id
        # every accepted decision from decide_service_identity carries its service_id
        assert service_id is not None
        _record_if_observed_only(
            entities,
            entity_id=service_id,
            discovery_status=service_decision.discovery_status,
            label="Service",
            name=span.service_name,
        )
        if isinstance(destination_decision, PubSubDecision):
            # I4 §9: a declared Topic (producer) or declared Subscription (consumer) only.
            if relation_type == "SENDS":
                fact_relation_type, object_id = "PUBLISHES_TO", destination_decision.topic_id
            else:
                fact_relation_type, object_id = (
                    "RECEIVES_FROM",
                    destination_decision.subscription_id,
                )
        else:
            fact_relation_type, object_id = relation_type, destination_decision.queue_id
            # every accepted queue decision carries its queue_id
            assert object_id is not None
            _record_if_observed_only(
                entities,
                entity_id=object_id,
                discovery_status=destination_decision.discovery_status,
                label="Queue",
                name=destination_name,
            )

        # An accepted producer decision carries topic_id, an accepted consumer decision carries
        # subscription_id (decide_messaging_destination only accepts a consumer after matching one).
        assert object_id is not None
        timestamp = span.end_time
        bucket_start, bucket_end = day_bucket(timestamp)
        evidence_id = ids.observed_evidence_id(
            span.environment,
            bucket_start,
            service_id,
            fact_relation_type,
            object_id,
        )
        evidence = ObservedEvidence(
            id=evidence_id,
            environment=span.environment,
            bucket_start=bucket_start,
            bucket_end=bucket_end,
            first_seen=timestamp,
            last_seen=timestamp,
            observation_count=1,
            sample_trace_ids=[span.trace_id],
            service_version=span.service_version,
            correlation_mode=correlation_mode,
        )
        facts.append(
            ObservedFactCandidate(
                subject_id=service_id,
                relation_type=fact_relation_type,
                object_id=object_id,
                environment=span.environment,
                timestamp=timestamp,
                trace_id=span.trace_id,
                source_service_version=span.service_version,
                evidence=evidence,
            )
        )

    return ObservationBatch(entities=list(entities.values()), facts=facts, unresolved=unresolved)


def adapt(
    spans: list[RuntimeSpan],
    *,
    service_candidates: list[DeclaredServiceCandidate],
    operation_candidates: list[DeclaredOperationCandidate],
    queue_candidates: list[DeclaredQueueCandidate],
    service_aliases: dict[str, str],
    queue_aliases: dict[str, str],
    correlation_buffer: HttpCorrelationBuffer | None = None,
    topic_candidates: Sequence[DeclaredTopicCandidate] = (),
    subscription_candidates: Sequence[DeclaredSubscriptionCandidate] = (),
    topic_aliases: dict[str, str] | None = None,
) -> ObservationBatch:
    """Combines HTTP and queue observations from one decoded OTLP batch into a single
    ObservationBatch (spec §9's OpenTelemetryAdapter stage).

    Deliberately narrower than the `adapt(raw_bytes)` shape noted as deferred in Iteration 11C's
    plan - still takes an already-decoded list[RuntimeSpan], not raw OTLP bytes. Composing
    decode-then-adapt, and wiring any of this into POST /v1/traces, is deferred further to
    whichever iteration first needs it (11E at the earliest, once there's something to persist).

    Also extracts I3 §9.4 bounded runtime identity observations (spec §23 slice 2) - a third,
    independent step sourced directly from `spans`, with no coupling to the HTTP/queue correlation
    above and no interaction inference.
    """
    http_batch = correlate_http_call_observations(
        spans,
        service_candidates=service_candidates,
        operation_candidates=operation_candidates,
        service_aliases=service_aliases,
        correlation_buffer=correlation_buffer,
    )
    queue_batch = correlate_queue_observations(
        spans,
        service_candidates=service_candidates,
        queue_candidates=queue_candidates,
        service_aliases=service_aliases,
        queue_aliases=queue_aliases,
        topic_candidates=topic_candidates,
        subscription_candidates=subscription_candidates,
        topic_aliases=topic_aliases,
    )
    runtime_identity_observations = extract_runtime_identity_observations(spans)

    entities: dict[str, ObservedOnlyEntity] = {}
    for entity in [*http_batch.entities, *queue_batch.entities]:
        entities[entity.id] = entity

    return ObservationBatch(
        entities=list(entities.values()),
        facts=[*http_batch.facts, *queue_batch.facts],
        unresolved=[*http_batch.unresolved, *queue_batch.unresolved],
        runtime_identity_observations=runtime_identity_observations,
        scoped_refusals=http_batch.scoped_refusals,
    )
