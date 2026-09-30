"""Per-POST persistence of the isolated v2 scoped records (v0.6.0 I2.2b).

Real Neo4j, real transactions. Proves the flag gate, the isolation invariants of the I2 decision
record D1 (own label, no relationships, no owner ids, invisible to every v1 read, the snapshot and
the NL path), the unit's atomicity, lock-before-read under concurrency, order/split independence and
the one-revision-per-POST boundary.
"""

import random
import shutil
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.ai import question_service
from app.ai.cypher_validator import CypherValidationError
from app.ai.graph_reachability import GraphReachabilityError
from app.ai.question_service import ArchitectureQuestionService
from app.architecture_intelligence import repository
from app.architecture_intelligence.scoped_evidence_repository import read_scoped_observed_calls
from app.canonical import ids
from app.graph.importer import import_all_sources
from app.graph.revision_fence import bump_revision, lock_revision, read_revision
from app.graph.schema import ensure_schema
from app.provenance.model import ObservedEvidence
from app.settings import ScopedEvidenceConfig
from app.sources.model import FilesystemSourceConfig
from app.telemetry import aggregator
from app.telemetry.adapter import correlate_http_call_observations
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.correlation_buffer import HttpCorrelationBuffer
from app.telemetry.model import (
    ObservationBatch,
    ObservedFactCandidate,
    ObservedOnlyEntity,
    RuntimeSpan,
)
from app.telemetry.operation_resolver import DeclaredOperationCandidate
from app.telemetry.scoped_attribution import ScopedCallSeed
from app.telemetry.scoped_evidence import record_from_seed
from app.telemetry.service_resolver import DeclaredServiceCandidate

DATABASE = "neo4j"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "examples"
ON = ScopedEvidenceConfig(enabled=True)
OFF = ScopedEvidenceConfig(enabled=False)
CALLER = "service:orders-persist-test"
O1 = "operation:pricing-persist-test:GET:/prices"
K1 = "7f3c2a10-1b2d-4e5f-8a9b-0c1d2e3f4a5b"
BASE = datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
V2_PROPERTY_KEYS = {
    "id",
    "contract_version",
    "source_type",
    "evidence_type",
    "relation_type",
    "environment",
    "bucket_utc_day",
    "subject_id",
    "object_id",
    "caller_cluster_uid",
    "caller_pod_uid",
    "first_seen",
    "last_seen",
    "observation_count",
    "correlation_mode",
    "sample_trace_ids",
    "k8s_namespace_name",
    "k8s_pod_name",
    "k8s_deployment_name",
    "k8s_statefulset_name",
    "k8s_daemonset_name",
    "conflicting_consistency_attributes",
    "key_rule_id",
    "key_rule_version",
    "normalization_rule_id",
    "normalization_rule_version",
}


def _reset(driver):
    with driver.session(database=DATABASE) as session:
        session.run("MATCH (n) DETACH DELETE n").consume()
        ensure_schema(session)


@pytest.fixture
def graph(driver):
    _reset(driver)
    return driver


@pytest.fixture
def session(graph):
    with graph.session(database=DATABASE) as s:
        yield s


def _seed(
    *,
    pod="P1",
    subject=CALLER,
    obj=O1,
    day="2026-09-28",
    env="production",
    trace="a" * 32,
    at=BASE,
    mode="CLIENT_SERVER",
    **names,
) -> ScopedCallSeed:
    return ScopedCallSeed(
        environment=env,
        bucket_utc_day=day,
        subject_id=subject,
        object_id=obj,
        caller_cluster_uid=K1,
        caller_pod_uid=pod,
        fact_timestamp=at,
        trace_id=trace,
        correlation_mode=mode,
        **names,
    )


def _fact(seed: ScopedCallSeed) -> ObservedFactCandidate:
    day = datetime.fromisoformat(seed.bucket_utc_day).replace(tzinfo=UTC)
    return ObservedFactCandidate(
        subject_id=seed.subject_id,
        relation_type="CALLS",
        object_id=seed.object_id,
        environment=seed.environment,
        timestamp=seed.fact_timestamp,
        trace_id=seed.trace_id,
        evidence=ObservedEvidence(
            id=ids.observed_evidence_id(
                seed.environment, day, seed.subject_id, "CALLS", seed.object_id
            ),
            environment=seed.environment,
            bucket_start=day,
            bucket_end=day + timedelta(days=1),
            first_seen=seed.fact_timestamp,
            last_seen=seed.fact_timestamp,
            observation_count=1,
            sample_trace_ids=[seed.trace_id],
            correlation_mode=seed.correlation_mode,
        ),
        scoped_seed=seed,
    )


def _batch(*seeds: ScopedCallSeed) -> ObservationBatch:
    entities = {}
    for seed in seeds:
        entities[seed.subject_id] = ObservedOnlyEntity(
            id=seed.subject_id, label="Service", name=seed.subject_id
        )
        entities[seed.object_id] = ObservedOnlyEntity(
            id=seed.object_id, label="Operation", name=seed.object_id
        )
    return ObservationBatch(entities=list(entities.values()), facts=[_fact(seed) for seed in seeds])


def _persist(driver, *seeds, scoped=ON):
    persist_observation_batch(driver, DATABASE, _batch(*seeds), scoped=scoped)


def _count(session, query: str) -> int:
    return session.run(query).single()["c"]


def _v2_count(session) -> int:
    return _count(session, "MATCH (v:ScopedObservedCallV2) RETURN count(v) AS c")


def _v2_records(session, subject=CALLER):
    return read_scoped_observed_calls(session, subject_id=subject).records


# --- the flag ----------------------------------------------------------------------------------


@pytest.mark.parametrize("scoped", [None, OFF], ids=["absent", "disabled"])
def test_with_the_flag_off_nothing_v2_is_written_and_v1_is_unchanged(graph, session, scoped):
    before = read_revision(session)

    _persist(graph, _seed(), scoped=scoped)

    assert _v2_count(session) == 0
    assert _count(session, "MATCH (e:Evidence) RETURN count(e) AS c") == 1
    assert _count(session, "MATCH ()-[r:CALLS]->() RETURN count(r) AS c") == 1
    assert read_revision(session) == before + 1
    # v0.6.0 I2.2c: with the flag off there is no ledger, membership or counter either.
    assert (
        _count(
            session,
            "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ScopedEvidence') RETURN count(n) AS c",
        )
        == 0
    )


def test_with_the_flag_on_the_seed_becomes_one_isolated_record(graph, session):
    seed = _seed(k8s_namespace_name="shop", k8s_deployment_name="orders")

    _persist(graph, seed)

    [record] = _v2_records(session)
    assert record == record_from_seed(seed)
    node = session.run(
        "MATCH (v:ScopedObservedCallV2) RETURN labels(v) AS labels, keys(v) AS keys, "
        "COUNT { (v)--() } AS degree"
    ).single()
    assert node["labels"] == ["ScopedObservedCallV2"]
    # Neo4j stores no null property, so the three names this seed leaves unset are simply absent:
    # every non-null contract field is present and nothing outside the contract is.
    assert set(node["keys"]) == V2_PROPERTY_KEYS - {
        "k8s_pod_name",
        "k8s_statefulset_name",
        "k8s_daemonset_name",
    }
    assert "owner_source_ids" not in node["keys"]
    assert node["degree"] == 0


def test_a_fact_without_a_seed_writes_no_v2_even_with_the_flag_on(graph, session):
    fact = _fact(_seed()).model_copy(update={"scoped_seed": None})

    persist_observation_batch(
        graph,
        DATABASE,
        ObservationBatch(facts=[fact], entities=_batch(_seed()).entities),
        scoped=ON,
    )

    assert _v2_count(session) == 0
    assert _count(session, "MATCH (e:Evidence) RETURN count(e) AS c") == 1


def _v1_dump(session) -> dict:
    return {
        "evidence": sorted(
            str(dict(sorted(r["p"].items())))
            for r in session.run("MATCH (e:Evidence) RETURN properties(e) AS p")
        ),
        "relations": sorted(
            (r["a"], r["t"], r["b"], tuple(r["e"]))
            for r in session.run(
                "MATCH (a)-[r]->(b) RETURN a.id AS a, type(r) AS t, b.id AS b, r.evidence_ids AS e"
            )
        ),
        "nodes": sorted(
            str((r["l"], sorted(r["p"].items())))
            for r in session.run(
                "MATCH (n) WHERE NOT n:ScopedObservedCallV2 AND NOT n:AipInternalState "
                "AND NOT n:ScopedEvidenceCutover AND NOT n:ScopedEvidenceLegacyBucket "
                "AND NOT n:ScopedEvidenceTransitionCounter "
                "RETURN labels(n) AS l, properties(n) AS p"
            )
        ),
    }


def test_persisted_v1_state_is_identical_with_the_flag_on_and_off(driver):
    seeds = [_seed(pod="P1"), _seed(pod="P2", trace="b" * 32), _seed(pod="P1", trace="c" * 32)]
    dumps = {}
    for label, scoped in (("off", OFF), ("on", ON)):
        _reset(driver)
        _persist(driver, *seeds, scoped=scoped)
        with driver.session(database=DATABASE) as session:
            dumps[label] = _v1_dump(session)
            dumps[label + "_v2"] = _v2_count(session)

    assert dumps["off_v2"] == 0 and dumps["on_v2"] == 2
    assert dumps["off"] == dumps["on"]


# --- isolation from every v1 read, the snapshot and the NL path ---------------------------------


def _state(session):
    return repository.canonical_snapshot_state(session, coverage_qualification_enabled=True)


def test_the_snapshot_and_every_public_read_never_see_the_v2_record(driver):
    seeds = [_seed(pod="P1"), _seed(pod="P2", trace="b" * 32)]
    fingerprints = {}
    for label, scoped in (("off", OFF), ("on", ON)):
        _reset(driver)
        _persist(driver, *seeds, scoped=scoped)
        with driver.session(database=DATABASE) as session:
            fingerprints[label] = (
                repository.snapshot_fingerprint(_state(session)),
                read_revision(session),
            )
            if label == "on":
                v2_ids = [r.id for r in _v2_records(session)]
                assert len(v2_ids) == 2
                rows = repository.read_evidence_rows(session, evidence_ids=v2_ids)
                assert not any(row.get("id") in v2_ids for row in rows["evidence"])
                assert all(
                    repository.read_public_evidence_row(session, evidence_id=v) is None
                    for v in v2_ids
                )
                listed = {row["id"] for row in repository.read_public_evidence_list_rows(session)}
                assert not listed & set(v2_ids)
                relation_evidence = {
                    e for r in _state(session)["relations"] for e in (r.get("evidence_ids") or [])
                }
                assert not relation_evidence & set(v2_ids)

    # The v2 key enters the snapshot only in I2.5: until then a v2 record changes nothing in it.
    assert fingerprints["on"] == fingerprints["off"]


def test_declaration_reimport_and_source_removal_leave_the_v2_records_intact(
    graph, session, tmp_path
):
    root = tmp_path / "root"
    shutil.copytree(EXAMPLES_DIR / "product-service", root / "product-service")
    shutil.copytree(EXAMPLES_DIR / "order-service", root / "order-service")
    (root / "order-service" / "architecture.yaml").unlink()
    config = FilesystemSourceConfig(id="v2-survival", root=root)
    import_all_sources(graph, database=DATABASE, source_config=config)
    seed = _seed(
        subject="service:order-service", obj="operation:product-service:GET:/products/{id}"
    )
    _persist(graph, seed)
    [before] = _v2_records(session, subject="service:order-service")

    import_all_sources(graph, database=DATABASE, source_config=config)  # reimport
    shutil.rmtree(root / "product-service")
    stats = import_all_sources(graph, database=DATABASE, source_config=config)  # removal
    assert len(stats.removed_source_instance_ids) == 1

    assert _v2_records(session, subject="service:order-service") == (before,)
    degree = session.run("MATCH (v:ScopedObservedCallV2) RETURN COUNT { (v)--() } AS d").single()
    assert degree["d"] == 0


class _Provider:
    def __init__(self, cypher):
        self.cypher, self.composed = cypher, 0

    def generate_cypher(self, *, question, schema_description):
        return self.cypher

    def compose_answer(self, *, question, cypher, rows):
        self.composed += 1
        return "answer"


@pytest.mark.parametrize(
    ("cypher", "error"),
    [
        ("MATCH (n:ScopedObservedCallV2) RETURN n.caller_pod_uid AS p", CypherValidationError),
        (
            "MATCH (n) WHERE n.caller_pod_uid IS NOT NULL RETURN n.caller_pod_uid AS p",
            GraphReachabilityError,
        ),
        ("MATCH (n:`ScopedObservedCallV2`) RETURN n.caller_pod_uid AS p", GraphReachabilityError),
        (
            "MATCH (s:Service|ScopedObservedCallV2) RETURN s.caller_pod_uid AS p",
            GraphReachabilityError,
        ),
        ("MATCH (s:Service) RETURN labels(s) AS l", GraphReachabilityError),
    ],
)
def test_the_nl_path_cannot_reach_a_v2_record(graph, cypher, error):
    _persist(graph, _seed())
    provider = _Provider(cypher)
    service = ArchitectureQuestionService(driver=graph, database=DATABASE, provider=provider)

    with pytest.raises(error):
        service.ask("which pods called what?")

    assert provider.composed == 0


def test_an_authorized_nl_question_still_works_beside_a_v2_record(graph):
    _persist(graph, _seed())
    provider = _Provider("MATCH (s:Service) RETURN s.id AS id")
    service = ArchitectureQuestionService(driver=graph, database=DATABASE, provider=provider)

    result = service.ask("which services exist?")

    assert [row["id"] for row in result.rows] == [CALLER]
    assert question_service.check_node_patterns is not None


# --- atomicity ---------------------------------------------------------------------------------


def test_a_v2_failure_rolls_back_the_whole_unit(graph, session, monkeypatch):
    real = aggregator._persist_scoped_seed
    calls = []

    def failing_on_the_second(tx, seed_record):
        calls.append(seed_record.id)
        if len(calls) == 2:
            raise RuntimeError("injected v2 failure")
        real(tx, seed_record)

    monkeypatch.setattr(aggregator, "_persist_scoped_seed", failing_on_the_second)
    before = read_revision(session)

    with pytest.raises(RuntimeError, match="injected"):
        _persist(graph, _seed(pod="P1"), _seed(pod="P2", trace="b" * 32))

    assert len(calls) == 2  # the first v2 record really was written inside the transaction
    assert _v2_count(session) == 0
    assert _count(session, "MATCH (e:Evidence) RETURN count(e) AS c") == 0
    assert _count(session, "MATCH ()-[r:CALLS]->() RETURN count(r) AS c") == 0
    assert read_revision(session) == before


# --- concurrency -------------------------------------------------------------------------------


def test_concurrent_units_never_lose_an_update(graph, session):
    workers = 12
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []
    trace_ids = [f"{i:x}" * 32 for i in range(workers)]

    def run(index: int) -> None:
        try:
            barrier.wait()
            seed = _seed(
                trace=trace_ids[index],
                at=BASE + timedelta(seconds=index),
                mode="CLIENT_ONLY" if index % 2 else "CLIENT_SERVER",
            )
            persist_observation_batch(graph, DATABASE, _batch(seed), scoped=ON)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert errors == []
    [record] = _v2_records(session)
    assert record.observation_count == workers
    assert record.first_seen == BASE
    assert record.last_seen == BASE + timedelta(seconds=workers - 1)
    assert record.correlation_mode == "CLIENT_SERVER"
    assert record.sample_trace_ids == sorted(trace_ids)[:5]


def test_the_v2_node_lock_alone_prevents_lost_updates(graph, session):
    """In the full path the v1 evidence write, which every unit makes first for the same bucket,
    already serializes units, so the test above cannot tell whether the v2 lock does its job. Drive
    the v2 step alone, concurrently, so nothing else serializes it: without lock-before-read two
    transactions read the same committed count and one overwrites the other."""
    workers, rounds = 16, 4
    errors: list[BaseException] = []
    trace_ids = [
        f"{(r * workers + i) % 4096:03x}".ljust(32, "0")
        for r in range(rounds)
        for i in range(workers)
    ]

    for round_index in range(rounds):
        barrier = threading.Barrier(workers)

        def run(index: int, round_index: int = round_index, barrier: threading.Barrier = barrier):
            try:
                record = record_from_seed(
                    _seed(
                        trace=trace_ids[round_index * workers + index],
                        at=BASE + timedelta(seconds=index),
                    )
                )
                barrier.wait()
                with graph.session(database=DATABASE) as own:
                    own.execute_write(aggregator._persist_scoped_seed, record)
            except BaseException as exc:  # noqa: BLE001 - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=120)

    assert errors == []
    [record] = _v2_records(session)
    assert record.observation_count == workers * rounds


# --- replay / permutation ----------------------------------------------------------------------


def _interactions() -> list[ScopedCallSeed]:
    return [
        _seed(
            pod="P1", trace="1" * 32, at=BASE, k8s_pod_name="orders-a", k8s_namespace_name="shop"
        ),
        _seed(pod="P1", trace="2" * 32, at=BASE + timedelta(seconds=9), k8s_pod_name="orders-b"),
        _seed(pod="P1", trace="3" * 32, at=BASE + timedelta(seconds=4), k8s_pod_name="orders-a"),
        _seed(pod="P2", trace="4" * 32, at=BASE + timedelta(seconds=2), mode="CLIENT_ONLY"),
        _seed(
            pod="P2", trace="5" * 32, at=BASE + timedelta(seconds=3), k8s_deployment_name="orders"
        ),
        _seed(pod="P3", obj="operation:legacy-persist-test:GET:/prices", trace="6" * 32),
    ]


def _replay(driver, splits: list[list[ScopedCallSeed]]):
    _reset(driver)
    for split in splits:
        _persist(driver, *split)
    with driver.session(database=DATABASE) as session:
        return _v2_records(session)


def test_shuffled_order_and_different_post_splits_give_identical_records(driver):
    interactions = _interactions()
    reference = _replay(driver, [interactions])
    assert len(reference) == 3
    p1 = next(r for r in reference if r.caller_pod_uid == "P1")
    assert p1.k8s_pod_name is None and p1.conflicting_consistency_attributes == ["k8s_pod_name"]

    rng = random.Random(20260929)
    for _ in range(4):
        shuffled = list(interactions)
        rng.shuffle(shuffled)
        cut = rng.randint(1, len(shuffled) - 1)
        assert _replay(driver, [shuffled[:cut], shuffled[cut:]]) == reference
    assert _replay(driver, [[s] for s in reversed(interactions)]) == reference


# --- the unit boundary -------------------------------------------------------------------------


def test_one_post_advances_the_revision_by_exactly_one_however_many_seeds(graph, session):
    before = read_revision(session)

    _persist(
        graph, _seed(pod="P1"), _seed(pod="P2", trace="b" * 32), _seed(pod="P3", trace="c" * 32)
    )

    assert _v2_count(session) == 3
    assert read_revision(session) == before + 1


def test_an_empty_post_still_advances_the_revision_once_and_writes_no_v2(graph, session):
    before = read_revision(session)

    persist_observation_batch(graph, DATABASE, ObservationBatch(), scoped=ON)

    assert _v2_count(session) == 0
    assert read_revision(session) == before + 1


_ORDER = DeclaredServiceCandidate(id="service:order-service", name="OrderService", namespace=None)
_PRODUCT = DeclaredServiceCandidate(
    id="service:product-service", name="ProductService", namespace=None
)
_OPERATION = DeclaredOperationCandidate(
    id="operation:product-service:GET:/products/{id}",
    provider_service_id="service:product-service",
    method="GET",
    path="/products/{id}",
)


def _span(**overrides) -> RuntimeSpan:
    fields = {
        "trace_id": "a" * 32,
        "span_id": "c1" * 8,
        "parent_span_id": None,
        "span_name": "op",
        "span_kind": "CLIENT",
        "service_name": "OrderService",
        "environment": "production",
        "k8s_pod_uid": "11111111-aaaa-4bbb-8ccc-000000000001",
        "k8s_cluster_uid": K1,
        "start_time": BASE,
        "end_time": BASE + timedelta(seconds=1),
    }
    fields.update(overrides)
    return RuntimeSpan(**fields)


def _pair():
    client = _span()
    server = _span(
        span_kind="SERVER",
        span_id="d2" * 8,
        parent_span_id=client.span_id,
        service_name="ProductService",
        end_time=BASE + timedelta(seconds=2),
        attributes={"http.request.method": "GET", "http.route": "/products/{id}"},
    )
    return client, server


def _correlate(spans, buffer):
    return correlate_http_call_observations(
        spans,
        service_candidates=[_ORDER, _PRODUCT],
        operation_candidates=[_OPERATION],
        service_aliases={},
        correlation_buffer=buffer,
    )


def test_a_cross_batch_pair_contributes_in_the_post_where_it_resolves(graph, session):
    client, server = _pair()
    buffer = HttpCorrelationBuffer(ttl_seconds=60, max_pending_spans=10000)

    persist_observation_batch(graph, DATABASE, _correlate([client], buffer), scoped=ON)
    assert _v2_count(session) == 0

    persist_observation_batch(graph, DATABASE, _correlate([server], buffer), scoped=ON)
    [record] = _v2_records(session, subject="service:order-service")
    assert record.observation_count == 1
    assert record.first_seen == server.end_time  # the accepted fact time, not the CLIENT's


def test_a_repeated_successful_post_counts_again_in_v1_and_v2(graph, session):
    """Disclosed (D6): there is no v2-only deduplication; a repeated POST is another unit."""
    client, server = _pair()
    for _ in range(2):
        persist_observation_batch(graph, DATABASE, _correlate([client, server], None), scoped=ON)

    [record] = _v2_records(session, subject="service:order-service")
    assert record.observation_count == 2
    evidence = session.run("MATCH (e:Evidence) RETURN e.observation_count AS c").single()
    assert evidence["c"] == 2


# --- the revision fence helpers ---------------------------------------------------------------


def test_bump_revision_returns_the_revision_it_commits(driver):
    _reset(driver)
    with driver.session(database=DATABASE) as session:
        before = read_revision(session)
        returned = session.execute_write(bump_revision)
        assert returned == before + 1 == read_revision(session)


def test_lock_revision_returns_the_current_revision_without_advancing_it(driver):
    _reset(driver)
    with driver.session(database=DATABASE) as session:
        before = read_revision(session)
        assert session.execute_write(lock_revision) == before
        assert read_revision(session) == before
        # The lock is taken with a scratch property that must leave no trace on the singleton.
        keys = session.run("MATCH (s:AipInternalState) RETURN keys(s) AS keys").single()["keys"]
        assert set(keys) == {"id", "revision"}


def test_a_held_revision_lock_blocks_a_concurrent_bump_until_commit(driver):
    _reset(driver)
    finished = threading.Event()

    def bump():
        with driver.session(database=DATABASE) as other:
            other.execute_write(bump_revision)
        finished.set()

    with driver.session(database=DATABASE) as holder:
        tx = holder.begin_transaction()
        lock_revision(tx)
        thread = threading.Thread(target=bump)
        thread.start()
        assert not finished.wait(timeout=1.5), "the bump ran despite the held lock"
        tx.commit()
    thread.join(timeout=30)

    assert finished.is_set()
