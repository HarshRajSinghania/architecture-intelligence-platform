from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import LiteralString

import neo4j

from app.qualification.declared_observed import (
    CONFIRMED,
    COVERAGE_NONE,  # noqa: F401 - re-exported; external importers use app.analysis.runtime.COVERAGE_NONE
    COVERAGE_PARTIAL,  # noqa: F401 - re-exported; see COVERAGE_NONE above
    COVERAGE_SUFFICIENT,  # noqa: F401 - re-exported; see COVERAGE_NONE above
    COVERAGE_UNKNOWN,  # noqa: F401 - re-exported; see COVERAGE_NONE above
    NOT_OBSERVED_IN_WINDOW,
    OBSERVED_ONLY,
    declared_evidence_exists,
    not_declared_evidence_exists,
    not_observed_evidence_exists,
    observed_evidence_condition,
    observed_evidence_exists,
)
from app.qualification.declared_observed import (
    classify_coverage as _kernel_classify_coverage,
)

DEFAULT_WINDOW_HOURS = 24
DEFAULT_ENVIRONMENT = "production"

# Shared building blocks for the CALLS branch used by O1-O4: CALLS always goes
# (Service)-[r]->(Operation), never Service->Service, and PROVIDES is only ever written by the
# declared OpenAPI import path (never by the H4 telemetry pipeline for an undeclared/Fall-B
# operation stub). An inner join through PROVIDES would therefore silently drop exactly the rows
# O3 exists to surface (undeclared operations/services) - every query below uses OPTIONAL MATCH
# and a coalesce() fallback chain for the target's identity instead.
_CALLS_TARGET_ID_EXPR: LiteralString = "coalesce(provider.id, o.id)"
_CALLS_TARGET_NAME_EXPR: LiteralString = (
    "coalesce(provider.name, o.name, o.method + ' ' + o.path, o.id)"
)
_CALLS_TARGET: LiteralString = (
    f"{_CALLS_TARGET_ID_EXPR} AS target_id, {_CALLS_TARGET_NAME_EXPR} AS target_name"
)

# I1.2 (spec §13): these Cypher fragments now originate from app.qualification.declared_observed,
# the single shared semantic owner for declared/observed evidence matching, instead of being
# independently authored here. Reconstructed under their existing private names so every
# downstream f-string usage below (_O2_QUERY/_O3_QUERY via _status_query, _O4_QUERY, the four
# coverage-driver queries) needs no further edits.
_OBSERVED_EXISTS = observed_evidence_exists()
_NOT_OBSERVED_EXISTS = not_observed_evidence_exists()
_DECLARED_EXISTS = declared_evidence_exists()
_NOT_DECLARED_EXISTS = not_declared_evidence_exists()


def default_since(hours: int = DEFAULT_WINDOW_HOURS) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


@dataclass(frozen=True)
class RelationObservation:
    """A relation with matching OBSERVED evidence - every row here was actually seen at runtime
    (used by O1/O2/O3). Multiple daily evidence buckets within the window are aggregated into one
    summary row per relation."""

    source_id: str
    source_name: str
    relation_type: str
    target_id: str
    target_name: str
    environment: str
    first_seen: datetime
    last_seen: datetime
    observation_count: int


_O1_QUERY: LiteralString = (
    "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
    "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
    # WITH is required here, not cosmetic: a WHERE clause directly after OPTIONAL MATCH is parsed
    # as part of that OPTIONAL MATCH's own pattern (Cypher grammar), not as a row filter - a false
    # condition just null-pads `provider` instead of dropping the row. This silently broke O1's
    # to_id/relation_type/from_id filters whenever they'd otherwise exclude a CALLS row (the row
    # survived anyway, with a wrongly-nulled provider feeding _CALLS_TARGET_ID_EXPR's fallback).
    "WITH a, r, o, provider "
    "WHERE ($relation_type IS NULL OR $relation_type = 'CALLS') "
    "AND ($from_id IS NULL OR a.id = $from_id) "
    f"AND ($to_id IS NULL OR {_CALLS_TARGET_ID_EXPR} = $to_id) "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    f"WHERE {observed_evidence_condition(environment_optional=True)} "
    f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET}, "
    "e.environment AS environment, "
    "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
    "sum(e.observation_count) AS observation_count "
    "UNION "
    "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
    "WHERE ($relation_type IS NULL OR $relation_type = type(r)) "
    "AND ($from_id IS NULL OR a.id = $from_id) AND ($to_id IS NULL OR b.id = $to_id) "
    "UNWIND coalesce(r.evidence_ids, []) AS eid "
    "MATCH (e:Evidence {id: eid}) "
    f"WHERE {observed_evidence_condition(environment_optional=True)} "
    "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
    "b.id AS target_id, b.name AS target_name, e.environment AS environment, "
    "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
    "sum(e.observation_count) AS observation_count "
    "ORDER BY source_id, target_id"
)


def observed_relations(
    session: neo4j.Session,
    *,
    environment: str | None = None,
    from_id: str | None = None,
    to_id: str | None = None,
    relation_type: str | None = None,
    since: datetime,
    until: datetime | None = None,
) -> list[RelationObservation]:
    """O1 - which architecture relationships were actually observed (spec §42). All filters are
    optional - a plain call with no filters is a valid raw listing."""
    records = session.run(
        _O1_QUERY,
        environment=environment,
        from_id=from_id,
        to_id=to_id,
        relation_type=relation_type,
        since=since,
        until=until,
    )
    return [RelationObservation(**record.data()) for record in records]


def _status_query(declared_guard: LiteralString, observed_guard: LiteralString) -> LiteralString:
    return (
        "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
        "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
        # See _O1_QUERY's comment - WHERE right after OPTIONAL MATCH filters the optional pattern,
        # not the row, so this WITH is required for the declared_guard/observed_guard EXISTS{}
        # checks to actually exclude non-matching rows instead of null-padding provider and
        # silently keeping them (which made O2/O3 return rows that belonged in the other's
        # category, or in O4, whenever the same environment had both CONFIRMED and DECLARED_ONLY/
        # OBSERVED_ONLY relations - i.e. essentially every non-trivial real graph).
        "WITH a, r, o, provider "
        f"WHERE {declared_guard} AND {observed_guard} "
        "UNWIND coalesce(r.evidence_ids, []) AS eid "
        "MATCH (e:Evidence {id: eid}) "
        f"WHERE {observed_evidence_condition()} "
        f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET}, "
        "e.environment AS environment, "
        "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
        "sum(e.observation_count) AS observation_count "
        "UNION "
        "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
        f"WHERE {declared_guard} AND {observed_guard} "
        "UNWIND coalesce(r.evidence_ids, []) AS eid "
        "MATCH (e:Evidence {id: eid}) "
        f"WHERE {observed_evidence_condition()} "
        "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
        "b.id AS target_id, b.name AS target_name, e.environment AS environment, "
        "min(e.first_seen) AS first_seen, max(e.last_seen) AS last_seen, "
        "sum(e.observation_count) AS observation_count "
        "ORDER BY source_id, target_id"
    )


_O2_QUERY = _status_query(_DECLARED_EXISTS, _OBSERVED_EXISTS)
_O3_QUERY = _status_query(_NOT_DECLARED_EXISTS, _OBSERVED_EXISTS)


def confirmed_relations(
    session: neo4j.Session, *, environment: str, since: datetime, until: datetime | None = None
) -> list[RelationObservation]:
    """O2 - Declared ∩ Observed (spec §43/§38: D ∧ O => CONFIRMED). environment is required, not
    optional: the same fact can be CONFIRMED in production and DECLARED_ONLY in staging
    simultaneously, so a status-deriving function can't default to "any" environment."""
    records = session.run(_O2_QUERY, environment=environment, since=since, until=until)
    return [RelationObservation(**record.data()) for record in records]


def observed_only_relations(
    session: neo4j.Session, *, environment: str, since: datetime, until: datetime | None = None
) -> list[RelationObservation]:
    """O3 - Observed - Declared (spec §44/§38: ¬D ∧ O => OBSERVED_ONLY) - undocumented real
    dependencies. Spec calls this "probably the most important H4 analysis"."""
    records = session.run(_O3_QUERY, environment=environment, since=since, until=until)
    return [RelationObservation(**record.data()) for record in records]


@dataclass(frozen=True)
class DeclaredOnlyRelation:
    """A relation with DECLARED evidence but no matching OBSERVED evidence in the given
    environment/window (spec §45/§38: D ∧ ¬O => DECLARED_ONLY). status is always
    NOT_OBSERVED_IN_WINDOW - never "obsolete"/"unused"/"dead" (spec §40/H4.16)."""

    source_id: str
    source_name: str
    relation_type: str
    target_id: str
    target_name: str
    environment: str
    since: datetime
    status: str
    telemetry_coverage_available: bool
    coverage: str


_O4_QUERY: LiteralString = (
    "MATCH (a:Service)-[r:CALLS]->(o:Operation) "
    "OPTIONAL MATCH (o)<-[:PROVIDES]-(provider:Service) "
    # Same fix as _O1_QUERY/_status_query - see their comments.
    "WITH a, r, o, provider "
    f"WHERE {_DECLARED_EXISTS} AND {_NOT_OBSERVED_EXISTS} "
    f"RETURN a.id AS source_id, a.name AS source_name, 'CALLS' AS relation_type, {_CALLS_TARGET} "
    "UNION "
    "MATCH (a:Service)-[r:SENDS|RECEIVES_FROM]->(b:Queue) "
    f"WHERE {_DECLARED_EXISTS} AND {_NOT_OBSERVED_EXISTS} "
    "RETURN a.id AS source_id, a.name AS source_name, type(r) AS relation_type, "
    "b.id AS target_id, b.name AS target_name "
    "ORDER BY source_id, target_id"
)


def declared_only_relations(
    session: neo4j.Session,
    *,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    qualification_enabled: bool = True,
) -> list[DeclaredOnlyRelation]:
    """O4 - Declared - Observed(window, environment) (spec §45/§38). telemetry_coverage_available
    and coverage are both composed from O5 (not duplicated Cypher), read off each row's SUBJECT -
    which is always a real, directly-identified Service, so this never needs the
    PROVIDES/target-side resolution that O1-O3's target identity does. qualification_enabled is
    spec §22's `telemetry.coverage.qualification-enabled` kill switch (11H-E/spec §11) - when
    False, `coverage` degrades to UNKNOWN for every row rather than being omitted, so API
    consumers never need to branch on the field's presence; telemetry_coverage_available's
    original boolean semantics are untouched either way."""
    rows = [
        dict(record)
        for record in session.run(_O4_QUERY, environment=environment, since=since, until=until)
    ]
    subject_ids = sorted({row["source_id"] for row in rows})
    # v0.4.1 I1.3: `until` MUST be threaded through here, not just into the O4 query above - a
    # pre-existing bug (predating I1) omitted it, so a service's coverage annotation always used an
    # open-ended upper bound regardless of what `until` this function itself was given, silently
    # counting observed evidence from *after* the requested window as coverage. Caught by the real-
    # Neo4j differential test (tests/integration/test_qualification_consistency.py, case Q13)
    # disagreeing with app.architecture_intelligence.dependency_projection's equivalent computation,
    # which already bounded coverage by `until` correctly (repository.read_service_dependency_rows
    # passes `until=window_end` to `telemetry_coverage` explicitly) - per spec §15, the differential
    # path was determined correct and only this path was changed.
    coverage = {
        c.service_id: c
        for c in telemetry_coverage(
            session, environment=environment, since=since, until=until, service_ids=subject_ids
        )
    }
    results = []
    for row in rows:
        service_coverage = coverage.get(row["source_id"])
        if service_coverage is None:
            available = False
        elif row["relation_type"] == "CALLS":
            available = service_coverage.http_observed
        else:
            available = service_coverage.messaging_observed
        results.append(
            DeclaredOnlyRelation(
                **row,
                environment=environment,
                since=since,
                status=NOT_OBSERVED_IN_WINDOW,
                telemetry_coverage_available=available,
                coverage=_classify_coverage(
                    service_coverage,
                    row["relation_type"],
                    qualification_enabled=qualification_enabled,
                ),
            )
        )
    return results


@dataclass(frozen=True)
class ServiceTelemetryCoverage:
    """Whether a service emitted any usable telemetry at all within the window/environment (spec
    §41/§46) - used to judge how trustworthy an O4 "not observed" result is. http_observed's
    provider-side check has a known, inherited limitation: it can only see PROVIDES edges, which
    the H4 telemetry pipeline never writes for an undeclared (Fall-B) operation, so a service that
    is only ever an undeclared provider will show http_observed=False even with real observed
    traffic reaching it."""

    service_id: str
    service_name: str
    environment: str
    since: datetime
    http_observed: bool
    messaging_observed: bool
    spans_observed: bool


_ALL_SERVICES_QUERY: LiteralString = "MATCH (s:Service) RETURN s.id AS id, s.name AS name"

_HTTP_CALLER_OBSERVED_QUERY: LiteralString = (
    f"MATCH (s:Service {{id: $service_id}})-[r:CALLS]->(:Operation) WHERE {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)
_HTTP_PROVIDER_OBSERVED_QUERY: LiteralString = (
    "MATCH (s:Service {id: $service_id})-[:PROVIDES]->(:Operation)<-[r:CALLS]-(:Service) "
    f"WHERE {_OBSERVED_EXISTS} RETURN count(r) > 0 AS observed"
)
# v0.5.0 I4 slice 4 (spec §12.5): one shared messaging-coverage rule, widened to the Pub/Sub
# relations - observed `PUBLISHES_TO -> Topic` counts like `SENDS -> Queue`, and observed
# `RECEIVES_FROM -> Subscription` like `RECEIVES_FROM -> Queue`. Target labels stay explicit so no
# other relation/label pairing silently becomes messaging coverage.
_SENDS_OBSERVED_QUERY: LiteralString = (
    "MATCH (s:Service {id: $service_id})-[r:SENDS|PUBLISHES_TO]->(t) "
    "WHERE ((type(r) = 'SENDS' AND t:Queue) OR (type(r) = 'PUBLISHES_TO' AND t:Topic)) "
    f"AND {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)
_RECEIVES_OBSERVED_QUERY: LiteralString = (
    "MATCH (s:Service {id: $service_id})-[r:RECEIVES_FROM]->(t) "
    f"WHERE (t:Queue OR t:Subscription) AND {_OBSERVED_EXISTS} "
    "RETURN count(r) > 0 AS observed"
)


def _observed(session: neo4j.Session, query: LiteralString, **params) -> bool:
    record = session.run(query, **params).single()
    return bool(record["observed"]) if record else False


def telemetry_coverage(
    session: neo4j.Session,
    *,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    service_ids: list[str] | None = None,
) -> list[ServiceTelemetryCoverage]:
    """O5 - per-service telemetry coverage (spec §46). Deliberately four small separate per-service
    queries rather than one combined traversal, mirroring blast_radius.py's existing preference for
    simple per-hop queries over one clever query."""
    if service_ids is None:
        services = [(r["id"], r["name"]) for r in session.run(_ALL_SERVICES_QUERY)]
    else:
        all_names = {r["id"]: r["name"] for r in session.run(_ALL_SERVICES_QUERY)}
        services = [(sid, all_names.get(sid, sid)) for sid in service_ids]

    results = []
    for service_id, service_name in services:
        params = {
            "service_id": service_id,
            "environment": environment,
            "since": since,
            "until": until,
        }
        http_observed = _observed(session, _HTTP_CALLER_OBSERVED_QUERY, **params) or _observed(
            session, _HTTP_PROVIDER_OBSERVED_QUERY, **params
        )
        messaging_observed = _observed(session, _SENDS_OBSERVED_QUERY, **params) or _observed(
            session, _RECEIVES_OBSERVED_QUERY, **params
        )
        results.append(
            ServiceTelemetryCoverage(
                service_id=service_id,
                service_name=service_name,
                environment=environment,
                since=since,
                http_observed=http_observed,
                messaging_observed=messaging_observed,
                spans_observed=http_observed or messaging_observed,
            )
        )
    return results


def _classify_coverage(
    service_coverage: ServiceTelemetryCoverage | None,
    relation_type: str,
    *,
    qualification_enabled: bool,
) -> str:
    """Qualifies how much weight an O4 NOT_OBSERVED_IN_WINDOW finding should carry (11H R7/spec
    §11, 11H.11; v0.4.1 spec §12). Thin adapter over the shared kernel's `classify_coverage`
    (app.qualification.declared_observed) - I1.2 unpacks this module's own
    `ServiceTelemetryCoverage` into the flat booleans the dependency-free kernel accepts. The
    kernel cannot import `ServiceTelemetryCoverage` itself: it's defined here, and this module
    imports the kernel, so the reverse import would be circular."""
    return _kernel_classify_coverage(
        relation_type,
        http_observed=service_coverage.http_observed if service_coverage else False,
        messaging_observed=service_coverage.messaging_observed if service_coverage else False,
        spans_observed=service_coverage.spans_observed if service_coverage else False,
        coverage_row_exists=service_coverage is not None,
        qualification_enabled=qualification_enabled,
    )


@dataclass(frozen=True)
class RuntimeRelationStatus:
    """One outgoing relation from a profiled service, labeled with its O2/O3/O4 status (used by
    service_runtime_profile - the Runtime API's per-service endpoint and the Service Explorer UI's
    Observed section, spec §49/§50)."""

    relation_type: str
    target_id: str
    target_name: str
    status: str  # "CONFIRMED" | "OBSERVED_ONLY" | NOT_OBSERVED_IN_WINDOW
    first_seen: datetime | None
    last_seen: datetime | None
    observation_count: int | None
    telemetry_coverage_available: bool | None  # only meaningful for NOT_OBSERVED_IN_WINDOW rows
    coverage: str | None  # SUFFICIENT/PARTIAL/NONE/UNKNOWN - only meaningful for the same rows


@dataclass(frozen=True)
class ServiceRuntimeProfile:
    service_id: str
    service_name: str
    environment: str
    since: datetime
    coverage: ServiceTelemetryCoverage
    relations: list[RuntimeRelationStatus]


_SERVICE_NAME_QUERY: LiteralString = "MATCH (s:Service {id: $id}) RETURN s.name AS name"


def service_runtime_profile(
    session: neo4j.Session,
    *,
    service_id: str,
    environment: str,
    since: datetime,
    until: datetime | None = None,
    qualification_enabled: bool = True,
) -> ServiceRuntimeProfile | None:
    """Per-service runtime view: this service's outgoing CONFIRMED + OBSERVED_ONLY + DECLARED_ONLY
    relations plus its O5 coverage (spec §49's sketch shows only outgoing declared/observed
    relations from the profiled service's own perspective - matches the existing declared
    Provides/Calls asymmetry already in service.html). Composes O2+O3+O4+O5 rather than adding a
    from_id filter to those four tested functions - filters their full-graph results down to
    source_id == service_id in Python, deliberately not touching their signatures/tests, cheap at
    this PoC's scale (same "simple over clever" call O5 itself already makes). Returns None if the
    service doesn't exist - callers decide the 404."""
    name_row = session.run(_SERVICE_NAME_QUERY, id=service_id).single()
    if name_row is None:
        return None

    confirmed = [
        r
        for r in confirmed_relations(session, environment=environment, since=since, until=until)
        if r.source_id == service_id
    ]
    observed_only = [
        r
        for r in observed_only_relations(session, environment=environment, since=since, until=until)
        if r.source_id == service_id
    ]
    declared_only = [
        r
        for r in declared_only_relations(
            session,
            environment=environment,
            since=since,
            until=until,
            qualification_enabled=qualification_enabled,
        )
        if r.source_id == service_id
    ]
    coverage = telemetry_coverage(
        session, environment=environment, since=since, until=until, service_ids=[service_id]
    )[0]

    relations = (
        [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status=CONFIRMED,
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                observation_count=r.observation_count,
                telemetry_coverage_available=None,
                coverage=None,
            )
            for r in confirmed
        ]
        + [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status=OBSERVED_ONLY,
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                observation_count=r.observation_count,
                telemetry_coverage_available=None,
                coverage=None,
            )
            for r in observed_only
        ]
        + [
            RuntimeRelationStatus(
                relation_type=r.relation_type,
                target_id=r.target_id,
                target_name=r.target_name,
                status=r.status,
                first_seen=None,
                last_seen=None,
                observation_count=None,
                telemetry_coverage_available=r.telemetry_coverage_available,
                coverage=r.coverage,
            )
            for r in declared_only
        ]
    )
    return ServiceRuntimeProfile(
        service_id=service_id,
        service_name=name_row["name"],
        environment=environment,
        since=since,
        coverage=coverage,
        relations=relations,
    )
