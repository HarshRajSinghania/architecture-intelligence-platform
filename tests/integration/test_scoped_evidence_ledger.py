"""Cutover ledger, durable legacy membership and the transition report (v0.6.0 I2.2c).

Real Neo4j. The bare provenance nodes are written inside the same per-POST transaction as the unit
they describe: proven here for the first-unit cutover, mixed marking, exact counters, restart,
stream changes, tampering, racing first units, isolation from every v1 read, the snapshot and the NL
path, atomic rollback and the post-commit sampled logging.
"""

import logging
import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.ai.cypher_validator import CypherValidationError
from app.ai.graph_reachability import GraphReachabilityError
from app.ai.question_service import ArchitectureQuestionService
from app.architecture_intelligence import repository
from app.canonical import ids
from app.graph.revision_fence import read_revision
from app.graph.schema import ensure_schema
from app.settings import ScopedEvidenceConfig
from app.telemetry import aggregator
from app.telemetry.aggregator import persist_observation_batch
from app.telemetry.model import ObservationBatch, RuntimeIdentityObservation
from app.telemetry.scoped_attribution import (
    LocalityDisposition,
    ScopedIngressRefusal,
    server_only_refusal,
)
from app.telemetry.scoped_ledger import (
    CATEGORY_REFUSED,
    CATEGORY_WRITTEN,
    CUTOVER_ID,
    TRANSITION_REPORT_SCHEMA,
    TransitionReportUnstable,
    read_transition_report,
)
from tests.integration.test_scoped_evidence_persistence import BASE, _batch, _seed

DATABASE = "neo4j"
STREAM = "stream-a"
ON = ScopedEvidenceConfig(enabled=True, stream_id=STREAM)
OTHER_STREAM = ScopedEvidenceConfig(enabled=True, stream_id="stream-b")
POD_UID_MISSING = "LOCALITY_POD_UID_MISSING"


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


def _bucket_id(seed) -> str:
    day = datetime.fromisoformat(seed.bucket_utc_day).replace(tzinfo=UTC)
    return ids.observed_evidence_id(seed.environment, day, seed.subject_id, "CALLS", seed.object_id)


def _legacy(driver, *seeds):
    """Pre-existing v1 buckets, written before scoped evidence is ever enabled."""
    persist_observation_batch(driver, DATABASE, _batch(*seeds), scoped=None)


def _unit(driver, *seeds, scoped=ON, refusals=(), unscoped=()):
    """One enabled POST: the given seeds, plus facts that carry no seed (with their refusals)."""
    batch = _batch(*seeds, *unscoped)
    facts = batch.facts[: len(seeds)] + [
        fact.model_copy(update={"scoped_seed": None}) for fact in batch.facts[len(seeds) :]
    ]
    persist_observation_batch(
        driver,
        DATABASE,
        ObservationBatch(entities=batch.entities, facts=facts, scoped_refusals=list(refusals)),
        scoped=scoped,
    )


def _ledger(session):
    return session.run(
        "MATCH (c:ScopedEvidenceCutover) RETURN c.id AS id, c.stream_id AS stream_id, "
        "c.enabled_at_revision AS rev, c.pre_enablement_v1_bucket_count AS n, "
        "c.pre_enablement_v1_bucket_digest AS digest"
    ).data()


def _membership(session) -> dict[str, dict]:
    return {
        r["id"]: {"cutover": r["cutover"], "mixed": r["mixed"]}
        for r in session.run(
            "MATCH (b:ScopedEvidenceLegacyBucket) RETURN b.id AS id, "
            "b.cutover_revision AS cutover, b.mixed_at_revision AS mixed"
        )
    }


# --- the cutover -------------------------------------------------------------------------------


def test_the_first_enabled_unit_records_the_pre_existing_v1_call_buckets(graph, session):
    old_a = _seed(obj="operation:legacy-a:GET:/a", day="2026-09-27")
    old_b = _seed(obj="operation:legacy-b:GET:/b")
    _legacy(graph, old_a, old_b)

    _unit(graph, _seed(pod="P9", obj="operation:brand-new:GET:/n"))

    expected = sorted([_bucket_id(old_a), _bucket_id(old_b)])
    [ledger] = _ledger(session)
    assert ledger["id"] == CUTOVER_ID and ledger["stream_id"] == STREAM
    assert ledger["n"] == 2 and ledger["digest"] == ids.legacy_bucket_digest(expected)
    assert ledger["rev"] == read_revision(session)
    membership = _membership(session)
    assert sorted(membership) == expected
    assert {m["cutover"] for m in membership.values()} == {ledger["rev"]}
    assert {m["mixed"] for m in membership.values()} == {None}
    report = read_transition_report(session, STREAM)
    assert (
        report.legacy.known,
        report.legacy.legacy_unscoped_buckets,
        report.legacy.mixed_buckets,
    ) == (
        True,
        2,
        0,
    )


def test_a_bucket_created_by_the_first_enabled_unit_itself_is_not_legacy(graph, session):
    _unit(graph, _seed(obj="operation:first-ever:GET:/x"))

    [ledger] = _ledger(session)
    assert ledger["n"] == 0
    assert _membership(session) == {}
    assert read_transition_report(session, STREAM).legacy.legacy_unscoped_buckets == 0


def test_declared_and_v2_ids_are_never_membership(graph, session):
    _legacy(graph, _seed(obj="operation:legacy-a:GET:/a"))
    _unit(graph, _seed(pod="P9", obj="operation:new:GET:/n"))

    assert all(b.startswith("evidence:otel:") for b in _membership(session))
    assert not any(b.startswith(ids.SCOPED_CALL_V2_ID_PREFIX) for b in _membership(session))


def test_a_post_cutover_contribution_makes_a_bucket_mixed_whether_written_or_refused(
    graph, session
):
    written = _seed(obj="operation:legacy-a:GET:/a")
    refused = _seed(obj="operation:legacy-b:GET:/b")
    untouched = _seed(obj="operation:legacy-c:GET:/c")
    _legacy(graph, written, refused, untouched)

    _unit(graph, written)  # written to v2: also the cutover unit
    after_first = read_revision(session)
    _unit(
        graph,
        unscoped=[refused],
        refusals=[
            ScopedIngressRefusal(
                trace_id=refused.trace_id,
                environment=refused.environment,
                bucket_utc_day=refused.bucket_utc_day,
                disposition=LocalityDisposition.INSUFFICIENT_EVIDENCE,
                reasons=(POD_UID_MISSING,),
            )
        ],
    )
    after_second = read_revision(session)

    membership = _membership(session)
    assert membership[_bucket_id(written)]["mixed"] == after_first
    assert membership[_bucket_id(refused)]["mixed"] == after_second
    assert membership[_bucket_id(untouched)]["mixed"] is None
    legacy = read_transition_report(session, STREAM).legacy
    assert (legacy.legacy_unscoped_buckets, legacy.mixed_buckets) == (1, 2)


def test_a_bucket_stays_marked_at_the_revision_of_its_first_mixing_unit(graph, session):
    seed = _seed(obj="operation:legacy-a:GET:/a")
    _legacy(graph, seed)
    _unit(graph, seed)
    first = _membership(session)[_bucket_id(seed)]["mixed"]

    _unit(graph, _seed(obj="operation:legacy-a:GET:/a", trace="b" * 32))

    assert _membership(session)[_bucket_id(seed)]["mixed"] == first


def test_an_unrelated_runtime_identity_observation_never_marks_a_bucket(graph, session):
    seed = _seed(obj="operation:legacy-a:GET:/a")
    _legacy(graph, seed)
    other = _seed(pod="P9", obj="operation:other:GET:/o")
    batch = _batch(other)
    observation = RuntimeIdentityObservation(
        id="runtime-identity:otel:production:2026-09-28:abc",
        service_name="orders",
        environment="production",
        k8s_pod_uid="P1",
        first_seen=BASE,
        last_seen=BASE,
        observation_count=1,
    )
    persist_observation_batch(
        graph,
        DATABASE,
        batch.model_copy(update={"runtime_identity_observations": [observation]}),
        scoped=ON,
    )

    assert _membership(session)[_bucket_id(seed)]["mixed"] is None


def test_repeated_enabled_units_never_rewrite_the_ledger_or_membership(graph, session):
    old = _seed(obj="operation:legacy-a:GET:/a")
    _legacy(graph, old)
    _unit(graph, _seed(pod="P2", obj="operation:new:GET:/n"))
    ledger_before, membership_before = _ledger(session), _membership(session)

    for i in range(3):
        _unit(graph, _seed(pod=f"P{i}", obj="operation:new:GET:/n", trace=f"{i}" * 32))

    assert _ledger(session) == ledger_before
    assert _membership(session) == membership_before


def test_the_report_is_rebuilt_from_the_graph_alone_by_a_fresh_connection(
    graph, session, neo4j_container
):
    seed = _seed(obj="operation:legacy-a:GET:/a")
    _legacy(graph, seed)
    _unit(graph, seed)
    before = read_transition_report(session, STREAM)

    fresh = neo4j_container.get_driver()  # a new process's connection: no in-memory state carried
    try:
        with fresh.session(database=DATABASE) as other:
            after = read_transition_report(other, STREAM)
    finally:
        fresh.close()

    assert after == before
    assert before.schema == TRANSITION_REPORT_SCHEMA == "aip-scoped-evidence-transition-report/1"


# --- a report is only as-of the revision it is consistent with ---------------------------------


def test_a_unit_committing_mid_read_is_never_reported_under_a_stale_revision(graph, session):
    _unit(graph, _seed())
    calls: list[int] = []

    def revision_fn() -> int:
        revision = read_revision(session)
        calls.append(revision)
        if len(calls) == 1:
            # A POST commits after the first revision read and before the report's queries.
            _unit(graph, _seed(pod="P2", trace="b" * 32))
        return revision

    report = read_transition_report(session, STREAM, read_revision_fn=revision_fn)

    current = read_revision(session)
    assert calls == [current - 1, current, current, current]  # attempt 1 discarded, attempt 2 kept
    assert report.as_of_revision == current
    assert sum(r.count for r in report.scoped_v2_written) == 2
    assert max(r.last_revision for r in report.scoped_v2_written) <= report.as_of_revision


def test_a_graph_that_never_settles_fails_closed_instead_of_reporting(graph, session):
    _unit(graph, _seed())
    moves = iter(range(1000))

    def always_moving() -> int:
        _unit(graph, _seed(pod=f"P{next(moves)}", trace="c" * 32))
        return read_revision(session)

    with pytest.raises(TransitionReportUnstable, match="after 3 attempts"):
        read_transition_report(session, STREAM, read_revision_fn=always_moving)


def test_a_quiet_graph_is_read_once_with_two_revision_reads(graph, session):
    _unit(graph, _seed())
    calls: list[int] = []

    def counting() -> int:
        calls.append(read_revision(session))
        return calls[-1]

    report = read_transition_report(session, STREAM, read_revision_fn=counting)

    assert len(calls) == 2 and report.as_of_revision == calls[0]


# --- unknown history ---------------------------------------------------------------------------


def test_a_changed_stream_id_is_unknown_and_never_a_second_cutover(graph, session):
    _legacy(graph, _seed(obj="operation:legacy-a:GET:/a"))
    _unit(graph, _seed(pod="P2", obj="operation:new:GET:/n"))
    ledger, membership = _ledger(session), _membership(session)

    _unit(graph, _seed(pod="P3", obj="operation:new:GET:/n", trace="b" * 32), scoped=OTHER_STREAM)

    assert _ledger(session) == ledger and _membership(session) == membership
    other = read_transition_report(session, "stream-b")
    assert (other.legacy.known, other.legacy.unknown_reason) == (False, "STREAM_ID_MISMATCH")
    assert other.legacy.legacy_unscoped_buckets is None
    assert sum(r.count for r in other.scoped_v2_written) == 1
    assert read_transition_report(session, STREAM).legacy.known is True
    assert sum(r.count for r in read_transition_report(session, STREAM).scoped_v2_written) == 1


def test_a_missing_ledger_is_unknown_not_legacy_by_absence(graph, session):
    _legacy(graph, _seed(obj="operation:legacy-a:GET:/a"))

    report = read_transition_report(session, STREAM)

    assert (report.legacy.known, report.legacy.unknown_reason) == (False, "NO_LEDGER")
    assert report.scoped_v2_written == () and report.scoped_v2_refused == ()


def test_a_tampered_membership_or_digest_is_unknown(graph, session):
    for old in ("operation:legacy-a:GET:/a", "operation:legacy-b:GET:/b"):
        _legacy(graph, _seed(obj=old))
    _unit(graph, _seed(pod="P2", obj="operation:new:GET:/n"))
    assert read_transition_report(session, STREAM).legacy.known is True

    victim = min(_membership(session))
    session.run(
        "MATCH (b:ScopedEvidenceLegacyBucket {id: $id}) DETACH DELETE b", id=victim
    ).consume()
    assert read_transition_report(session, STREAM).legacy.unknown_reason == "MEMBERSHIP_MISMATCH"

    session.run("MERGE (b:ScopedEvidenceLegacyBucket {id: $id})", id=victim).consume()
    assert read_transition_report(session, STREAM).legacy.known is True
    session.run(
        "MATCH (c:ScopedEvidenceCutover) SET c.pre_enablement_v1_bucket_digest = 'tampered'"
    ).consume()
    assert read_transition_report(session, STREAM).legacy.unknown_reason == "MEMBERSHIP_MISMATCH"


# --- a race on the very first enabled unit -----------------------------------------------------


def test_racing_first_units_write_exactly_one_consistent_ledger(graph, session):
    legacy_seeds = [_seed(obj=f"operation:legacy-{i}:GET:/x") for i in range(5)]
    for legacy_seed in legacy_seeds:
        _legacy(graph, legacy_seed)
    workers = 6
    barrier = threading.Barrier(workers)
    errors: list[BaseException] = []

    def run(index: int) -> None:
        try:
            barrier.wait()
            # A distinct environment per worker gives each unit its own counter row, so each unit's
            # committed revision stays visible in the report afterwards.
            _unit(
                graph,
                _seed(pod=f"P{index}", env=f"env-{index}", obj=f"operation:racing-{index}:GET:/y"),
            )
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=180)

    assert errors == []
    [ledger] = _ledger(session)
    membership = _membership(session)
    assert ledger["n"] == 5 == len(membership)
    assert ledger["digest"] == ids.legacy_bucket_digest(list(membership))
    assert set(membership) == {_bucket_id(legacy_seed) for legacy_seed in legacy_seeds}
    report = read_transition_report(session, STREAM)
    assert report.legacy.known is True
    assert sum(r.count for r in report.scoped_v2_written) == workers
    # Exactly one unit wrote the cutover, and it was the first to commit: a racer that wrongly
    # believed it wrote it would have overwritten `enabled_at_revision` with its own, later one.
    unit_revisions = [r.last_revision for r in report.scoped_v2_written]
    assert len(set(unit_revisions)) == workers
    assert ledger["rev"] == min(unit_revisions)
    assert {m["cutover"] for m in membership.values()} == {ledger["rev"]}


# --- counters ----------------------------------------------------------------------------------


def _refusal(reason=POD_UID_MISSING, *, day="2026-09-28", env="production", trace="a" * 32):
    return ScopedIngressRefusal(
        trace_id=trace,
        environment=env,
        bucket_utc_day=day,
        disposition=LocalityDisposition.INSUFFICIENT_EVIDENCE,
        reasons=(reason,),
    )


def test_counters_are_exact_per_interaction_not_per_merged_record(graph, session):
    same_record = [_seed(trace=f"{i}" * 32, at=BASE + timedelta(seconds=i)) for i in range(3)]
    refusals = [_refusal(), _refusal(), _refusal("LOCALITY_CLUSTER_UID_MISSING")]

    _unit(graph, *same_record, refusals=refusals)

    report = read_transition_report(session, STREAM)
    [written] = report.scoped_v2_written
    assert (written.environment, written.utc_day, written.primary_reason, written.count) == (
        "production",
        "2026-09-28",
        None,
        3,
    )
    assert session.run("MATCH (v:ScopedObservedCallV2) RETURN count(v) AS c").single()["c"] == 1
    by_reason = {r.primary_reason: r.count for r in report.scoped_v2_refused}
    assert by_reason == {POD_UID_MISSING: 2, "LOCALITY_CLUSTER_UID_MISSING": 1}


def test_counters_accumulate_across_units_and_are_keyed_by_environment_and_day(graph, session):
    _unit(graph, _seed(), refusals=[_refusal()])
    revision = read_revision(session)
    _unit(
        graph,
        _seed(pod="P2", trace="b" * 32),
        _seed(pod="P3", env="staging", trace="c" * 32),
        _seed(pod="P4", day="2026-09-29", at=BASE + timedelta(days=1), trace="d" * 32),
        refusals=[_refusal(), _refusal(day="2026-09-29", env="staging")],
    )

    report = read_transition_report(session, STREAM)
    written = {(r.utc_day, r.environment): r for r in report.scoped_v2_written}
    assert {k: v.count for k, v in written.items()} == {
        ("2026-09-28", "production"): 2,
        ("2026-09-28", "staging"): 1,
        ("2026-09-29", "production"): 1,
    }
    assert written[("2026-09-28", "production")].last_revision == read_revision(session)
    assert written[("2026-09-28", "production")].last_revision > revision
    refused = {(r.utc_day, r.environment): r.count for r in report.scoped_v2_refused}
    assert refused == {("2026-09-28", "production"): 2, ("2026-09-29", "staging"): 1}
    assert [r.utc_day for r in report.scoped_v2_written] == sorted(
        r.utc_day for r in report.scoped_v2_written
    )


def test_a_server_only_refusal_is_counted_under_its_own_cause(graph, session):
    refusal = server_only_refusal(trace_id="e" * 32, environment="production", timestamp=BASE)

    _unit(graph, refusals=[refusal])

    [row] = read_transition_report(session, STREAM).scoped_v2_refused
    assert row.primary_reason == "LOCALITY_SERVER_ONLY_NO_CLIENT" and row.count == 1


def test_a_stream_report_never_counts_another_streams_interactions(graph, session):
    _unit(graph, _seed(), scoped=ON)
    _unit(
        graph, _seed(pod="P2", trace="b" * 32), _seed(pod="P3", trace="c" * 32), scoped=OTHER_STREAM
    )

    assert sum(r.count for r in read_transition_report(session, STREAM).scoped_v2_written) == 1
    assert sum(r.count for r in read_transition_report(session, "stream-b").scoped_v2_written) == 2
    assert read_transition_report(session, "nobody").scoped_v2_written == ()


# --- isolation ---------------------------------------------------------------------------------


def test_the_provenance_nodes_are_bare_isolated_and_invisible_to_every_read(driver):
    seeds = [_seed(obj="operation:legacy-a:GET:/a")]
    fingerprints = {}
    for label, scoped in (("off", None), ("on", ON)):
        _reset(driver)
        _legacy(driver, *seeds)
        _unit(driver, *seeds, scoped=scoped, refusals=[_refusal()] if scoped else [])
        with driver.session(database=DATABASE) as s:
            state = repository.canonical_snapshot_state(s, coverage_qualification_enabled=True)
            fingerprints[label] = (repository.snapshot_fingerprint(state), read_revision(s))
            if label == "on":
                nodes = s.run(
                    "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ScopedEvidence') "
                    "RETURN labels(n) AS labels, keys(n) AS keys, COUNT { (n)--() } AS degree"
                ).data()
                assert {tuple(n["labels"]) for n in nodes} == {
                    ("ScopedEvidenceCutover",),
                    ("ScopedEvidenceLegacyBucket",),
                    ("ScopedEvidenceTransitionCounter",),
                }
                assert all(n["degree"] == 0 for n in nodes)
                assert not any("owner_source_ids" in n["keys"] for n in nodes)
                every_id = {
                    r["id"] for r in s.run("MATCH (n) WHERE n.id IS NOT NULL RETURN n.id AS id")
                }
                listed = {row["id"] for row in repository.read_public_evidence_list_rows(s)}
                assert not listed & {
                    i for i in every_id if i.startswith("scoped-evidence-counter:")
                }
                assert not listed & {CUTOVER_ID}
                relation_ids = {
                    e for r in state["relations"] for e in (r.get("evidence_ids") or [])
                }
                assert not any(i.startswith("scoped-evidence-counter:") for i in relation_ids)

    assert fingerprints["on"] == fingerprints["off"]


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
        ("MATCH (n:ScopedEvidenceCutover) RETURN n.stream_id AS s", CypherValidationError),
        ("MATCH (n:ScopedEvidenceLegacyBucket) RETURN n.id AS s", CypherValidationError),
        ("MATCH (n:ScopedEvidenceTransitionCounter) RETURN n.count AS s", CypherValidationError),
        ("MATCH (n) WHERE n.stream_id IS NOT NULL RETURN n.stream_id AS s", GraphReachabilityError),
        ("MATCH (n:`ScopedEvidenceCutover`) RETURN n.stream_id AS s", GraphReachabilityError),
    ],
)
def test_the_nl_path_cannot_reach_the_provenance_nodes(graph, cypher, error):
    _legacy(graph, _seed(obj="operation:legacy-a:GET:/a"))
    _unit(graph, _seed(pod="P2", obj="operation:new:GET:/n"), refusals=[_refusal()])
    provider = _Provider(cypher)
    service = ArchitectureQuestionService(driver=graph, database=DATABASE, provider=provider)

    with pytest.raises(error):
        service.ask("what is the stream?")

    assert provider.composed == 0


# --- atomicity and logging ---------------------------------------------------------------------


def test_a_failed_unit_leaves_no_ledger_membership_or_counter(graph, session, monkeypatch):
    _legacy(graph, _seed(obj="operation:legacy-a:GET:/a"))
    real = aggregator._persist_scoped_seed
    monkeypatch.setattr(
        aggregator,
        "_persist_scoped_seed",
        lambda tx, record: (real(tx, record), (_ for _ in ()).throw(RuntimeError("injected")))[0],
    )
    before = read_revision(session)

    with pytest.raises(RuntimeError, match="injected"):
        _unit(graph, _seed(pod="P2", obj="operation:new:GET:/n"), refusals=[_refusal()])

    assert _ledger(session) == [] and _membership(session) == {}
    assert (
        session.run("MATCH (c:ScopedEvidenceTransitionCounter) RETURN count(c) AS c").single()["c"]
        == 0
    )
    assert session.run("MATCH (v:ScopedObservedCallV2) RETURN count(v) AS c").single()["c"] == 0
    assert read_revision(session) == before


def test_samples_are_logged_only_after_a_unit_commits(graph, caplog, monkeypatch):
    refusals = [_refusal(trace=f"{i:032x}") for i in range(23)]
    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        _unit(graph, _seed(), refusals=refusals)
    lines = [r.getMessage() for r in caplog.records if r.name == "app.telemetry.scoped_ledger"]
    assert sum("trace_id=" in m for m in lines) == 20
    assert sum("suppressed=3" in m for m in lines) == 1

    caplog.clear()
    monkeypatch.setattr(
        aggregator,
        "_persist_scoped_seed",
        lambda tx, record: (_ for _ in ()).throw(RuntimeError("x")),
    )
    with (
        caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"),
        pytest.raises(RuntimeError),
    ):
        _unit(graph, _seed(pod="P2"), refusals=refusals)
    assert [r for r in caplog.records if r.name == "app.telemetry.scoped_ledger"] == []


def test_nothing_is_logged_or_written_with_the_flag_off(graph, session, caplog):
    with caplog.at_level(logging.INFO, logger="app.telemetry.scoped_ledger"):
        _unit(graph, _seed(), scoped=None, refusals=[_refusal()])

    assert [r for r in caplog.records if r.name == "app.telemetry.scoped_ledger"] == []
    assert (
        session.run(
            "MATCH (n) WHERE any(l IN labels(n) WHERE l STARTS WITH 'ScopedEvidence') RETURN count(n) AS c"
        ).single()["c"]
        == 0
    )


def test_the_category_names_are_the_frozen_ones():
    assert (CATEGORY_WRITTEN, CATEGORY_REFUSED) == ("SCOPED_V2_WRITTEN", "SCOPED_V2_REFUSED")
    assert CUTOVER_ID == "graph"
