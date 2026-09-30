"""Schema and dedicated reader for the isolated v2 scoped records (v0.6.0 I2.2a).

Persistence wiring is I2.2b; here records are stored directly, exactly as the aggregator will, to
prove the constraint, the subject index and the reader's ordering, paging, filtering and label
isolation on a real Neo4j.
"""

from datetime import UTC, datetime, timedelta

import pytest
from neo4j.exceptions import ConstraintError

from app.architecture_intelligence.scoped_evidence_repository import (
    DEFAULT_PAGE_SIZE,
    read_scoped_observed_calls,
)
from app.graph.schema import ensure_schema
from app.telemetry.scoped_attribution import ScopedCallSeed
from app.telemetry.scoped_evidence import record_from_seed

DATABASE = "neo4j"
BASE = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
CALLER = "service:orders-repo-test"
OTHER_CALLER = "service:payments-repo-test"
O1 = "operation:pricing:GET:/prices"
O2 = "operation:legacy-pricing:GET:/prices"

_STORE = "MERGE (v:ScopedObservedCallV2 {id: $id}) SET v += $props"


@pytest.fixture(scope="module", autouse=True)
def schema(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n")
        ensure_schema(session)


@pytest.fixture
def session(driver):
    with driver.session(database=DATABASE) as s:
        s.run("MATCH (v:ScopedObservedCallV2) DETACH DELETE v")
        s.run("MATCH (e:Evidence) WHERE e.id STARTS WITH 'decoy:' DETACH DELETE e")
        yield s


def _record(*, pod: str, subject=CALLER, obj=O1, day="2026-09-28", environment="production", **kw):
    return record_from_seed(
        ScopedCallSeed(
            environment=environment,
            bucket_utc_day=day,
            subject_id=subject,
            object_id=obj,
            caller_cluster_uid="K1",
            caller_pod_uid=pod,
            fact_timestamp=kw.pop("fact_timestamp", BASE),
            trace_id="a" * 32,
            correlation_mode="CLIENT_SERVER",
            **kw,
        )
    )


def _store(session, record):
    session.run(_STORE, id=record.id, props=record.model_dump(exclude={"id"})).consume()
    return record


def test_ensure_schema_creates_the_v2_constraint_and_the_subject_index(session):
    constraints = {r["name"] for r in session.run("SHOW CONSTRAINTS YIELD name")}
    indexes = {r["name"] for r in session.run("SHOW INDEXES YIELD name")}

    assert "scoped_observed_call_v2_id" in constraints
    assert "scoped_observed_call_v2_subject" in indexes


def test_ensure_schema_is_idempotent(session):
    ensure_schema(session)
    ensure_schema(session)


def test_two_nodes_with_one_v2_id_are_rejected_by_the_constraint(session):
    record = _store(session, _record(pod="P1"))

    with pytest.raises(ConstraintError):
        session.run("CREATE (:ScopedObservedCallV2 {id: $id})", id=record.id).consume()


def test_records_round_trip_exactly_with_aware_datetimes(session):
    original = _store(
        session, _record(pod="P1", k8s_namespace_name="shop", k8s_pod_name="orders-a")
    )

    [read] = read_scoped_observed_calls(session, subject_id=CALLER).records

    assert read == original
    assert read.first_seen.tzinfo is not None and read.first_seen == BASE


def test_the_reader_returns_records_in_ascending_id_order(session):
    for pod in ("P4", "P1", "P3", "P2", "P5"):
        _store(session, _record(pod=pod))

    page = read_scoped_observed_calls(session, subject_id=CALLER)

    assert [r.id for r in page.records] == sorted(r.id for r in page.records)
    assert len(page.records) == 5 and page.truncated is False


def test_paging_walks_every_record_once_and_flags_truncation(session):
    stored = sorted(_store(session, _record(pod=f"P{i}")).id for i in range(5))

    seen, after_id, flags = [], None, []
    while True:
        page = read_scoped_observed_calls(session, subject_id=CALLER, after_id=after_id, limit=2)
        seen += [r.id for r in page.records]
        flags.append(page.truncated)
        if not page.truncated:
            break
        after_id = page.records[-1].id

    assert seen == stored
    assert flags == [True, True, False]


def test_a_full_last_page_is_not_reported_as_truncated(session):
    for i in range(4):
        _store(session, _record(pod=f"P{i}"))

    assert read_scoped_observed_calls(session, subject_id=CALLER, limit=4).truncated is False
    assert read_scoped_observed_calls(session, subject_id=CALLER, limit=3).truncated is True


def test_the_reader_filters_by_caller_and_optionally_by_operation_only(session):
    a = _store(session, _record(pod="P1", obj=O1))
    b = _store(session, _record(pod="P2", obj=O2))
    _store(session, _record(pod="P3", subject=OTHER_CALLER))

    both = read_scoped_observed_calls(session, subject_id=CALLER).records
    only_o2 = read_scoped_observed_calls(session, subject_id=CALLER, object_id=O2).records

    assert {r.id for r in both} == {a.id, b.id}
    assert [r.id for r in only_o2] == [b.id]
    assert read_scoped_observed_calls(session, subject_id="service:nobody").records == ()


def test_environment_and_day_are_never_filters(session):
    """I1 L10b / L17d: a wrong-environment or wrong-day record must still be read, to be judged."""
    stored = {
        _store(session, _record(pod="P1", environment="staging")).id,
        _store(
            session, _record(pod="P2", day="2026-09-29", fact_timestamp=BASE + timedelta(days=1))
        ).id,
        _store(session, _record(pod="P3")).id,
    }

    assert {r.id for r in read_scoped_observed_calls(session, subject_id=CALLER).records} == stored


def test_only_the_v2_label_is_read_never_an_evidence_node_with_the_same_shape(session):
    record = _store(session, _record(pod="P1"))
    props = record.model_dump(exclude={"id"})
    session.run("CREATE (e:Evidence {id: 'decoy:evidence'}) SET e += $props", props=props).consume()
    session.run(
        "CREATE (n:SomethingElse {id: 'decoy:other'}) SET n += $props", props=props
    ).consume()

    ids_read = [r.id for r in read_scoped_observed_calls(session, subject_id=CALLER).records]
    session.run("MATCH (n:SomethingElse {id: 'decoy:other'}) DELETE n").consume()

    assert ids_read == [record.id]


def test_the_reader_works_inside_a_managed_transaction(session):
    record = _store(session, _record(pod="P1"))

    page = session.execute_read(read_scoped_observed_calls, subject_id=CALLER)

    assert [r.id for r in page.records] == [record.id]


def test_the_default_page_size_is_the_frozen_500():
    assert DEFAULT_PAGE_SIZE == 500


@pytest.mark.parametrize("limit", [0, -1, DEFAULT_PAGE_SIZE + 1, 1_000_000])
def test_a_limit_outside_the_frozen_page_bound_is_rejected(session, limit):
    with pytest.raises(ValueError, match="between 1 and 500"):
        read_scoped_observed_calls(session, subject_id=CALLER, limit=limit)


def test_the_full_page_size_is_accepted_and_bounds_the_result(session):
    for i in range(3):
        _store(session, _record(pod=f"P{i}"))

    page = read_scoped_observed_calls(session, subject_id=CALLER, limit=DEFAULT_PAGE_SIZE)

    assert len(page.records) == 3 and page.truncated is False
